"""The Activity feed through the API: who appears (opt-in, public profile,
section switches, hidden dates), that trip plans and future dates never do,
high fives (one per user), deleting, admin hides (audited) and reports.

Row-level security for the same rule is tested against the local stack in
test_activity_policies.py.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.main import app
from app.models.activity import ActivityPost, ActivityReaction
from app.models.admin import AdminAuditLog
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileReport
from app.models.trail import Trail
from app.routers.availability import get_today
from app.routers.public_profiles import get_email_sender
from tests.test_availability import fetch, world  # noqa: F401  (fixtures)
from tests.test_public_profiles import Outbox

TODAY = date(2026, 10, 15)
ADMIN = uuid.UUID("aaaaaaaa-0000-4000-8000-0000000000ad")


@pytest.fixture(autouse=True)
def fixed_today():
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


@pytest.fixture
def outbox():
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def trails(world, session_factory):  # noqa: F811
    """The world's Skyline Trail plus five more, all moderate."""
    db = session_factory()
    ids = [world["trail"]]
    for n in range(5):
        trail = Trail(name=f"Extra Trail {n}", region=f"Park {n}, BC", country_code="CA", province_code="BC",
                      terrain_difficulty="easy")
        db.add(trail)
        db.flush()
        ids.append(trail.id)
    db.commit()
    db.close()
    return ids


@pytest.fixture
def person(client, make_token):
    """A user with a username, sharing their activity unless told otherwise."""

    def _make(username, *, share=True, province=None, **privacy):
        user_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {make_token(user_id, email=f'{username}@example.com')}"}
        profile = {"username": username, "display_name": username.title()}
        if province:
            profile["home_province"] = province
        assert client.patch("/api/me/profile", json=profile, headers=headers).status_code == 200
        response = client.patch("/api/me/privacy", json={"share_activity": share, **privacy}, headers=headers)
        assert response.status_code == 200, response.text
        return {"id": user_id, "headers": headers, "username": username}

    return _make


def log(client, who, trail_id, *, hiked_on="2026-08-14", share=True, note=None, photo=False, expect=None):
    body = {"hiked_on": hiked_on, "note": note}
    if share is not None:
        body["share"] = share
    if photo:
        body["photo_path"] = f"{who['id']}/{uuid.uuid4()}.webp"
    response = client.put(f"/api/me/hike-logs/{trail_id}", json=body, headers=who["headers"])
    if expect:
        assert response.status_code == expect, response.text
        return response.json()
    assert response.status_code in (200, 201), response.text
    return response.json()


def feed(client, headers=None, **params):
    response = client.get("/api/activity", params=params, headers=headers or {})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def flat(body):
    """Every post, with the milestones and ranks folded into hike posts as
    posts of their own (same author), for checks that don't care which."""
    out = []
    for item in body["items"]:
        out.append(item)
        for earned in item.get("earned", []):
            out.append({**earned, "author": item["author"], "folded": True})
    return out


def kinds(body, username=None):
    return [(item["author"]["username"], item["kind"]) for item in flat(body)
            if username is None or item["author"]["username"] == username]


def milestone_ids(body):
    return [item["milestone"]["id"] for item in flat(body) if item["kind"] == "milestone"]


def ranks(body):
    return [item["rank"] for item in flat(body) if item["kind"] == "rank"]


def hike_posts(body):
    return [item for item in body["items"] if item["kind"] == "hike"]


def set_privacy(client, who, **changes):
    assert client.patch("/api/me/privacy", json=changes, headers=who["headers"]).status_code == 200


# ------------------------------------------------------------- the setting


def test_sharing_is_off_by_default(client, make_token):
    headers = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    assert client.get("/api/me/privacy", headers=headers).json()["share_activity"] is False


def test_the_feed_starts_empty_for_guests(client):
    assert feed(client) == {"items": [], "next_cursor": None, "province": None, "follows_anyone": False}


