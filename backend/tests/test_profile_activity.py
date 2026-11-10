"""A profile's Activity tab: who sees it, and what.

- The owner (GET /api/me/activity) sees every post of theirs, whether or
  not it shows to anyone else (marked only_you), and is told whether it does.
- Visitors (GET /api/profiles/{username}/activity, and activity_count on the
  profile) get the tab only while the profile is public and "Share my
  activity in the feed" is on, and then only the posts the feed would show,
  under the feed's rules: hidden dates stay hidden, and so do seasonal
  milestones.
- What a hike earned is folded into that hike's card, as in the feed.
"""

import uuid

from sqlalchemy import select

from app.models.activity import ActivityPost
from app.models.privacy import ProfileModeration
from tests.test_activity import (  # noqa: F401  (fixtures)
    feed,
    fixed_today,
    log,
    person,
    set_privacy,
    trails,
)
from tests.test_availability import fetch, world  # noqa: F401  (fixtures)


def mine(client, who, **params):
    response = client.get("/api/me/activity", params=params, headers=who["headers"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def visit(client, username, headers=None, expect=200, **params):
    response = client.get(f"/api/profiles/{username}/activity", params=params, headers=headers or {})
    assert response.status_code == expect, response.text
    return response.json()


def profile_count(client, username):
    response = client.get(f"/api/profiles/{username}")
    assert response.status_code == 200, response.text
    return response.json()["activity_count"]


def kinds(body):
    return [item["kind"] for item in body["items"]]


def folded(body):
    """Milestones folded into hike cards."""
    return [e["milestone"]["id"] for item in body["items"] for e in item["earned"] if e["kind"] == "milestone"]


# ------------------------------------------------------------------- owner


def test_the_owner_needs_to_sign_in(client):
    assert client.get("/api/me/activity").status_code in (401, 403)


def test_the_owner_sees_their_posts_newest_first_with_milestones_folded_in(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-08-14", note="Larches!")
    log(client, alice, trails[1], hiked_on="2026-08-20")

    body = mine(client, alice)
    hikes = [item for item in body["items"] if item["kind"] == "hike"]
    assert [h["hike"]["trail"]["id"] for h in hikes] == [str(trails[1]), str(trails[0])]
    assert body["sharing"] is True and body["total"] == len(body["items"])
    assert all(item["mine"] and not item["only_you"] for item in body["items"])
    # "First steps" belongs to the first hike's card, not a card of its own.
    first = hikes[-1]
    assert "first-hike" in [e["milestone"]["id"] for e in first["earned"] if e["kind"] == "milestone"]
    assert "milestone" not in kinds(body) or "first-hike" not in [
        item["milestone"]["id"] for item in body["items"] if item["kind"] == "milestone"
    ]


def test_with_sharing_off_the_owner_still_sees_everything(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    before = mine(client, alice)
    set_privacy(client, alice, share_activity=False)

    body = mine(client, alice)
    assert body["sharing"] is False
    assert [item["id"] for item in body["items"]] == [item["id"] for item in before["items"]]
    assert all(item["only_you"] for item in body["items"])
    assert body["total"] == before["total"] > 0


def test_a_private_or_journal_hidden_owner_is_told_nothing_shows(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0])
    set_privacy(client, alice, show_journal=False)
    assert mine(client, alice)["sharing"] is False
    set_privacy(client, alice, show_journal=True, is_private=True)
    body = mine(client, alice)
    assert body["sharing"] is False and body["items"]


def test_hidden_dates_apply_to_the_owners_cards_too(client, trails, person):
    """As in the feed: the owner's cards show what their settings show."""
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-07-01")  # Canada Day
    set_privacy(client, alice, hide_hike_dates=True)

    body = mine(client, alice)
    hike = next(item for item in body["items"] if item["kind"] == "hike")
    assert hike["hike"]["hiked_on"] is None and hike["posted_at"] is None
    assert "first-hike" in folded(body)


def test_the_owner_pages_with_a_cursor(client, trails, person):
    alice = person("alice")
    for n, trail in enumerate(trails[:4]):
        log(client, alice, trail, hiked_on=f"2026-08-1{n}")
    first = mine(client, alice, limit=2)
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = mine(client, alice, limit=50, cursor=first["next_cursor"])
    assert second["total"] is None  # only the first page counts
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == first["total"]


# ----------------------------------------------------------------- visitors


def test_visitors_see_what_the_feed_shows_with_sharing_on(client, trails, person):
    alice = person("alice")
    bob = person("bob")
    log(client, alice, trails[0], note="Larches!")
    log(client, bob, trails[1])

    guest = visit(client, "alice")
    assert guest["sharing"] is None  # only the owner is told
    assert {item["author"]["username"] for item in guest["items"]} == {"alice"}
    assert guest["total"] == len(guest["items"]) == profile_count(client, "alice")
    assert "first-hike" in folded(guest)
    # The same posts as the feed's, card for card.
    from_feed = [item["id"] for item in feed(client)["items"] if item["author"]["username"] == "alice"]
    assert [item["id"] for item in guest["items"]] == from_feed

    signed_in = visit(client, "alice", headers=bob["headers"])
    assert [item["mine"] for item in signed_in["items"]] == [False] * len(signed_in["items"])
    # The owner on their own public page gets the visitors' list, marked as theirs.
    own = visit(client, "alice", headers=alice["headers"])
    assert all(item["mine"] for item in own["items"])


def test_no_tab_for_visitors_with_sharing_off(client, trails, person):
    alice = person("alice")
    bob = person("bob")
    log(client, alice, trails[0])
    set_privacy(client, alice, share_activity=False)

    assert profile_count(client, "alice") is None
    visit(client, "alice", expect=404)
    visit(client, "alice", headers=bob["headers"], expect=404)
    visit(client, "alice", headers=alice["headers"], expect=404)  # the owner's view is /api/me/activity


def test_no_tab_on_a_private_profile(client, trails, person):
    alice = person("alice")
    bob = person("bob")
    log(client, alice, trails[0])
    set_privacy(client, alice, is_private=True)

    assert client.get("/api/profiles/alice").json()["activity_count"] is None
    visit(client, "alice", expect=404)
    visit(client, "alice", headers=bob["headers"], expect=404)


def test_no_tab_on_a_profile_hidden_by_admins_or_unknown(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0])
    db = session_factory()
    db.add(ProfileModeration(user_id=alice["id"], hidden_by=uuid.uuid4(), reason="test"))
    db.commit()
    db.close()
    visit(client, "alice", expect=404)
    visit(client, "nobody-here", expect=404)


def test_sharing_on_with_nothing_posted_is_an_empty_tab(client, person):
    person("alice")
    assert profile_count(client, "alice") == 0
    assert visit(client, "alice") == {"items": [], "next_cursor": None, "total": 0, "sharing": None}


def test_a_hidden_journal_leaves_only_rank_posts(client, trails, person):
    alice = person("alice")
    for trail in trails[:6]:
        log(client, alice, trail)
    # The rank rides in the hike that reached it...
    assert any(e["kind"] == "rank" for item in visit(client, "alice")["items"] for e in item["earned"])
    # ...and stands alone once the hikes are hidden.
    set_privacy(client, alice, show_journal=False)
    body = visit(client, "alice")
    assert set(kinds(body)) == {"rank"} and body["total"] == len(body["items"])


def test_hidden_dates_stay_hidden_from_visitors(client, trails, person):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-07-01")  # Canada Day
    assert "canada-day" in folded(visit(client, "alice"))
    set_privacy(client, alice, hide_hike_dates=True)

    body = visit(client, "alice")
    assert body["items"]
    assert all(item["posted_at"] is None for item in body["items"])
    assert all(item["hike"]["hiked_on"] is None for item in body["items"] if item["kind"] == "hike")
    assert "canada-day" not in folded(body) and "first-hike" in folded(body)
    assert "2026-07-01" not in str(body)


def test_future_dated_hikes_never_show_to_visitors(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0], hiked_on="2026-08-14")
    # A browser can edit its own hike_logs row, so a date can move later.
    from app.models.hike_log import HikeLog
    from datetime import date
    db = session_factory()
    row = db.scalar(select(HikeLog).where(HikeLog.user_id == alice["id"]))
    row.hiked_on = date(2027, 1, 1)
    db.commit()
    db.close()
    body = visit(client, "alice")
    assert "hike" not in kinds(body)
    assert "first-hike" in [item["milestone"]["id"] for item in body["items"] if item["kind"] == "milestone"]


# ------------------------------------------------------------------ deleting


def test_deleting_a_hike_post_takes_its_folded_milestones(client, trails, person, session_factory):
    alice = person("alice")
    log(client, alice, trails[0])
    hike = next(item for item in mine(client, alice)["items"] if item["kind"] == "hike")
    assert hike["earned"]
    assert client.delete(f"/api/activity/{hike['id']}", headers=alice["headers"]).status_code == 204

    body = mine(client, alice)
    assert "hike" not in kinds(body) and "milestone" not in kinds(body)
    db = session_factory()
    assert db.scalars(select(ActivityPost).where(ActivityPost.kind == "milestone")).all() == []
    db.close()
    # The hike stays in the journal.
    assert client.get("/api/me/hike-logs", headers=alice["headers"]).json()
