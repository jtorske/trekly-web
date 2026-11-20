"""Editing an Activity post (its hike, through the journal's own PUT), the
"Edited" mark, moderation of edits, badges recalculated after a date change,
who high-fived (blocks, private profiles, follow state), and the owner's
high-five summary.
"""

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.main import app
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.models.social import Block
from app.moderation import get_moderation_services
from tests.moderation_fakes import FakeScreener, Outbox, fake_services
from tests.test_activity import feed, hike_posts, log, milestone_ids, person, set_privacy, trails  # noqa: F401
from tests.test_availability import world  # noqa: F401  (fixture)
from tests.test_follows import approve, follow


@pytest.fixture
def mod():
    fakes = SimpleNamespace(screener=FakeScreener(flag={"nastyword": ["harassment"]}), outbox=Outbox())
    app.dependency_overrides[get_moderation_services] = lambda: fake_services(
        screener=fakes.screener, outbox=fakes.outbox)
    yield fakes
    app.dependency_overrides.pop(get_moderation_services, None)


@pytest.fixture
def ana(person):  # noqa: F811
    return person("ana")


@pytest.fixture
def ben(person):  # noqa: F811
    return person("ben")


@pytest.fixture
def cam(person):  # noqa: F811
    return person("cam")


def edit(client, who, trail_id, *, hiked_on="2026-08-14", note=None, photo_path=None, expect=200):
    """What the "Edit post" dialog sends: no `share`, so sharing stays as it is."""
    body = {"hiked_on": hiked_on, "note": note, "photo_path": photo_path}
    response = client.put(f"/api/me/hike-logs/{trail_id}", json=body, headers=who["headers"])
    assert response.status_code == expect, response.text
    return response.json()


def the_post(client, headers=None):
    return hike_posts(feed(client, headers))[0]


def block(session_factory, blocker, blocked):
    db = session_factory()
    db.add(Block(blocker_id=blocker["id"], blocked_id=blocked["id"]))
    db.commit()
    db.close()


# ------------------------------------------------------------ editing


def test_editing_the_note_marks_the_post_edited(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0], note="Frist try")
    post = the_post(client)
    assert post["edited"] is False and post["edited_at"] is None
    edit(client, ana, trails[0], note="First try")
    post = the_post(client)
    assert post["hike"]["note"] == "First try"
    assert post["edited"] is True and post["edited_at"] is not None
    # Still shared, and still the same post.
    assert post["id"] == hike_posts(feed(client, ana["headers"]))[0]["id"]


def test_saving_without_changes_isnt_an_edit(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0], note="Same")
    edit(client, ana, trails[0], note="Same")
    assert the_post(client)["edited"] is False


def test_photos_can_be_added_replaced_and_removed(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0])
    first = f"{ana['id']}/{uuid.uuid4()}.webp"
    edit(client, ana, trails[0], photo_path=first)
    assert the_post(client)["hike"]["photo_path"] == first
    second = f"{ana['id']}/{uuid.uuid4()}.webp"
    edit(client, ana, trails[0], photo_path=second)
    assert the_post(client)["hike"]["photo_path"] == second
    edit(client, ana, trails[0], photo_path=None)
    assert the_post(client)["hike"]["photo_path"] is None
    # Someone else's photo folder is refused.
    edit(client, ana, trails[0], photo_path=f"{uuid.uuid4()}/{uuid.uuid4()}.webp", expect=422)


def test_an_edit_can_forget_the_date(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0])
    saved = edit(client, ana, trails[0], hiked_on=None)
    assert saved["hiked_on"] is None
    post = the_post(client)
    assert post["hike"]["hiked_on"] is None and post["edited"] is True


def test_only_the_author_edits_their_post(client, trails, ana, ben, mod):  # noqa: F811
    log(client, ana, trails[0], note="Ana's note")
    # The journal is keyed to the signed-in user: Ben's PUT makes his own entry
    # (unshared, since he didn't ask to share), never touches Ana's.
    edit(client, ben, trails[0], note="Ben's words", expect=201)
    posts = hike_posts(feed(client))
    assert [(p["author"]["username"], p["hike"]["note"], p["edited"]) for p in posts] == [("ana", "Ana's note", False)]