def test_a_shared_hike_posts_with_its_milestones(client, trails, person):
    alice = person("alice")
    saved = log(client, alice, trails[0], note="Larches!", photo=True)
    assert saved["shared"] is True

    body = feed(client)
    hikes = hike_posts(body)
    assert len(hikes) == 1
    post = hikes[0]
    assert post["author"] == {"username": "alice", "display_name": "Alice", "avatar_path": None, "follow": None}
    assert post["hike"]["trail"]["name"] == "Skyline Trail"
    assert post["hike"]["hiked_on"] == "2026-08-14"
    assert post["hike"]["note"] == "Larches!"
    assert post["hike"]["photo_path"] == saved["photo_path"]
    assert post["posted_at"] is not None
    assert post["high_fives"] == 0 and post["high_fived"] is False and post["mine"] is False
    # The first hike earns "First steps", posted alongside it.
    milestones = milestone_ids(body)
    assert "first-hike" in milestones
    # Only declared fields: no user id or email anywhere.
    text = str(body).replace(saved["photo_path"], "")
    assert str(alice["id"]) not in text and "@example.com" not in text


def test_a_rank_post_when_a_hike_reaches_a_new_rank(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id)
    reached = ranks(feed(client))
    assert reached and all(rank["level"] > 1 for rank in reached)
    assert len({rank["level"] for rank in reached}) == len(reached)  # one post per rank


def test_unticked_hikes_dont_post(client, trails, person):
    alice = person("alice")
    assert log(client, alice, trails[0], share=False)["shared"] is False
    assert log(client, alice, trails[1], share=None)["shared"] is False  # older clients
    assert feed(client)["items"] == []


def test_undated_past_hikes_never_post(client, trails, person):
    alice = person("alice")
    response = client.post("/api/me/hike-logs/past", json={"trail_ids": [str(t) for t in trails]},
                           headers=alice["headers"])
    assert response.status_code == 201
    assert feed(client)["items"] == []


def test_onboarding_hikes_and_what_they_earned_never_post(client, trails, person, session_factory):
    """Hikes from /welcome's "Which of these have you hiked?" post nothing, and a
    later shared hike posts only what that hike adds, never the milestones or
    rank the onboarding hikes had already earned."""
    from app.activity import standing

    alice = person("alice")
    response = client.post("/api/me/hike-logs/past", json={"trail_ids": [str(t) for t in trails[1:]]},
                           headers=alice["headers"])
    assert response.status_code == 201
    assert feed(client)["items"] == []
    db = session_factory()
    earned = standing(db, alice["id"])
    db.close()
    assert "first-hike" in earned.milestones  # the onboarding hikes did earn things

    log(client, alice, trails[0], hiked_on="2026-07-01")
    body = feed(client)
    assert [item["hike"]["trail"]["name"] for item in hike_posts(body)] == ["Skyline Trail"]
    posted = set(milestone_ids(body))
    assert posted and not posted & earned.milestones  # e.g. Canada Day, never First steps
    assert all(rank["level"] > earned.rank_level for rank in ranks(body))


def test_nothing_posts_while_they_cant_share(client, trails, person):
    """Ticking the box without the setting doesn't leave a post waiting to appear."""
    alice = person("alice", share=False)
    log(client, alice, trails[0])
    set_privacy(client, alice, share_activity=True)
    assert feed(client)["items"] == []


# ------------------------------------------------- who appears, immediately


@pytest.mark.parametrize(
    "change",
    [{"share_activity": False}, {"is_private": True}, {"show_journal": False}],
    ids=["share-off", "private", "journal-hidden"],
)
def test_turning_a_setting_off_hides_their_posts_right_away(client, trails, person, change):
    alice = person("alice")
    bob = person("bob")
    log(client, alice, trails[0])
    log(client, bob, trails[1])
    assert {"alice", "bob"} == {u for u, _ in kinds(feed(client))}

    set_privacy(client, alice, **change)
    # A hidden journal leaves rank posts to the rank switch (next test).
    shown = {u for u, k in kinds(feed(client)) if "show_journal" not in change or k != "rank"}
    assert shown == {"bob"}

    set_privacy(client, alice, **{key: not value for key, value in change.items()})
    assert {"alice", "bob"} == {u for u, _ in kinds(feed(client))}


def test_hiding_the_rank_hides_only_rank_posts(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id)
    assert "rank" in {k for _, k in kinds(feed(client))}
    set_privacy(client, alice, show_rank=False)
    remaining = {k for _, k in kinds(feed(client))}
    assert "rank" not in remaining and "hike" in remaining


