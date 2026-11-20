"""Comments on Activity posts: who may see and write them (guests, followers,
private profiles, blocks), moderation holds, rate limits, editing and
deleting, comments off, reports, notifications, and account deletion.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select

from app.main import app
from app.models.admin import AUTH_USERS
from app.models.comment import ActivityComment
from app.models.moderation import ModerationItem
from app.models.social import Block, Notification
from app.moderation import get_moderation_services
from tests.moderation_fakes import FakeScreener, Outbox, fake_services
from tests.test_activity import feed, hike_posts, log, person, set_privacy, trails  # noqa: F401  (fixtures)
from tests.test_availability import world  # noqa: F401  (fixture)
from tests.test_follows import approve, follow

NOW = datetime.now(timezone.utc)


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


@pytest.fixture
def post(client, trails, ana, mod):  # noqa: F811
    """Ana's shared hike post."""
    log(client, ana, trails[0])
    return hike_posts(feed(client))[0]["id"]


def comment(client, who, post_id, body="Looks great!", parent=None, expect=201):
    payload = {"body": body}
    if parent:
        payload["parent_id"] = parent
    response = client.post(f"/api/activity/{post_id}/comments", json=payload, headers=who["headers"] if who else {})
    assert response.status_code == expect, response.text
    return response.json()


def comments(client, post_id, who=None, expect=200):
    response = client.get(f"/api/activity/{post_id}/comments", headers=who["headers"] if who else {})
    assert response.status_code == expect, response.text
    return response.json()


def bodies(body):
    return [c["body"] for c in body["comments"]]


def block(session_factory, blocker, blocked):
    db = session_factory()
    db.add(Block(blocker_id=blocker["id"], blocked_id=blocked["id"]))
    db.commit()
    db.close()


def auth_row(session_factory, who, *, age=timedelta(days=30), confirmed=True):
    db = session_factory()
    db.execute(insert(AUTH_USERS).values(id=who["id"], email=f"{who['username']}@example.com",
                                         created_at=NOW - age, email_confirmed_at=NOW - age if confirmed else None))
    db.commit()
    db.close()


def inbox(client, who):
    items = client.get("/api/me/notifications", headers=who["headers"]).json()["items"]
    return [(i["kind"], [a["username"] for a in i["actors"]]) for i in items]


# ------------------------------------------------------------ seeing and writing


def test_guests_read_comments_but_cant_write(client, post, ben):
    comment(client, ben, post, "Nice one")
    assert bodies(comments(client, post)) == ["Nice one"]
    assert comments(client, post)["can_comment"] is False
    comment(client, None, post, "Hi", expect=401)


def test_comments_show_on_the_feed_with_a_count_and_the_newest_two(client, post, ana, ben, cam):
    for n in range(3):
        comment(client, ben if n % 2 == 0 else cam, post, f"Comment {n}")
    item = hike_posts(feed(client))[0]
    assert item["comment_count"] == 3
    # The newest two, oldest first.
    assert [c["body"] for c in item["comments"]] == ["Comment 1", "Comment 2"]
    assert set(item["comments"][0]["author"]) == {"username", "display_name", "avatar_path", "label"}
    assert item["comments_off"] is False
    assert item["can_comment"] is False  # a guest
    assert hike_posts(feed(client, ben["headers"]))[0]["can_comment"] is True
    # The post's own page.
    single = client.get(f"/api/activity/{post}", headers=ben["headers"]).json()
    assert single["id"] == post and single["comment_count"] == 3


