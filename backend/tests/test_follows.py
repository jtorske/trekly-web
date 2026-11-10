"""Following through the API: instant follows of public profiles, requests to
private ones (approve, decline, cancel), what an approved follower sees,
hidden lists, removing followers, search, and the Following feed.

Row-level security for the same rules is tested against the local stack in
test_follows_policies.py.
"""

import pytest

from app.models.privacy import ProfileModeration
from tests.test_activity import feed, kinds, log, person, set_privacy, trails  # noqa: F401  (fixtures)
from tests.test_availability import fetch, world  # noqa: F401  (fixtures)


def profile(client, who, viewer=None):
    response = client.get(f"/api/profiles/{who['username']}", headers=viewer["headers"] if viewer else {})
    assert response.status_code == 200, response.text
    return response.json()


def follow(client, viewer, who, expect=200):
    response = client.put(f"/api/profiles/{who['username']}/follow", headers=viewer["headers"])
    assert response.status_code == expect, response.text
    return response.json()


def unfollow(client, viewer, who):
    response = client.delete(f"/api/profiles/{who['username']}/follow", headers=viewer["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def people(client, who, which, viewer=None, expect=200, **params):
    response = client.get(f"/api/profiles/{who['username']}/{which}", params=params,
                          headers=viewer["headers"] if viewer else {})
    assert response.status_code == expect, response.text
    return response.json()


def names(page):
    return [item["username"] for item in page["items"]]


def requests(client, owner):
    response = client.get("/api/me/follow-requests", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return names(response.json())


def approve(client, owner, follower, expect=200):
    response = client.post(f"/api/me/follow-requests/{follower['username']}", headers=owner["headers"])
    assert response.status_code == expect, response.text


@pytest.fixture
def ana(person):  # noqa: F811
    return person("ana")


@pytest.fixture
def ben(person):  # noqa: F811
    return person("ben")


@pytest.fixture
def cam(person):  # noqa: F811
    return person("cam")


# ------------------------------------------------------------ public profiles


def test_following_a_public_profile_is_instant(client, ana, ben):
    assert follow(client, ben, ana) == {"follow": "following", "followers_count": 1}
    seen = profile(client, ana, ben)
    assert seen["follow"] == "following" and seen["followers_count"] == 1
    assert profile(client, ben, ana)["follows_you"] is True
    assert profile(client, ben)["following_count"] == 1
    # Idempotent.
    assert follow(client, ben, ana)["followers_count"] == 1


def test_unfollow_uses_the_same_button(client, ana, ben):
    follow(client, ben, ana)
    assert unfollow(client, ben, ana) == {"follow": "none", "followers_count": 0}
    assert profile(client, ana, ben)["follow"] == "none"


def test_you_cant_follow_yourself_or_without_a_username(client, ana, make_token):
    follow(client, ana, ana, expect=422)
    nameless = {"headers": {"Authorization": f"Bearer {make_token()}"}}
    follow(client, nameless, ana, expect=409)


def test_guests_get_no_follow_state(client, ana):
    body = profile(client, ana)
    assert body["follow"] is None and body["follows_you"] is False
    assert client.put("/api/profiles/ana/follow").status_code == 401


def test_the_owner_has_no_follow_state(client, ana):
    body = profile(client, ana, ana)
    assert body["follow"] is None and body["lists_open"] is True


# ------------------------------------------------------------ private profiles


def test_a_private_profile_gets_a_request(client, ana, ben):
    set_privacy(client, ana, is_private=True)
    assert follow(client, ben, ana) == {"follow": "requested", "followers_count": 0}
    seen = profile(client, ana, ben)
    assert seen["follow"] == "requested"
    assert seen["can_view"] is False and seen["journal"] is None and seen["bio"] is None
    assert requests(client, ana) == ["ben"]


def test_an_approved_follower_sees_the_switched_on_sections(client, trails, ana, ben, cam):
    log(client, ana, trails[0], note="Windy")
    set_privacy(client, ana, is_private=True, show_gear=False)
    follow(client, ben, ana)
    approve(client, ana, ben)

    seen = profile(client, ana, ben)
    assert seen["follow"] == "following" and seen["is_private"] is True and seen["can_view"] is True
    assert [e["note"] for e in seen["journal"]["entries"]] == ["Windy"]
    assert seen["rank"] is not None
    # Switched off stays private, even for followers.
    assert seen["gear"] is None and seen["trip_plans"] is None
    # Everyone else still sees a private profile.
    for viewer in (None, cam):
        other = profile(client, ana, viewer)
        assert other["can_view"] is False and other["journal"] is None and other["rank"] is None
    assert profile(client, ana)["followers_count"] == 1


def test_followers_dont_put_a_private_profile_in_public_features(client, trails, ana, ben):
    """Hiked by and the feed are public to all, so they still need a public profile."""
    set_privacy(client, ana, show_in_community=True)
    log(client, ana, trails[0], note="Windy")
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    approve(client, ana, ben)
    assert client.get(f"/api/trails/{trails[0]}/hikers", headers=ben["headers"]).json()["hikers"] == []
    assert kinds(feed(client, ben["headers"], scope="following")) == []
    assert kinds(feed(client, ben["headers"])) == []


def test_declining_and_cancelling_leave_nothing_behind(client, ana, ben, cam):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    follow(client, cam, ana)
    assert client.delete("/api/me/follow-requests/ben", headers=ana["headers"]).status_code == 204
    assert profile(client, ana, ben)["follow"] == "none"
    assert unfollow(client, cam, ana)["follow"] == "none"
    assert requests(client, ana) == []
    approve(client, ana, ben, expect=404)


def test_only_the_owner_approves(client, ana, ben, cam):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    # Cam has no request from Ben; Ben can't approve himself into Ana's followers.
    approve(client, cam, ben, expect=404)
    response = client.post("/api/me/follow-requests/ben", headers=ben["headers"])
    assert response.status_code == 404
    assert profile(client, ana, ben)["follow"] == "requested"


def test_going_public_approves_waiting_requests(client, ana, ben):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    set_privacy(client, ana, is_private=False)
    assert profile(client, ana, ben)["follow"] == "following"


def test_going_private_keeps_existing_followers(client, trails, ana, ben):
    log(client, ana, trails[0])
    follow(client, ben, ana)
    set_privacy(client, ana, is_private=True)
    assert profile(client, ana, ben)["journal"] is not None


def test_removing_a_follower_ends_their_access(client, trails, ana, ben):
    log(client, ana, trails[0])
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    approve(client, ana, ben)
    assert client.delete("/api/me/followers/ben", headers=ana["headers"]).status_code == 204
    seen = profile(client, ana, ben)
    assert seen["follow"] == "none" and seen["journal"] is None
    assert names(people(client, ana, "followers", ana)) == []


def test_profile_counts(client, ana, ben, cam):
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    follow(client, ana, cam)
    counts = client.get("/api/me/profile", headers=ana["headers"]).json()["counts"]
    assert counts["followers"] == 0 and counts["following"] == 1 and counts["follow_requests"] == 1


# ------------------------------------------------------------ the lists


def test_lists_show_people_and_your_state_toward_them(client, ana, ben, cam):
    follow(client, ben, ana)
    follow(client, cam, ana)
    follow(client, ben, cam)
    page = people(client, ana, "followers", ben)
    assert names(page) == ["cam", "ben"]  # newest first
    assert {item["username"]: item["follow"] for item in page["items"]} == {"cam": "following", "ben": None}
    assert set(page["items"][0]) == {"username", "display_name", "avatar_path", "label", "is_private", "follow"}
    assert names(people(client, ben, "following")) == ["cam", "ana"]


def test_lists_page_and_search(client, ana, person):  # noqa: F811
    for n in range(5):
        follow(client, person(f"hiker{n}"), ana)
    first = people(client, ana, "followers", limit=2)
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = people(client, ana, "followers", limit=2, cursor=first["next_cursor"])
    assert set(names(first)).isdisjoint(names(second))
    assert names(people(client, ana, "followers", q="hiker3")) == ["hiker3"]
    # Display names match anywhere ("Hiker4" is hiker4's display name).
    assert names(people(client, ana, "followers", q="ker4")) == ["hiker4"]
    # LIKE wildcards are literal.
    assert names(people(client, ana, "followers", q="%")) == []


def test_hidden_lists_still_show_counts(client, ana, ben, cam):
    follow(client, ben, ana)
    set_privacy(client, ana, hide_follow_lists=True)
    body = profile(client, ana, cam)
    assert body["followers_count"] == 1 and body["lists_open"] is False
    for which in ("followers", "following"):
        people(client, ana, which, cam, expect=403)
        people(client, ana, which, expect=403)
        # Even a follower can't open them...
        people(client, ana, which, ben, expect=403)
        # ...but the owner can.
        people(client, ana, which, ana)


def test_a_private_profiles_lists_are_for_approved_followers(client, ana, ben, cam):
    set_privacy(client, ana, is_private=True)
    follow(client, cam, ana)
    people(client, ana, "followers", ben, expect=403)
    people(client, ana, "followers", cam, expect=403)  # only requested
    approve(client, ana, cam)
    assert names(people(client, ana, "followers", cam)) == ["cam"]


def test_hidden_accounts_leave_lists_and_counts(client, session_factory, ana, ben):
    follow(client, ben, ana)
    db = session_factory()
    db.add(ProfileModeration(user_id=ben["id"]))
    db.commit()
    db.close()
    assert names(people(client, ana, "followers")) == []
    assert profile(client, ana)["followers_count"] == 0
    # Ben's profile itself is gone for visitors, so he can't be followed either.
    follow(client, ana, ben, expect=404)


# ------------------------------------------------------------ the Following feed


def test_the_following_feed(client, trails, ana, ben, cam):
    log(client, ana, trails[0])
    log(client, cam, trails[1])
    assert feed(client, ben["headers"])["follows_anyone"] is False
    assert kinds(feed(client, ben["headers"], scope="following")) == []

    follow(client, ben, ana)
    body = feed(client, ben["headers"], scope="following")
    assert body["follows_anyone"] is True
    assert {author for author, _ in kinds(body)} == {"ana"}
    assert all(item["author"]["follow"] == "following" for item in body["items"])
    # Everyone still has both, and says whom Ben follows.
    everyone = feed(client, ben["headers"])
    assert {author for author, _ in kinds(everyone)} == {"ana", "cam"}
    assert {i["author"]["username"]: i["author"]["follow"] for i in everyone["items"]} == {"ana": "following",
                                                                                         "cam": "none"}


def test_the_following_feed_keeps_the_feed_rules(client, trails, ana, ben):
    log(client, ana, trails[0])
    follow(client, ben, ana)
    set_privacy(client, ana, share_activity=False)
    assert kinds(feed(client, ben["headers"], scope="following")) == []


def test_requests_dont_count_for_the_following_feed(client, trails, ana, ben):
    log(client, ana, trails[0])
    set_privacy(client, ana, is_private=True)
    follow(client, ben, ana)
    body = feed(client, ben["headers"], scope="following")
    assert body["items"] == [] and body["follows_anyone"] is False


def test_guests_following_feed_is_empty(client, trails, ana):
    log(client, ana, trails[0])
    assert feed(client, scope="following")["items"] == []


# ------------------------------------------------------------ account deletion


def test_deleting_an_account_removes_its_follows_and_requests(client, session_factory, ana, ben, cam):
    from sqlalchemy import func, select

    from app.models.social import Follow

    follow(client, ben, ana)
    follow(client, ana, cam)
    set_privacy(client, cam, is_private=True)
    follow(client, ana, ben)
    set_privacy(client, ben, is_private=True)
    follow(client, cam, ben)  # a request to Ben, untouched
    response = client.request("DELETE", "/api/me", json={"confirm": "delete my account"},
                              headers=ana["headers"])
    assert response.status_code == 204, response.text
    db = session_factory()
    left = db.execute(select(Follow.follower_id, Follow.followee_id)).all()
    assert all(ana["id"] not in row for row in left)
    assert db.scalar(select(func.count()).select_from(Follow)) == 1
    db.close()
    assert profile(client, cam)["followers_count"] == 0