def test_no_username_or_admin_hidden_profile_means_no_posts(client, trails, person, session_factory):
    alice = person("alice")
    bob = person("bob")
    log(client, alice, trails[0])
    log(client, bob, trails[1])
    db = session_factory()
    db.add(ProfileModeration(user_id=bob["id"]))
    from app.models.account import Profile
    db.get(Profile, alice["id"]).username = None
    db.commit()
    db.close()
    assert feed(client)["items"] == []


def test_hidden_dates_hide_the_date_and_seasonal_milestones(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-07-01")  # Canada Day
    body = feed(client)
    assert "canada-day" in milestone_ids(body)

    set_privacy(client, alice, hide_hike_dates=True)
    body = feed(client)
    assert hike_posts(body)[0]["hike"]["hiked_on"] is None
    assert all(item["posted_at"] is None for item in body["items"])
    milestones = milestone_ids(body)
    assert "canada-day" not in milestones and "first-hike" in milestones
    assert all(i["milestone"]["earned_on"] is None for i in flat(body) if i["kind"] == "milestone")


def test_milestone_posts_carry_their_card_details(client, trails, person):
    """How it's earned and the day, for the badge's details card."""
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-08-14")
    post = next(i for i in flat(feed(client)) if i["kind"] == "milestone" and i["milestone"]["id"] == "first-hike")
    badge = post["milestone"]
    assert badge["detail"] and badge["tier"] == "bronze" and badge["secret"] is False
    assert badge["earned_on"] == "2026-08-14" and badge["earned_with"] is None

    # A hike logged later but dated earlier moves the day back, as in their journal.
    log(client, alice, trails[1], hiked_on="2026-06-01", share=False)
    post = next(i for i in flat(feed(client)) if i["kind"] == "milestone" and i["milestone"]["id"] == "first-hike")
    assert post["milestone"]["earned_on"] == "2026-06-01"


def test_an_undated_hike_shared_from_the_dialog_shows_no_date(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on=None)
    assert hike_posts(feed(client))[0]["hike"]["hiked_on"] is None


# --------------------------------------------- never plans or future dates


def test_future_dates_are_refused_and_never_shown(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-12-01", expect=422)
    log(client, alice, trails[0], hiked_on="2026-10-15")
    assert len(hike_posts(feed(client))) == 1

    # A browser can edit its own hike_logs row directly; the feed re-checks.
    db = session_factory()
    db.scalar(select(HikeLog).where(HikeLog.user_id == alice["id"])).hiked_on = date(2027, 6, 1)
    db.commit()
    db.close()
    assert hike_posts(feed(client)) == []


def test_trip_plans_never_appear(client, trails, person, world, fetch):  # noqa: F811
    from tests.test_plans import plan_body

    alice = person("alice", show_trip_plans=True)
    response = client.post("/api/me/plans", json=plan_body(world, notes="gate code 4321"), headers=alice["headers"])
    assert response.status_code == 201, response.text
    log(client, alice, trails[1])
    body = feed(client)
    text = str(body)
    assert "Skyline with Sam" not in text and "2026-10-20" not in text and "gate code" not in text
    assert {item["kind"] for item in body["items"]} <= {"hike", "milestone", "rank"}
    assert all(item["milestone"]["category"] not in ("planning", "gear")
               for item in flat(body) if item["kind"] == "milestone")


def test_planning_milestones_are_never_shown(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0])
    db = session_factory()
    db.add(ActivityPost(user_id=alice["id"], kind="milestone", milestone="planner"))
    db.commit()
    db.close()
    assert "planner" not in str(feed(client))


# ------------------------------------------------------------- high fives


def high_five(client, who, post_id, method="put"):
    return getattr(client, method)(f"/api/activity/{post_id}/high-five", headers=who["headers"] if who else {})


def test_one_high_five_per_person_and_it_toggles_off(client, trails, person, session_factory):
    alice, bob, cara = person("alice"), person("bob"), person("cara")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]

    assert high_five(client, bob, post_id).json() == {"high_fives": 1, "high_fived": True}
    assert high_five(client, bob, post_id).json() == {"high_fives": 1, "high_fived": True}
    assert high_five(client, cara, post_id).json() == {"high_fives": 2, "high_fived": True}

    assert hike_posts(feed(client, bob["headers"]))[0]["high_fived"] is True
    assert hike_posts(feed(client))[0]["high_fives"] == 2
    assert hike_posts(feed(client, alice["headers"]))[0]["mine"] is True

    assert high_five(client, bob, post_id, "delete").json() == {"high_fives": 1, "high_fived": False}
    assert high_five(client, bob, post_id, "delete").json() == {"high_fives": 1, "high_fived": False}
    db = session_factory()
    assert db.scalars(select(ActivityReaction.user_id)).all() == [cara["id"]]
    db.close()


