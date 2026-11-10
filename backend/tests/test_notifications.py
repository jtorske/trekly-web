"""Notifications through the API: which actions make them, undoing an action
takes its notification back, grouping, server-side read state, per-type
settings, and cleanup when an account is deleted.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.privacy import ProfileModeration
from app.models.social import Notification
from tests.test_activity import hike_posts, feed, log, person, set_privacy, trails  # noqa: F401  (fixtures)
from tests.test_availability import fetch, world  # noqa: F401  (fixtures)
from tests.test_follows import approve, follow, unfollow


def inbox(client, who):
    response = client.get("/api/me/notifications", headers=who["headers"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def lines(body):
    """(kind, actor usernames, count, unread) per group, newest first."""
    return [(i["kind"], [a["username"] for a in i["actors"]], i["actor_count"], i["unread"]) for i in body["items"]]


def badge(client, who):
    return client.get("/api/me/notifications/unread", headers=who["headers"]).json()["unread"]


def high_five(client, who, post_id, on=True):
    response = client.request("PUT" if on else "DELETE", f"/api/activity/{post_id}/high-five", headers=who["headers"])
    assert response.status_code == 200, response.text


@pytest.fixture
def ana(person):  # noqa: F811
    return person("ana")


@pytest.fixture
def ben(person):  # noqa: F811
    return person("ben")


@pytest.fixture
def cam(person):  # noqa: F811
    return person("cam")


@pytest.fixture
def ana_post(client, trails, ana):  # noqa: F811
    log(client, ana, trails[0])
    return hike_posts(feed(client))[0]["id"]


# ------------------------------------------------------------ follows


def test_a_new_follower(client, ana, ben):
    follow(client, ben, ana)
    body = inbox(client, ana)
    assert lines(body) == [("new_follower", ["ben"], 1, True)]
    item = body["items"][0]
    assert item["follow"] == "none"  # "Follow back"
    assert set(item["actors"][0]) == {"username", "display_name", "avatar_path"}
    assert body["unread"] == 1 and badge(client, ana) == 1
    # Nothing for the follower.
    assert inbox(client, ben)["items"] == []


def test_unfollowing_takes_it_back_and_refollowing_doesnt_double(client, ana, ben):
    follow(client, ben, ana)
    unfollow(client, ben, ana)
    assert inbox(client, ana)["items"] == []
    follow(client, ben, ana)
    unfollow(client, ben, ana)
    follow(client, ben, ana)
    assert lines(inbox(client, ana)) == [("new_follower", ["ben"], 1, True)]


def test_a_request_then_approval(client, ana, ben):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    assert lines(inbox(client, ana)) == [("follow_request", ["ben"], 1, True)]
    approve(client, ana, ben)
    # The request is answered, so it goes; Ben hears it was approved.
    assert inbox(client, ana)["items"] == []
    assert lines(inbox(client, ben)) == [("request_approved", ["ana"], 1, True)]


def test_declined_or_cancelled_requests_leave_no_notification(client, ana, ben, cam):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    follow(client, cam, ana)
    assert client.delete("/api/me/follow-requests/ben", headers=ana["headers"]).status_code == 204
    unfollow(client, cam, ana)
    assert inbox(client, ana)["items"] == []
    # Declining tells Ben nothing.
    assert inbox(client, ben)["items"] == []


def test_going_public_approves_and_tells_them(client, ana, ben):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    set_privacy(client, ana, is_private=False)
    assert inbox(client, ana)["items"] == []
    assert lines(inbox(client, ben)) == [("request_approved", ["ana"], 1, True)]


def test_removing_a_follower_takes_back_their_notification(client, ana, ben):
    follow(client, ben, ana)
    assert client.delete("/api/me/followers/ben", headers=ana["headers"]).status_code == 204
    assert inbox(client, ana)["items"] == []


# ------------------------------------------------------------ high fives


def test_high_fives_group_by_post(client, ana, ben, cam, person, ana_post):  # noqa: F811
    dee = person("dee")
    for who in (ben, cam, dee):
        high_five(client, who, ana_post)
    body = inbox(client, ana)
    assert lines(body) == [("high_five", ["dee", "cam", "ben"], 3, True)]
    post = body["items"][0]["post"]
    assert {k: post[k] for k in ("id", "kind", "title")} == {"id": ana_post, "kind": "hike", "title": "Skyline Trail"}
    assert post["trail_id"]
    assert len(body["items"][0]["ids"]) == 3
    assert body["items"][0]["follow"] is None  # only for one-person groups
    # Five people show as the three newest, and a count.
    for name in ("eve", "fay"):
        high_five(client, person(name), ana_post)
    assert lines(inbox(client, ana))[0][1:3] == (["fay", "eve", "dee"], 5)


def test_taking_back_a_high_five_takes_back_its_notification(client, ana, ben, ana_post):
    high_five(client, ben, ana_post)
    high_five(client, ben, ana_post, on=False)
    assert inbox(client, ana)["items"] == []


def test_your_own_high_five_notifies_nobody(client, ana, ana_post):
    high_five(client, ana, ana_post)
    assert inbox(client, ana)["items"] == []


def test_different_posts_are_different_groups(client, trails, ana, ben, ana_post):
    log(client, ana, trails[1])
    other = [p["id"] for p in hike_posts(feed(client)) if p["id"] != ana_post][0]
    high_five(client, ben, ana_post)
    high_five(client, ben, other)
    assert [i["post"]["id"] for i in inbox(client, ana)["items"]] == [other, ana_post]


def test_followers_group_by_day_and_requests_dont_group(client, session_factory, ana, ben, cam, person):  # noqa: F811
    follow(client, ben, ana)
    follow(client, cam, ana)
    assert lines(inbox(client, ana)) == [("new_follower", ["cam", "ben"], 2, True)]
    # Ben's follow was yesterday: two groups.
    db = session_factory()
    row = db.scalar(select(Notification).where(Notification.actor_id == ben["id"]))
    row.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    db.close()
    assert [g[1] for g in lines(inbox(client, ana))] == [["cam"], ["ben"]]

    set_privacy(client, cam, is_private=True)
    follow(client, ana, cam)
    follow(client, ben, cam)
    assert lines(inbox(client, cam)) == [("follow_request", ["ben"], 1, True), ("follow_request", ["ana"], 1, True)]


# ------------------------------------------------------------ read state


def test_mark_all_read_is_stored(client, ana, ben, cam, ana_post):
    follow(client, ben, ana)
    high_five(client, cam, ana_post)
    assert badge(client, ana) == 2
    response = client.post("/api/me/notifications/read", json={}, headers=ana["headers"])
    assert response.json() == {"unread": 0}
    assert [i["unread"] for i in inbox(client, ana)["items"]] == [False, False]
    # A new high five makes that group unread again.
    high_five(client, ben, ana_post)
    assert [(i["kind"], i["unread"]) for i in inbox(client, ana)["items"]] == [("high_five", True), ("new_follower", False)]


def test_mark_some_read(client, ana, ben, cam, ana_post):
    follow(client, ben, ana)
    high_five(client, cam, ana_post)
    first = inbox(client, ana)["items"][0]
    assert client.post("/api/me/notifications/read", json={"ids": first["ids"]},
                       headers=ana["headers"]).json() == {"unread": 1}


def test_you_cant_mark_someone_elses_read(client, ana, ben):
    follow(client, ben, ana)
    ids = inbox(client, ana)["items"][0]["ids"]
    client.post("/api/me/notifications/read", json={"ids": ids}, headers=ben["headers"])
    assert badge(client, ana) == 1


def test_signed_out_gets_nothing(client):
    assert client.get("/api/me/notifications").status_code == 401
    assert client.get("/api/me/notifications/unread").status_code == 401
    assert client.post("/api/me/notifications/read", json={}).status_code == 401


# ------------------------------------------------------------ settings


def test_settings_default_on_and_turning_off_stops_and_hides(client, ana, ben, cam, ana_post):
    settings = client.get("/api/me/notification-settings", headers=ana["headers"]).json()
    assert settings == {"new_follower": True, "follow_request": True, "request_approved": True,
                        "high_five": True, "comment": True}
    high_five(client, ben, ana_post)
    response = client.patch("/api/me/notification-settings", json={"high_five": False}, headers=ana["headers"])
    assert response.json()["high_five"] is False and response.json()["new_follower"] is True
    # Hidden, and new ones aren't made.
    assert inbox(client, ana)["items"] == []
    high_five(client, cam, ana_post)
    follow(client, ben, ana)
    assert [i["kind"] for i in inbox(client, ana)["items"]] == ["new_follower"]
    client.patch("/api/me/notification-settings", json={"high_five": True}, headers=ana["headers"])
    assert [g[1] for g in lines(inbox(client, ana)) if g[0] == "high_five"] == [["ben"]]


def test_settings_reject_unknown_types(client, ana):
    response = client.patch("/api/me/notification-settings", json={"email": True}, headers=ana["headers"])
    assert response.status_code == 422


# ------------------------------------------------------------ who shows


def test_hidden_accounts_disappear_from_notifications(client, session_factory, ana, ben):
    follow(client, ben, ana)
    db = session_factory()
    db.add(ProfileModeration(user_id=ben["id"]))
    db.commit()
    db.close()
    assert inbox(client, ana)["items"] == [] and badge(client, ana) == 0


def test_deleting_an_account_removes_notifications_both_ways(client, session_factory, ana, ben, cam, ana_post):
    follow(client, ben, ana)
    follow(client, ana, cam)
    high_five(client, cam, ana_post)
    client.patch("/api/me/notification-settings", json={"comment": False}, headers=ana["headers"])
    response = client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=ana["headers"])
    assert response.status_code == 204
    db = session_factory()
    assert db.scalar(select(func.count()).select_from(Notification).where(
        (Notification.user_id == ana["id"]) | (Notification.actor_id == ana["id"])
    )) == 0
    db.close()
    assert inbox(client, cam)["items"] == []