def test_a_flagged_edit_is_held_like_a_new_post(client, trails, ana, ben, mod):  # noqa: F811
    log(client, ana, trails[0], note="Lovely day")
    saved = edit(client, ana, trails[0], note="Lovely nastyword day")
    assert saved["review"] == "pending" and saved["note"] == "Lovely nastyword day"
    # Others see the post without the held note; Ana sees it with "being reviewed".
    assert the_post(client)["hike"]["note"] is None
    mine = hike_posts(feed(client, ana["headers"]))[0]
    assert mine["hike"]["note"] == "Lovely nastyword day" and mine["review"] == "pending"
    assert mine["edited"] is True


def test_changing_the_date_recalculates_badges(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0], hiked_on="2026-08-14")
    assert "canada-day" not in milestone_ids(feed(client))
    saved = edit(client, ana, trails[0], hiked_on="2026-07-01")
    # The edit re-evaluated the journal…
    assert saved["progress"] is not None
    assert "canada-day" in [m["id"] for m in saved["progress"]["new_milestones"]]
    # …and the post now carries the badge, folded into the hike.
    post = the_post(client)
    assert "canada-day" in [e["milestone"]["id"] for e in post["earned"] if e["kind"] == "milestone"]
    milestones = client.get("/api/me/milestones", headers=ana["headers"]).json()
    earned = {m["id"] for m in milestones["milestones"] if m["earned"]}
    assert "canada-day" in earned
    # Moving it back takes the badge (and its post) away again.
    edit(client, ana, trails[0], hiked_on="2026-08-14")
    assert "canada-day" not in milestone_ids(feed(client))
    assert "canada-day" not in milestone_ids(feed(client, ana["headers"]))


def test_a_badge_earned_by_editing_an_unshared_hike_stays_private(client, trails, ana, session_factory, mod):  # noqa: F811
    log(client, ana, trails[0], share=False)
    client.get("/api/me/activity", headers=ana["headers"])  # its owner-only post
    edit(client, ana, trails[0], hiked_on="2026-07-01")
    assert milestone_ids(feed(client)) == []
    db = session_factory()
    badge = db.scalar(select(ActivityPost).where(ActivityPost.milestone == "canada-day"))
    assert badge is not None and badge.owner_only
    db.close()


def test_changing_a_verified_hikes_date_drops_the_check(client, trails, ana, session_factory, mod):  # noqa: F811
    log(client, ana, trails[0])
    db = session_factory()
    entry = db.scalar(select(HikeLog).where(HikeLog.user_id == ana["id"]))
    entry.verified, entry.match_score = True, 0.9
    db.commit()
    db.close()
    assert the_post(client)["hike"]["verified"] is True
    edit(client, ana, trails[0], note="Just a note")
    assert the_post(client)["hike"]["verified"] is True  # a note doesn't touch it
    edit(client, ana, trails[0], hiked_on="2026-08-13", note="Just a note")
    assert the_post(client)["hike"]["verified"] is False


def test_the_edit_time_hides_with_the_dates(client, trails, ana, mod):  # noqa: F811
    log(client, ana, trails[0])
    edit(client, ana, trails[0], note="Changed")
    set_privacy(client, ana, hide_hike_dates=True)
    post = the_post(client)
    assert post["edited"] is True and post["edited_at"] is None


def test_admins_cant_edit_only_hide(client, trails, ana, make_token, monkeypatch, mod):  # noqa: F811
    log(client, ana, trails[0], note="Original")
    admin_id = uuid.uuid4()
    monkeypatch.setenv("ADMIN_USER_IDS", str(admin_id))
    admin = {"Authorization": f"Bearer {make_token(admin_id)}"}
    # No route edits someone else's hike: an admin's PUT is about their own journal.
    client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-14", "note": "Admin's"},
               headers=admin)
    assert the_post(client)["hike"]["note"] == "Original"