def test_guests_cant_high_five(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    assert high_five(client, None, post_id).status_code == 401


def test_hidden_posts_cant_be_high_fived(client, trails, person):
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    set_privacy(client, alice, share_activity=False)
    assert high_five(client, bob, post_id).status_code == 404
    assert high_five(client, bob, uuid.uuid4()).status_code == 404


# ------------------------------------------------------------------ delete


def test_owners_delete_their_posts_and_nobody_else_can(client, trails, person):
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    assert client.delete(f"/api/activity/{post_id}", headers=bob["headers"]).status_code == 404
    assert client.delete(f"/api/activity/{post_id}").status_code == 401
    assert client.delete(f"/api/activity/{post_id}", headers=alice["headers"]).status_code == 204
    assert hike_posts(feed(client)) == []
    # The hike itself stays, no longer shared.
    entries = client.get("/api/me/hike-logs", headers=alice["headers"]).json()
    assert len(entries) == 1 and entries[0]["shared"] is False


def test_deleting_a_hike_removes_its_posts(client, trails, person, session_factory):
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    high_five(client, bob, post_id)
    assert client.delete(f"/api/me/hike-logs/{trails[0]}", headers=alice["headers"]).status_code == 204
    # The hike's post and the milestones it earned all go, with their high fives.
    assert feed(client)["items"] == []
    db = session_factory()
    assert db.scalars(select(ActivityPost)).all() == []
    assert db.scalars(select(ActivityReaction)).all() == []
    db.close()


def test_unticking_share_removes_the_hike_post(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    assert log(client, alice, trails[0], share=False)["shared"] is False
    assert hike_posts(feed(client)) == []


# ------------------------------------------------------------- admin hide


@pytest.fixture
def admin(monkeypatch, make_token):
    monkeypatch.setenv("ADMIN_USER_IDS", str(ADMIN))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    return {"Authorization": f"Bearer {make_token(ADMIN)}"}


def test_admins_hide_and_unhide_posts_with_an_audit_trail(client, trails, person, admin, session_factory):
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]

    assert client.post(f"/api/admin/activity/{post_id}/hide", json={}, headers=bob["headers"]).status_code == 403
    response = client.post(f"/api/admin/activity/{post_id}/hide", json={"reason": "Spam"}, headers=admin)
    assert response.status_code == 200, response.text
    assert hike_posts(feed(client)) == []
    assert client.post(f"/api/admin/activity/{post_id}/hide", json={}, headers=admin).status_code == 409

    assert client.post(f"/api/admin/activity/{post_id}/unhide", headers=admin).status_code == 200
    assert len(hike_posts(feed(client))) == 1

    db = session_factory()
    rows = db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at)).all()
    assert [(r.action, r.target_user_id, r.details.get("post_id")) for r in rows] == [
        ("hide_post", alice["id"], post_id), ("unhide_post", alice["id"], post_id),
    ]
    assert rows[0].details["reason"] == "Spam"
    db.close()


# ----------------------------------------------------------------- reports


def report(client, who, username, **body):
    return client.post(f"/api/profiles/{username}/report", json={"reason": "spam", **body}, headers=who["headers"])


def test_reporting_a_post_uses_the_report_flow(client, trails, person, outbox, admin, session_factory):
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0], note="Buy my stuff")
    post_id = hike_posts(feed(client))[0]["id"]

    assert report(client, bob, "alice", post_id=post_id).status_code == 202
    assert "Activity post report" in outbox.sent[0].subject
    assert "Buy my stuff" in outbox.sent[0].text and "bob@example.com" not in outbox.sent[0].text
    db = session_factory()
    assert str(db.scalar(select(ProfileReport.post_id))) == post_id
    db.close()

    listed = client.get("/api/admin/reports", headers=admin).json()["items"][0]
    assert listed["kind"] == "post"
    assert listed["post"]["summary"] == "Hiked Skyline Trail" and listed["post"]["hidden"] is False


