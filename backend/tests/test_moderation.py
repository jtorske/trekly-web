"""Moderation: each screening outcome, the API-down fallback, child safety,
the report threshold, new-account limits, the digest and the admin actions.

OpenAI, Storage, email and Supabase are fakes (tests/moderation_fakes.py);
auth.users rows are written directly to set email confirmation and account age.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import insert, select

from app import moderation, moderation_config as config
from app.main import app
from app.models.account import Profile
from app.models.admin import AUTH_USERS, SYSTEM_ADMIN_ID, AdminAuditLog
from app.models.hike_log import HikeLog
from app.models.moderation import AccountRestriction, ModerationItem
from app.models.privacy import ProfileModeration, ProfileReport
from app.models.social import Block
from app.moderation import get_moderation_services
from tests.moderation_fakes import FakeMedia, FakeScreener, FakeSupabase, Outbox, fake_services
from tests.test_availability import world  # noqa: F401  (fixture)
from tests.test_trail_hikers import hikers


def listed(client, world):  # noqa: F811
    """The first trip note others see in "Hiked by", or None."""
    notes = hikers(client, world)["notes"]
    return notes[0] if notes else None


def listed_note(client, world):  # noqa: F811
    note = listed(client, world)
    return note["note"] if note else None

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=30)


@pytest.fixture
def mod():
    """The fakes behind every request in a test, shared so tests can inspect them."""
    fakes = SimpleNamespace(screener=FakeScreener(), outbox=Outbox(), author_outbox=Outbox(), media=FakeMedia(),
                            supabase=FakeSupabase())
    app.dependency_overrides[get_moderation_services] = lambda: fake_services(
        screener=fakes.screener, outbox=fakes.outbox, author_outbox=fakes.author_outbox, media=fakes.media,
        supabase=fakes.supabase)
    return fakes


@pytest.fixture
def account(client, make_token, session_factory, world):  # noqa: F811
    """A signed-up user with a username, in auth.users with the given age and confirmation."""

    def _make(username, *, age=timedelta(days=30), confirmed=True, community=True):
        user_id = uuid.uuid4()
        db = session_factory()
        db.execute(insert(AUTH_USERS).values(id=user_id, email=f"{username}@example.com", created_at=NOW - age,
                                             email_confirmed_at=NOW - age if confirmed else None))
        db.commit()
        db.close()
        headers = {"Authorization": f"Bearer {make_token(user_id, email=f'{username}@example.com')}"}
        assert client.patch("/api/me/profile", json={"username": username, "display_name": username.title()},
                            headers=headers).status_code == 200
        if community:
            assert client.patch("/api/me/privacy", json={"show_in_community": True},
                                headers=headers).status_code == 200
        return SimpleNamespace(id=user_id, headers=headers, username=username)

    return _make


@pytest.fixture
def admin(make_token, monkeypatch):
    admin_id = uuid.uuid4()
    monkeypatch.setenv("ADMIN_USER_IDS", str(admin_id))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    return {"Authorization": f"Bearer {make_token(admin_id)}"}


def log_hike(client, world, who, *, note=None, photo=None, status=None):  # noqa: F811
    body = {"hiked_on": "2026-08-14", "note": note}
    if photo is not None:
        body["photo_path"] = photo if "/" in photo else f"{who.id}/{photo}"
    response = client.put(f"/api/me/hike-logs/{world['trail']}", json=body, headers=who.headers)
    if status is not None:
        assert response.status_code == status, response.text
    return response


def photo_name():
    return f"{uuid.uuid4()}.webp"


def items(session_factory, **where):
    db = session_factory()
    rows = db.scalars(select(ModerationItem).filter_by(**where)).all()
    db.close()
    return rows


def column(session_factory, model, key, attribute):
    db = session_factory()
    value = getattr(db.get(model, key), attribute)
    db.close()
    return value


# ------------------------------------------------------------ screening outcomes


def test_clearly_fine_content_publishes_and_keeps_its_scores(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    saved = log_hike(client, world, ana, note="Larches were glowing", status=201).json()
    assert saved["note"] == "Larches were glowing" and saved["review"] is None
    assert listed_note(client, world) == "Larches were glowing"

    [item] = items(session_factory, kind="hike_note")
    assert item.state == "visible" and not item.in_queue and item.screening == "passed"
    assert item.scores["harassment"] == pytest.approx(0.01) and item.screening_model == "omni-moderation-test"
    assert mod.outbox.sent == []


def test_flagged_note_is_held_for_the_author_only_and_queued(client, world, account, mod, session_factory):  # noqa: F811
    mod.screener.flag = {"idiot": ["harassment"]}
    ana = account("ana")
    saved = log_hike(client, world, ana, note="You're all idiots", status=201).json()
    # The author sees it, marked as being reviewed.
    assert saved["note"] == "You're all idiots" and saved["review"] == "pending" and saved["review_parts"] == ["note"]
    assert client.get("/api/me/hike-logs", headers=ana.headers).json()[0]["review"] == "pending"
    # Nobody else does: it isn't in the entry at all.
    assert listed_note(client, world) is None
    [log] = items(session_factory, kind="hike_note")
    assert column(session_factory, HikeLog, log.target_id, "note") is None

    assert log.state == "held" and log.in_queue and log.queue_reason == "flagged"
    assert log.flagged_categories == ["harassment"] and log.scores["harassment"] == pytest.approx(0.97)
    assert log.text == "You're all idiots"  # never deleted
    [digest] = mod.outbox.sent
    assert digest.to == config.ADMIN_EMAIL and "1 held" in digest.subject and "idiots" in digest.text


def test_resending_the_held_note_doesnt_screen_again(client, world, account, mod, session_factory):  # noqa: F811
    mod.screener.flag = {"idiot": ["harassment"]}
    ana = account("ana")
    log_hike(client, world, ana, note="idiot", status=201)
    calls = len(mod.screener.calls)
    again = log_hike(client, world, ana, note="idiot", status=200).json()
    assert len(mod.screener.calls) == calls and again["review"] == "pending"
    # Replacing it with something fine publishes the new note and drops it from the queue.
    fixed = log_hike(client, world, ana, note="Great day out", status=200).json()
    assert fixed["review"] is None and listed_note(client, world) == "Great day out"
    assert not items(session_factory, kind="hike_note")[0].in_queue


def test_flagged_photo_is_held(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    bad = photo_name()
    mod.screener.flag = {f"{ana.id}/{bad}": ["violence/graphic"]}
    saved = log_hike(client, world, ana, note="Fine words", photo=bad, status=201).json()
    assert saved["review_parts"] == ["photo"] and saved["photo_path"].endswith(bad)
    entry = listed(client, world)
    assert entry["note"] == "Fine words" and entry["photo_path"] is None
    [item] = items(session_factory, kind="hike_photo")
    assert item.state == "held" and item.photo_path.endswith(bad)


def test_flagged_bio_and_avatar_are_held(client, account, mod, session_factory):
    ana = account("ana", community=False)
    avatar = f"{ana.id}/{photo_name()}"
    mod.screener.flag = {"scam": ["harassment"], avatar: ["sexual"]}
    body = client.patch("/api/me/profile", json={"bio": "Join my scam", "avatar_path": avatar},
                        headers=ana.headers).json()
    assert body["bio"] == "Join my scam" and body["avatar_path"] == avatar
    assert body["review"] == "pending" and set(body["review_parts"]) == {"bio", "avatar"}
    assert column(session_factory, Profile, ana.id, "bio") is None
    assert column(session_factory, Profile, ana.id, "avatar_path") is None
    public = client.get(f"/api/profiles/{ana.username}").json()
    assert public["profile"].get("bio") is None if "profile" in public else public.get("bio") is None


# ------------------------------------------------------------ the API is down


@pytest.mark.parametrize("screener", [FakeScreener(down=True), None])
def test_when_screening_is_down_content_publishes_and_queues(client, world, account, session_factory, screener):  # noqa: F811
    outbox = Outbox()
    app.dependency_overrides[get_moderation_services] = lambda: fake_services(
        screener=screener if screener is not None else False, outbox=outbox)
    if screener is None:  # no OPENAI_API_KEY at all
        app.dependency_overrides[get_moderation_services] = lambda: _no_key(outbox)
    ana = account("ana")
    saved = log_hike(client, world, ana, note="Unchecked words", status=201).json()
    assert saved["review"] is None and listed_note(client, world) == "Unchecked words"
    [item] = items(session_factory, kind="hike_note")
    assert item.state == "visible" and item.in_queue and item.queue_reason == "unscreened"
    assert item.screening == "unavailable" and item.scores is None
    assert "Published unscreened" in outbox.sent[0].text


def _no_key(outbox):
    services = fake_services(outbox=outbox)
    services.screener = None
    return services


def test_an_unreadable_photo_counts_as_down(client, world, account, mod, session_factory):  # noqa: F811
    def broken(bucket, path):
        raise RuntimeError("storage down")

    mod.media.read = broken
    ana = account("ana")
    saved = log_hike(client, world, ana, photo=photo_name(), status=201).json()
    assert saved["review"] is None
    assert items(session_factory, kind="hike_photo")[0].queue_reason == "unscreened"


# ------------------------------------------------------------ child safety


def test_child_safety_flag_hides_keeps_locks_and_alerts(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    bad = photo_name()
    mod.screener.flag = {f"{ana.id}/{bad}": ["sexual", "sexual/minors"]}
    saved = log_hike(client, world, ana, photo=bad, status=201).json()
    assert saved["review"] == "pending"
    assert listed(client, world) is None  # no note, and the photo isn't on the entry

    [item] = items(session_factory, kind="hike_photo")
    assert item.child_safety and item.state == "held" and item.queue_reason == "child_safety"
    assert item.photo_path.endswith(bad)  # kept
    assert mod.media.quarantined == [("hike-photos", f"{ana.id}/{bad}")] and item.quarantine_path
    # Locked: restriction, hidden profile, Supabase ban, audited as the system.
    db = session_factory()
    assert db.get(AccountRestriction, ana.id).locked_at is not None
    assert db.get(ProfileModeration, ana.id) is not None
    [audit] = db.scalars(select(AdminAuditLog)).all()
    assert audit.action == "lock_account" and audit.admin_id == SYSTEM_ADMIN_ID
    db.close()
    assert ("ban", ana.id) in mod.supabase.calls
    # The urgent alert went at once, without the content or a link to it.
    urgent = [e for e in mod.outbox.sent if e.subject.startswith("URGENT")]
    assert len(urgent) == 1
    assert "cybertip.ca" in urgent[0].text.lower() and "21 days" in urgent[0].text
    assert bad not in urgent[0].text.replace(item.quarantine_path, "")
    assert mod.author_outbox.sent == []  # the author is never told
    # The account can't post any more.
    assert log_hike(client, world, ana, note="more").status_code == 403


def test_child_safety_items_never_show_their_photo_to_admins(client, world, account, mod, admin):  # noqa: F811
    ana = account("ana")
    bad = photo_name()
    mod.screener.flag = {f"{ana.id}/{bad}": ["sexual/minors"]}
    log_hike(client, world, ana, photo=bad, status=201)
    [listed] = client.get("/api/admin/moderation", headers=admin).json()["items"]
    assert listed["child_safety"] and listed["photo_url"] is None and listed["has_photo"]


# ------------------------------------------------------------ reports


def _report(client, who, username, **body):
    return client.post(f"/api/profiles/{username}/report", json={"reason": "harassment", **body},
                       headers=who.headers)


def test_three_qualifying_reports_hide_an_item_pending_review(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    log_hike(client, world, ana, note="Mean words", status=201)
    reporters = [account(f"rep{n}") for n in range(3)]
    for who in reporters[:2]:
        assert _report(client, who, "ana", trail_id=str(world["trail"])).status_code == 202
    assert listed_note(client, world) == "Mean words"  # two isn't enough
    [item] = items(session_factory, kind="hike_note")
    assert item.in_queue and item.queue_reason == "reported" and item.open_reports == 2

    assert _report(client, reporters[2], "ana", trail_id=str(world["trail"])).status_code == 202
    [item] = items(session_factory, kind="hike_note")
    assert item.state == "held" and item.qualifying_reports == 3
    assert listed_note(client, world) is None
    assert client.get("/api/me/hike-logs", headers=ana.headers).json()[0]["review"] == "pending"


def test_new_or_unconfirmed_reporters_dont_count_toward_the_hide(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    log_hike(client, world, ana, note="Words", status=201)
    weak = [account("young", age=timedelta(days=3)), account("unconfirmed", confirmed=False),
            account("almost", age=config.REPORTER_MIN_ACCOUNT_AGE - timedelta(hours=1))]
    strong = [account("old1"), account("old2")]
    for who in weak + strong:
        assert _report(client, who, "ana", trail_id=str(world["trail"])).status_code == 202
    [item] = items(session_factory, kind="hike_note")
    assert item.open_reports == 5 and item.qualifying_reports == 2 and item.state == "visible"


def test_reports_from_someone_the_author_blocked_are_ignored(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    log_hike(client, world, ana, note="Words", status=201)
    reporters = [account(f"rep{n}") for n in range(3)]
    db = session_factory()
    db.add(Block(blocker_id=ana.id, blocked_id=reporters[0].id))
    # A block the other way round (a reporter blocking the author) doesn't matter.
    db.add(Block(blocker_id=reporters[1].id, blocked_id=ana.id))
    db.commit()
    db.close()
    for who in reporters:
        assert _report(client, who, "ana", trail_id=str(world["trail"])).status_code == 202
    [item] = items(session_factory, kind="hike_note")
    assert item.qualifying_reports == 2 and item.state == "visible"
    db = session_factory()
    assert db.scalar(select(ProfileReport).where(ProfileReport.reporter_id == reporters[0].id)).counts_toward_hide is False
    db.close()


def test_three_reports_on_a_post_hide_it_from_the_feed(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    client.patch("/api/me/privacy", json={"share_activity": True}, headers=ana.headers)
    body = {"hiked_on": "2026-08-14", "note": "Spammy", "share": True}
    assert client.put(f"/api/me/hike-logs/{world['trail']}", json=body, headers=ana.headers).status_code == 201
    feed = client.get("/api/activity").json()["items"]
    post_id = next(p["id"] for p in feed if p["kind"] == "hike")
    for n in range(3):
        assert _report(client, account(f"rep{n}"), "ana", post_id=post_id).status_code == 202
    assert all(p["id"] != post_id for p in client.get("/api/activity").json()["items"])
    mine = client.get("/api/activity", headers=ana.headers).json()["items"]
    held = next(p for p in mine if p["id"] == post_id)
    assert held["review"] == "pending" and held["hike"]["note"] == "Spammy"


# ------------------------------------------------------------ new-account limits


def test_photos_wait_for_a_confirmed_email(client, world, account, mod):  # noqa: F811
    new = account("newbie", age=timedelta(hours=1), confirmed=False)
    refused = log_hike(client, world, new, note="ok", photo=photo_name())
    assert refused.status_code == 403 and "Confirm your email" in refused.text
    avatar = client.patch("/api/me/profile", json={"avatar_path": f"{new.id}/{photo_name()}"}, headers=new.headers)
    assert avatar.status_code == 403
    # Text is fine.
    log_hike(client, world, new, note="ok", status=201)


def test_new_accounts_have_lower_post_limits(client, account, mod, session_factory, monkeypatch):
    from app.models.trail import Trail

    db = session_factory()
    trails = [Trail(name=f"T{n}", region="R", country_code="CA", province_code="BC", terrain_difficulty="easy") for n in range(8)]
    db.add_all(trails)
    db.commit()
    ids = [t.id for t in trails]
    db.close()
    monkeypatch.setattr(config, "NEW_ACCOUNT_POST_LIMITS", ((3, timedelta(hours=1)),))
    monkeypatch.setattr(config, "POST_LIMITS", ((6, timedelta(hours=1)),))

    def log_many(who, n):
        return [client.put(f"/api/me/hike-logs/{ids[i]}", json={"hiked_on": "2026-08-14"},
                           headers=who.headers).status_code for i in range(n)]

    new = account("fresh", age=timedelta(hours=2))
    assert log_many(new, 4) == [201, 201, 201, 429]
    old = account("veteran")
    assert log_many(old, 4) == [201, 201, 201, 201]


def test_comment_limits_need_a_confirmed_email_and_are_lower_at_first(client, account, session_factory, monkeypatch):
    monkeypatch.setattr(config, "NEW_ACCOUNT_COMMENT_LIMITS", ((2, timedelta(hours=1)),))
    unconfirmed, new, old = (account("unconf1", confirmed=False), account("newbie1", age=timedelta(hours=3)),
                             account("oldie1"))
    db = session_factory()
    with pytest.raises(HTTPException) as raised:
        moderation.ensure_can_comment(db, unconfirmed.id, lambda since: 0)
    assert raised.value.status_code == 403
    with pytest.raises(HTTPException) as raised:
        moderation.ensure_can_comment(db, new.id, lambda since: 2)
    assert raised.value.status_code == 429
    moderation.ensure_can_comment(db, old.id, lambda since: 2)  # established: the higher limit
    db.close()


# ------------------------------------------------------------ the digest


def test_at_most_one_digest_an_hour(client, world, account, mod, session_factory):  # noqa: F811
    mod.screener.flag = {"bad": ["harassment"]}
    for name in ("ana", "ben", "cyd"):
        log_hike(client, world, account(name), note="bad", status=201)
    assert len(mod.outbox.sent) == 1  # the first; the others wait
    db = session_factory()
    sent_at = moderation.now()  # just after the first digest
    assert moderation.maybe_send_digest(db, mod.outbox, sent_at + timedelta(minutes=30)) is False
    assert moderation.maybe_send_digest(db, mod.outbox, sent_at + timedelta(minutes=61)) is True
    db.close()
    assert len(mod.outbox.sent) == 2 and "2 new" in mod.outbox.sent[1].subject


# ------------------------------------------------------------ admin actions


def _held_note(client, world, account, mod, name="ana", note="You idiot"):  # noqa: F811
    mod.screener.flag = {"idiot": ["harassment"]}
    who = account(name)
    log_hike(client, world, who, note=note, status=201)
    return who


def _audits(session_factory):
    db = session_factory()
    rows = [(r.action, r.target_user_id) for r in db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at))]
    db.close()
    return rows


def test_admin_queue_lists_held_and_reported_with_scores(client, world, account, mod, admin):  # noqa: F811
    _held_note(client, world, account, mod)
    ben = account("ben")
    log_hike(client, world, ben, note="Fine", status=201)
    for n in range(2):
        _report(client, account(f"rep{n}"), "ben", trail_id=str(world["trail"]))
    page = client.get("/api/admin/moderation", headers=admin).json()
    assert page["queue_total"] == 2 and {i["author"]["username"] for i in page["items"]} == {"ana", "ben"}
    by_reports = client.get("/api/admin/moderation?sort=most_reported", headers=admin).json()["items"]
    assert by_reports[0]["author"]["username"] == "ben" and len(by_reports[0]["reports"]) == 2
    held = next(i for i in page["items"] if i["author"]["username"] == "ana")
    assert held["scores"][0] == {"category": "harassment", "score": 0.97} and held["text"] == "You idiot"
    assert held["context"] == "On Skyline Trail"


def test_only_admins_reach_the_queue(client, account, mod):
    ana = account("ana")
    for path in ("/api/admin/moderation",):
        assert client.get(path, headers=ana.headers).status_code == 403
    item = uuid.uuid4()
    assert client.post(f"/api/admin/moderation/{item}/approve", headers=ana.headers).status_code == 403
    assert client.post(f"/api/admin/moderation/users/{ana.id}/ban", json={"reason": "x"},
                       headers=ana.headers).status_code == 403


def test_approve_restores_and_is_audited(client, world, account, mod, admin, session_factory):  # noqa: F811
    ana = _held_note(client, world, account, mod)
    [item] = items(session_factory, kind="hike_note")
    assert client.post(f"/api/admin/moderation/{item.id}/approve", headers=admin).status_code == 200
    assert listed_note(client, world) == "You idiot"
    [item] = items(session_factory, kind="hike_note")
    assert item.state == "visible" and not item.in_queue and item.decision == "approved"
    assert client.get("/api/me/hike-logs", headers=ana.headers).json()[0]["review"] is None
    assert _audits(session_factory) == [("approve_item", ana.id)]


def test_hide_emails_the_author_with_reason_and_appeal(client, world, account, mod, admin, session_factory):  # noqa: F811
    ana = account("ana")
    log_hike(client, world, ana, note="Borderline", status=201)
    for n in range(2):
        _report(client, account(f"rep{n}"), "ana", trail_id=str(world["trail"]))
    [item] = items(session_factory, kind="hike_note")
    response = client.post(f"/api/admin/moderation/{item.id}/hide", json={"reason": "Personal attack"},
                           headers=admin)
    assert response.status_code == 200 and "emailed" in response.json()["message"]
    assert listed_note(client, world) is None
    [email] = mod.author_outbox.sent
    assert email.to == "ana@example.com" and "Personal attack" in email.text
    assert config.APPEAL_EMAIL in email.text and "rep0" not in email.text  # never who reported
    assert client.get("/api/me/hike-logs", headers=ana.headers).json()[0]["review"] == "hidden"
    db = session_factory()
    assert all(r.status == "resolved" for r in db.scalars(select(ProfileReport)))
    db.close()
    assert _audits(session_factory) == [("hide_item", ana.id)]
    # Editing it afterwards holds the new text for review, whatever the check says.
    again = log_hike(client, world, ana, note="Totally new words", status=200).json()
    assert again["review"] == "pending"
    assert items(session_factory, kind="hike_note")[0].queue_reason == "edited_after_hide"


def test_warn_suspend_ban_and_unlock(client, world, account, mod, admin, session_factory):  # noqa: F811
    ana = account("ana")
    base = f"/api/admin/moderation/users/{ana.id}"
    assert client.post(f"{base}/warn", json={"reason": "Be kind"}, headers=admin).status_code == 200
    assert "Be kind" in mod.author_outbox.sent[-1].text and config.APPEAL_EMAIL in mod.author_outbox.sent[-1].text

    assert client.post(f"{base}/suspend", json={"reason": "Spam", "days": 3}, headers=admin).status_code == 200
    assert ("suspend", ana.id, 3) in mod.supabase.calls
    refused = log_hike(client, world, ana, note="hi")
    assert refused.status_code == 403 and "suspended" in refused.text

    assert client.post(f"{base}/unlock", headers=admin).status_code == 200
    log_hike(client, world, ana, note="hi", status=201)

    assert client.post(f"{base}/ban", json={"reason": "Repeat spam"}, headers=admin).status_code == 200
    assert ("ban", ana.id) in mod.supabase.calls
    assert log_hike(client, world, ana, note="again").status_code == 403
    assert [a for a, _ in _audits(session_factory)] == ["warn_user", "suspend_user", "unsuspend_user", "ban_user"]


def test_a_failed_supabase_call_changes_nothing(client, account, mod, admin, session_factory):
    ana = account("ana")
    mod.supabase.fail = True
    response = client.post(f"/api/admin/moderation/users/{ana.id}/suspend", json={"reason": "x", "days": 1},
                           headers=admin)
    assert response.status_code == 502
    assert column_or_none(session_factory, ana.id) is None and _audits(session_factory) == []


def column_or_none(session_factory, user_id):
    db = session_factory()
    row = db.get(AccountRestriction, user_id)
    db.close()
    return row


def test_admins_cant_moderate_themselves(client, admin, mod, make_token, monkeypatch):
    admin_id = uuid.UUID(str(__import__("os").environ["ADMIN_USER_IDS"]))
    response = client.post(f"/api/admin/moderation/users/{admin_id}/ban", json={"reason": "x"}, headers=admin)
    assert response.status_code == 422


# ------------------------------------------------------------ account deletion


def test_deleting_an_account_clears_its_moderation_records(client, world, account, mod, session_factory):  # noqa: F811
    mod.screener.flag = {"idiot": ["harassment"]}
    ana = account("ana")
    log_hike(client, world, ana, note="idiot", status=201)
    assert items(session_factory, author_id=ana.id)
    deleted = client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=ana.headers)
    assert deleted.status_code == 204, deleted.text
    assert items(session_factory, author_id=ana.id) == []


def test_a_locked_account_cant_delete_itself_and_keeps_the_evidence(client, world, account, mod, session_factory):  # noqa: F811
    ana = account("ana")
    bad = photo_name()
    mod.screener.flag = {f"{ana.id}/{bad}": ["sexual/minors"]}
    log_hike(client, world, ana, photo=bad, status=201)
    refused = client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=ana.headers)
    assert refused.status_code == 403 and "locked" in refused.text
    assert items(session_factory, author_id=ana.id, child_safety=True)


def test_the_overview_counts_the_queue(client, world, account, mod, admin):  # noqa: F811
    mod.screener.flag = {"idiot": ["harassment"]}
    log_hike(client, world, account("ana"), note="idiot", status=201)
    assert client.get("/api/admin/overview", headers=admin).json()["moderation_queue"] == 1