def test_only_posts_you_can_see(client, trails, ana, ben, mod):  # noqa: F811
    log(client, ana, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    set_privacy(client, ana, share_activity=False)
    comments(client, post_id, ben, expect=404)
    comment(client, ben, post_id, expect=404)
    # Its author still can, on their own post.
    comment(client, ana, post_id, "Note to self")
    assert bodies(comments(client, post_id, ana)) == ["Note to self"]


def test_private_profiles_posts_are_closed_even_to_approved_followers(client, trails, ana, ben, cam, mod):  # noqa: F811
    log(client, ana, trails[0])
    post_id = hike_posts(feed(client))[0]["id"]
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    approve(client, ana, ben)
    # Private profiles never post to the feed, so nobody else reads or writes here.
    for who in (ben, cam):
        comments(client, post_id, who, expect=404)
        comment(client, who, post_id, expect=404)
    assert client.get(f"/api/activity/{post_id}", headers=ben["headers"]).status_code == 404
    comment(client, ana, post_id, "Mine")


def test_blocks_work_both_ways(client, post, session_factory, ana, ben, cam):
    comment(client, cam, post, "From Cam")
    block(session_factory, cam, ben)  # Cam blocked Ben
    # Ben no longer sees Cam's comment, and Cam won't see Ben's.
    assert bodies(comments(client, post, ben)) == []
    comment(client, ben, post, "From Ben")
    assert bodies(comments(client, post, cam)) == ["From Cam"]
    assert bodies(comments(client, post)) == ["From Cam", "From Ben"]
    # Ana blocking Ben: he can't see her post or comment on it.
    block(session_factory, ana, ben)
    comments(client, post, ben, expect=404)
    comment(client, ben, post, expect=404)
    assert client.get(f"/api/activity/{post}", headers=ben["headers"]).status_code == 404
    # Nor can he reply to Cam under it.
    assert hike_posts(feed(client, ben["headers"])) == []


def test_a_blocked_hikers_comment_cant_be_replied_to(client, post, session_factory, ben, cam):
    top = comment(client, cam, post, "From Cam")
    block(session_factory, ben, cam)
    comment(client, ben, post, "Reply", parent=top["id"], expect=404)


def test_comment_text_is_plain_and_bounded(client, post, ben):
    made = comment(client, ben, post, "  Line one\r\n\r\n\r\n\r\nLine two https://example.com  ")
    assert made["body"] == "Line one\n\nLine two https://example.com"
    comment(client, ben, post, "x" * 501, expect=422)
    comment(client, ben, post, "   ", expect=422)


# ------------------------------------------------------------ replies


def test_one_level_of_replies(client, post, ben, cam):
    top = comment(client, ben, post, "Top")
    reply = comment(client, cam, post, "@ben Reply", parent=top["id"])
    deeper = comment(client, ben, post, "@cam Deeper", parent=reply["id"])
    assert reply["parent_id"] == top["id"]
    assert deeper["parent_id"] == top["id"]  # filed under the same top-level comment
    other = comment(client, cam, post, "Second top")
    assert bodies(comments(client, post)) == ["Top", "@ben Reply", "@cam Deeper", "Second top"]
    assert other["parent_id"] is None


def test_a_reply_must_be_to_a_comment_on_the_same_post(client, trails, post, ana, ben):  # noqa: F811
    log(client, ana, trails[1])
    other_post = [p["id"] for p in hike_posts(feed(client)) if p["id"] != post][0]
    top = comment(client, ben, other_post, "Elsewhere")
    comment(client, ben, post, "Nope", parent=top["id"], expect=404)
    comment(client, ben, post, "Nope", parent=str(uuid.uuid4()), expect=404)


# ------------------------------------------------------------ editing and deleting


def test_authors_edit_their_own_comments(client, post, ana, ben, cam):
    made = comment(client, ben, post, "Frist")
    assert made["edited_at"] is None and made["mine"] is True
    response = client.patch(f"/api/comments/{made['id']}", json={"body": "First"}, headers=ben["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["body"] == "First" and response.json()["edited_at"] is not None
    assert comments(client, post)["comments"][0]["edited_at"] is not None
    # Nobody else can, not even the post's author.
    for who in (ana, cam):
        assert client.patch(f"/api/comments/{made['id']}", json={"body": "Hijacked"},
                            headers=who["headers"]).status_code == 404
    assert bodies(comments(client, post)) == ["First"]


def test_the_commenter_or_the_posts_author_can_delete(client, post, ana, ben, cam):
    mine = comment(client, ben, post, "Ben's")
    theirs = comment(client, cam, post, "Cam's")
    reply = comment(client, ben, post, "Reply to Cam", parent=theirs["id"])
    listed = {c["body"]: c for c in comments(client, post, ana)["comments"]}
    assert all(c["can_delete"] for c in listed.values())  # Ana's post
    assert comments(client, post, ben)["comments"][0]["can_delete"] is True
    assert comments(client, post, ben)["comments"][1]["can_delete"] is False
    # Cam can't delete Ben's.
    assert client.delete(f"/api/comments/{mine['id']}", headers=cam["headers"]).status_code == 404
    assert client.delete(f"/api/comments/{mine['id']}", headers=ben["headers"]).status_code == 204
    # The post's author deletes Cam's, and the reply under it goes too.
    assert client.delete(f"/api/comments/{theirs['id']}", headers=ana["headers"]).status_code == 204
    assert bodies(comments(client, post)) == []
    assert client.delete(f"/api/comments/{reply['id']}", headers=ben["headers"]).status_code == 404


def test_deleting_the_post_deletes_its_comments(client, post, session_factory, ana, ben):
    comment(client, ben, post, "Gone soon")
    assert client.delete(f"/api/activity/{post}", headers=ana["headers"]).status_code == 204
    db = session_factory()
    assert db.scalars(select(ActivityComment)).all() == []
    db.close()


# ------------------------------------------------------------ comments off


def test_the_posts_author_turns_comments_off_and_on(client, post, ana, ben):
    comment(client, ben, post, "Before")
    assert client.put(f"/api/activity/{post}/comments-off", json={"off": True},
                      headers=ben["headers"]).status_code == 404
    response = client.put(f"/api/activity/{post}/comments-off", json={"off": True}, headers=ana["headers"])
    assert response.json() == {"comments_off": True}
    listing = comments(client, post, ben)
    assert listing["comments_off"] is True and listing["can_comment"] is False
    assert bodies(listing) == ["Before"]  # the ones already there stay
    response = client.post(f"/api/activity/{post}/comments", json={"body": "After"}, headers=ben["headers"])
    assert response.status_code == 403 and "off" in response.json()["detail"]
    assert hike_posts(feed(client))[0]["comments_off"] is True
    client.put(f"/api/activity/{post}/comments-off", json={"off": False}, headers=ana["headers"])
    comment(client, ben, post, "After")


# ------------------------------------------------------------ moderation


def test_a_flagged_comment_is_held_for_its_author_only(client, post, session_factory, mod, ana, ben, cam):
    held = comment(client, ben, post, "You nastyword")
    assert held["review"] == "pending" and held["body"] == "You nastyword"
    assert bodies(comments(client, post, ben)) == ["You nastyword"]
    assert comments(client, post, ben)["comments"][0]["review"] == "pending"
    for who in (None, ana, cam):
        assert bodies(comments(client, post, who)) == []
    assert hike_posts(feed(client))[0]["comment_count"] == 0
    db = session_factory()
    item = db.scalar(select(ModerationItem).where(ModerationItem.kind == "comment"))
    assert item.state == "held" and item.in_queue and item.queue_reason == "flagged"
    assert db.get(ActivityComment, uuid.UUID(held["id"])).body is None
    db.close()
    # No notification about a held comment.
    assert inbox(client, ana) == []


def test_an_edit_is_screened_again(client, post, session_factory, ana, ben):
    made = comment(client, ben, post, "Fine words")
    assert inbox(client, ana) == [("comment", ["ben"])]
    response = client.patch(f"/api/comments/{made['id']}", json={"body": "Now nastyword"}, headers=ben["headers"])
    assert response.json()["review"] == "pending"
    assert bodies(comments(client, post, ana)) == []
    # Its notification is taken back.
    assert inbox(client, ana) == []
    # Editing back to clean text publishes it again.
    response = client.patch(f"/api/comments/{made['id']}", json={"body": "Fine again"}, headers=ben["headers"])
    assert response.json()["review"] is None
    assert bodies(comments(client, post, ana)) == ["Fine again"]


def test_a_comment_reported_three_times_is_held(client, post, session_factory, ben, person):  # noqa: F811
    made = comment(client, ben, post, "Borderline")
    reporters = [person(f"rep{n}") for n in range(3)]
    for who in reporters:
        auth_row(session_factory, who)
        response = client.post("/api/profiles/ben/report", json={"reason": "harassment", "comment_id": made["id"]},
                               headers=who["headers"])
        assert response.status_code == 202, response.text
    assert bodies(comments(client, post)) == []
    db = session_factory()
    item = db.scalar(select(ModerationItem).where(ModerationItem.kind == "comment"))
    assert item.state == "held" and item.text == "Borderline" and item.qualifying_reports == 3
    db.close()
    assert comments(client, post, ben)["comments"][0]["review"] == "pending"


def test_reporting_needs_a_comment_you_can_see(client, post, session_factory, ana, ben, cam):
    made = comment(client, ben, post, "Hello")
    response = client.post("/api/profiles/cam/report", json={"reason": "spam", "comment_id": made["id"]},
                           headers=ana["headers"])
    assert response.status_code == 404  # not Cam's comment
    block(session_factory, ben, cam)
    response = client.post("/api/profiles/ben/report", json={"reason": "spam", "comment_id": made["id"]},
                           headers=cam["headers"])
    assert response.status_code == 404


def test_an_admin_hide_is_final_until_reviewed(client, post, session_factory, ben, make_token, monkeypatch):
    made = comment(client, ben, post, "Rude")
    admin_id = uuid.uuid4()
    monkeypatch.setenv("ADMIN_USER_IDS", str(admin_id))
    admin = {"Authorization": f"Bearer {make_token(admin_id)}"}
    # Screening made its moderation item; the admin hides it from the queue.
    db = session_factory()
    item_id = db.scalar(select(ModerationItem.id).where(ModerationItem.kind == "comment"))
    db.close()
    response = client.post(f"/api/admin/moderation/{item_id}/hide", json={"reason": "Rude"}, headers=admin)
    assert response.status_code == 200, response.text
    assert bodies(comments(client, post)) == []
    assert comments(client, post, ben)["comments"][0]["review"] == "hidden"
    # Editing it doesn't undo the decision: it's held for review.
    response = client.patch(f"/api/comments/{made['id']}", json={"body": "Sorry"}, headers=ben["headers"])
    assert response.json()["review"] == "pending"
    assert bodies(comments(client, post)) == []


# ------------------------------------------------------------ limits


def test_the_rate_limit(client, post, ben):
    for n in range(10):
        comment(client, ben, post, f"Comment {n}")
    response = client.post(f"/api/activity/{post}/comments", json={"body": "One more"}, headers=ben["headers"])
    assert response.status_code == 429


def test_new_accounts_get_a_lower_limit(client, post, session_factory, ben):
    auth_row(session_factory, ben, age=timedelta(hours=2))
    for n in range(3):
        comment(client, ben, post, f"Comment {n}")
    comment(client, ben, post, "Too many", expect=429)


def test_an_unconfirmed_email_cant_comment(client, post, session_factory, ben):
    auth_row(session_factory, ben, confirmed=False)
    response = client.post(f"/api/activity/{post}/comments", json={"body": "Hi"}, headers=ben["headers"])
    assert response.status_code == 403 and "Confirm your email" in response.json()["detail"]


# ------------------------------------------------------------ notifications


def test_comment_reply_and_mention_notifications(client, post, ana, ben, cam, person):  # noqa: F811
    dee = person("dee")
    top = comment(client, ben, post, "Great day")
    assert inbox(client, ana) == [("comment", ["ben"])]
    comment(client, cam, post, "@ben agreed, and @dee you'd love it", parent=top["id"])
    assert inbox(client, ben) == [("comment_reply", ["cam"])]  # not also "mentioned you"
    assert inbox(client, dee) == [("mention", ["cam"])]
    assert inbox(client, ana) == [("comment", ["cam", "ben"])]  # grouped by post
    # Mentioning the post's author gets them one notification, "commented".
    comment(client, cam, post, "@ana thanks")
    assert [kind for kind, _ in inbox(client, ana)] == ["comment"]


def test_mentions_only_reach_people_who_can_see_the_post(client, post, session_factory, ana, ben, person):  # noqa: F811
    dee = person("dee")
    block(session_factory, ana, dee)
    comment(client, ben, post, "@dee look at this")
    assert inbox(client, dee) == []


def test_no_notifications_between_blocked_hikers(client, post, session_factory, ana, ben):
    top = comment(client, ana, post, "Thanks all")
    block(session_factory, ana, ben)
    # Ben can't see the post now, so he can't comment; and if he could, Ana wouldn't hear.
    comment(client, ben, post, "Hey", parent=top["id"], expect=404)
    assert inbox(client, ana) == []


def test_deleting_a_comment_takes_its_notification_back(client, post, ana, ben):
    made = comment(client, ben, post, "Hello")
    assert inbox(client, ana) == [("comment", ["ben"])]
    client.delete(f"/api/comments/{made['id']}", headers=ben["headers"])
    assert inbox(client, ana) == []


def test_each_type_can_be_turned_off(client, post, ana, ben, cam):
    response = client.patch("/api/me/notification-settings", json={"comment_reply": False, "mention": False},
                            headers=ben["headers"])
    assert response.status_code == 200, response.text
    top = comment(client, ben, post, "Top")
    comment(client, cam, post, "@ben reply", parent=top["id"])
    assert inbox(client, ben) == []


# ------------------------------------------------------------ account deletion


def test_comments_go_with_the_account(client, post, session_factory, ana, ben, cam):
    top = comment(client, ben, post, "Ben's")
    comment(client, cam, post, "Cam's reply", parent=top["id"])
    comment(client, cam, post, "Cam's own")
    response = client.request("DELETE", "/api/me", json={"confirm": "delete my account"},
                              headers=ben["headers"])
    assert response.status_code == 204, response.text
    assert bodies(comments(client, post)) == ["Cam's own"]
    db = session_factory()
    assert db.scalar(select(ActivityComment).where(ActivityComment.user_id == ben["id"])) is None
    assert db.scalars(select(Notification).where(Notification.actor_id == ben["id"])).all() == []
    db.close()