def test_only_visible_posts_of_that_profile_can_be_reported(client, trails, person, outbox):
    alice, bob, cara = person("alice"), person("bob"), person("cara")
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    # Not cara's post.
    assert report(client, bob, "cara", post_id=post_id).status_code == 404
    set_privacy(client, alice, share_activity=False)
    assert report(client, bob, "alice", post_id=post_id).status_code == 404
    assert outbox.sent == []


# ------------------------------------------------------ province and paging


def test_from_my_province_needs_the_author_to_show_theirs(client, trails, person):
    viewer = person("viewer", province="AB")
    shows = person("shows", province="AB", show_home_province=True)
    quiet = person("quiet", province="AB")  # same province, but it's hidden
    other = person("other", province="BC", show_home_province=True)
    for who, trail_id in ((shows, trails[0]), (quiet, trails[1]), (other, trails[2])):
        log(client, who, trail_id)

    body = feed(client, viewer["headers"], scope="province")
    assert body["province"] == "AB"
    assert {u for u, _ in kinds(body)} == {"shows"}
    assert {u for u, _ in kinds(feed(client, viewer["headers"]))} == {"shows", "quiet", "other"}
    # Guests and people without a province get nothing from the filter.
    assert feed(client, scope="province")["items"] == []


def test_newest_first_with_a_cursor(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id, share=True)
    everything = [item["id"] for item in feed(client, limit=50)["items"]]
    assert len(everything) == 6  # one card per hike; what each earned is folded in

    seen, cursor = [], None
    while True:
        page = feed(client, limit=4, **({"cursor": cursor} if cursor else {}))
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == everything
    names = [item["hike"]["trail"]["name"] for item in feed(client, limit=50)["items"] if item["kind"] == "hike"]
    assert names[0] == "Extra Trail 4" and names[-1] == "Skyline Trail"


def test_a_bad_cursor_is_422(client):
    assert client.get("/api/activity", params={"cursor": "nope"}).status_code == 422


# ------------------------------------------- folding, only-you, high-fivers