# ------------------------------------------------------------ who high-fived


def high_five(client, who, post_id):
    assert client.put(f"/api/activity/{post_id}/high-five", headers=who["headers"]).status_code == 200


def fivers(client, post_id, who=None, expect=200):
    response = client.get(f"/api/activity/{post_id}/high-fives", headers=who["headers"] if who else {})
    assert response.status_code == expect, response.text
    return response.json()


def test_who_high_fived_respects_private_profiles_follows_and_blocks(client, trails, session_factory, person, mod):  # noqa: F811
    ana, ben, cam, dee, eve = (person(n) for n in ("ana", "ben", "cam", "dee", "eve"))
    log(client, ana, trails[0])
    post_id = the_post(client)["id"]
    for who in (ben, cam, dee, eve):
        high_five(client, who, post_id)
    set_privacy(client, cam, is_private=True)
    block(session_factory, dee, eve)  # Dee blocked Eve

    # Ana: everyone public by name, with follow buttons; private Cam is a count.
    body = fivers(client, post_id, ana)
    assert body["high_fives"] == 4
    assert [h["username"] for h in body["hikers"]] == ["eve", "dee", "ben"]
    assert all(h["follow"] == "none" for h in body["hikers"])
    assert body["others"] == 1
    # Eve doesn't see Dee (blocked either way), but does see herself, with no button.
    body = fivers(client, post_id, eve)
    assert [h["username"] for h in body["hikers"]] == ["eve", "ben"]
    assert body["hikers"][0]["follow"] is None
    assert body["others"] == 2
    # Ana follows Cam (approved): now Cam shows to her by name.
    follow(client, ana, cam)
    approve(client, cam, ana)
    body = fivers(client, post_id, ana)
    assert "cam" in [h["username"] for h in body["hikers"]] and body["others"] == 0
    cam_row = next(h for h in body["hikers"] if h["username"] == "cam")
    assert cam_row["is_private"] is True and cam_row["follow"] == "following"
    # Guests: public profiles only.
    assert [h["username"] for h in fivers(client, post_id)["hikers"]] == ["eve", "dee", "ben"]


def test_a_blocked_reader_cant_see_who_high_fived(client, trails, session_factory, ana, ben, mod):  # noqa: F811
    log(client, ana, trails[0])
    post_id = the_post(client)["id"]
    block(session_factory, ana, ben)
    fivers(client, post_id, ben, expect=404)


def test_authors_see_their_counts_and_cant_high_five_themselves(client, trails, ana, ben, mod):  # noqa: F811
    log(client, ana, trails[0])
    mine = hike_posts(feed(client, ana["headers"]))[0]
    assert mine["mine"] is True and mine["high_fives"] == 0
    # Their own list works at zero.
    assert fivers(client, mine["id"], ana) == {"high_fives": 0, "hikers": [], "others": 0}


# ------------------------------------------------------------ the owner's summary


def test_the_owners_summary_and_visitors_dont_get_one(client, trails, ana, ben, cam, mod):  # noqa: F811
    log(client, ana, trails[0])
    log(client, ana, trails[1])
    first, second = sorted(hike_posts(feed(client)), key=lambda p: p["hike"]["trail"]["id"] != str(trails[0]))
    page = client.get("/api/me/activity", headers=ana["headers"]).json()
    assert page["summary"] == {"high_fives": 0, "top_post": None}
    high_five(client, ben, second["id"])
    high_five(client, cam, second["id"])
    high_five(client, ben, first["id"])
    page = client.get("/api/me/activity", headers=ana["headers"]).json()
    assert page["summary"]["high_fives"] == 3
    assert page["summary"]["top_post"]["id"] == second["id"]
    assert page["summary"]["top_post"]["high_fives"] == 2
    assert page["summary"]["top_post"]["title"] == second["hike"]["trail"]["name"]
    visitor = client.get("/api/profiles/ana/activity", headers=ben["headers"]).json()
    assert visitor.get("summary") is None