def test_what_a_hike_earned_folds_into_its_post(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    body = feed(client)
    assert [item["kind"] for item in body["items"]] == ["hike"]
    earned = body["items"][0]["earned"]
    assert {"kind": "milestone"}.items() <= earned[0].items()
    assert "first-hike" in [e["milestone"]["id"] for e in earned if e["kind"] == "milestone"]


def test_ranks_fold_in_after_the_milestones(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id)
    for item in feed(client, limit=50)["items"]:
        assert item["kind"] == "hike"
        kinds_in = [e["kind"] for e in item["earned"]]
        assert kinds_in == sorted(kinds_in, key=lambda k: k == "rank")


def test_earned_stands_alone_once_the_hike_post_is_unshared(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    log(client, alice, trails[0], share=False)  # the hike leaves the feed; the badge stays earned
    body = feed(client)
    assert body["items"] and {i["kind"] for i in body["items"]} <= {"milestone", "rank"}
    assert all(item["earned"] == [] for item in body["items"])


def test_a_hidden_journal_leaves_the_rank_standing_alone(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id)
    set_privacy(client, alice, show_journal=False)
    items = feed(client, limit=50)["items"]
    assert items and all(item["kind"] == "rank" for item in items)


def test_a_hidden_rank_stays_out_of_the_folded_list(client, trails, person):
    alice = person("alice")
    for trail_id in trails:
        log(client, alice, trail_id)
    set_privacy(client, alice, show_rank=False)
    assert ranks(feed(client, limit=50)) == []


def test_deleting_a_hike_post_takes_its_badges_along(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0])
    post = feed(client)["items"][0]
    assert post["earned"]
    assert client.delete(f"/api/activity/{post['id']}", headers=alice["headers"]).status_code == 204
    assert feed(client)["items"] == []
    db = session_factory()
    assert db.scalars(select(ActivityPost)).all() == []
    db.close()
    # The milestones themselves stay earned.
    earned = client.get("/api/me/milestones", headers=alice["headers"]).json()["milestones"]
    assert any(m["id"] == "first-hike" and m["earned"] for m in earned)


@pytest.mark.parametrize(
    "change",
    [{"share_activity": False}, {"is_private": True}, {"show_journal": False}],
    ids=["share-off", "private", "journal-hidden"],
)
def test_your_unshared_posts_show_only_to_you(client, trails, person, change):
    """The privacy check: with sharing off, a guest and another signed-in user
    see nothing of alice's; alice sees her own, marked only_you."""
    alice, bob = person("alice"), person("bob")
    log(client, alice, trails[0])
    set_privacy(client, alice, **change)

    # A hidden journal leaves rank posts to the rank switch, as before.
    def public(body):
        return [k for _, k in kinds(body) if "show_journal" not in change or k != "rank"]
    assert public(feed(client)) == []
    assert public(feed(client, bob["headers"])) == []
    own = feed(client, alice["headers"])["items"]
    assert [item["kind"] for item in own] == ["hike"]
    assert own[0]["mine"] is True and own[0]["only_you"] is True
    assert own[0]["earned"]  # still folded in for her
    # Nobody can high five it or list its high fives.
    assert high_five(client, bob, own[0]["id"]).status_code == 404
    assert client.get(f"/api/activity/{own[0]['id']}/high-fives", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/activity/{own[0]['id']}/high-fives", headers=alice["headers"]).status_code == 200

    set_privacy(client, alice, **{key: not value for key, value in change.items()})
    shown = feed(client, alice["headers"])["items"]
    assert shown[0]["only_you"] is False and shown[0]["mine"] is True


def test_admin_hidden_posts_stay_hidden_from_their_owner_too(client, trails, person, session_factory):
    from datetime import datetime, timezone
    alice = person("alice")
    log(client, alice, trails[0])
    db = session_factory()
    for post in db.scalars(select(ActivityPost)):
        post.hidden_at = datetime.now(timezone.utc)
    db.commit()
    db.close()
    assert feed(client, alice["headers"])["items"] == []


def test_who_high_fived_lists_public_profiles_only(client, trails, person):
    alice = person("alice")
    bob = person("bob", share=False)
    carol = person("carol", share=False, is_private=True)
    log(client, alice, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    for who in (bob, carol):
        assert high_five(client, who, post_id).status_code == 200

    response = client.get(f"/api/activity/{post_id}/high-fives")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["high_fives"] == 2 and body["others"] == 1
    assert body["hikers"] == [{"username": "bob", "display_name": "Bob", "avatar_path": None}]
    assert str(carol["id"]) not in response.text and "@example.com" not in response.text
    assert client.get(f"/api/activity/{uuid.uuid4()}/high-fives").status_code == 404


def test_trending_counts_this_weeks_logs_and_saves(client, trails, person, session_factory):
    from datetime import datetime, timedelta, timezone
    from app.models.account import SavedTrail
    db = session_factory()
    for n, trail_id in enumerate(trails):
        trail = db.get(Trail, trail_id)
        trail.popularity_rank = n + 1
    old = datetime.now(timezone.utc) - timedelta(days=30)
    a, b = uuid.uuid4(), uuid.uuid4()
    db.add_all([
        SavedTrail(user_id=a, trail_id=trails[3]),
        SavedTrail(user_id=b, trail_id=trails[3]),
        SavedTrail(user_id=a, trail_id=trails[5]),
        SavedTrail(user_id=b, trail_id=trails[1], created_at=old),  # last month: doesn't count
    ])
    db.commit()
    db.close()
    alice = person("alice", share=False)
    log(client, alice, trails[5], hiked_on="2026-10-01")

    response = client.get("/api/activity/trending")
    assert response.status_code == 200
    rows = response.json()["trails"]
    assert len(rows) == 5
    week = [row["trail"]["id"] for row in rows if row["this_week"]]
    assert week == [str(trails[3]), str(trails[5])]  # two saves; a save and a log, then by popularity
    # Topped up with the most popular trails, never repeating one.
    assert [row["trail"]["id"] for row in rows if not row["this_week"]] == [str(t) for t in trails[:3]]
    assert "alice" not in response.text
