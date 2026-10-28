"""'Hiked by' on trail pages, through the API: who appears, what shows, and
that turning any required setting off removes someone from the very next
response. Row-level security for the same rule is tested against the local
stack (test_profile_privacy_policies.py).
"""

import uuid

import pytest

from app.main import app
from app.models.account import Profile
from app.models.privacy import ProfileModeration
from app.routers.public_profiles import get_email_sender
from tests.test_availability import world  # noqa: F401  (fixture)
from tests.test_public_profiles import Outbox


@pytest.fixture
def outbox():
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def hiker(client, make_token, world):  # noqa: F811
    """A user who logged the trail: username, a dated note and a photo."""

    def _make(username, *, hiked_on="2026-08-14", note="Larches!", photo=True, community=True, **privacy):
        user_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {make_token(user_id, email=f'{username}@example.com')}"}
        assert client.patch("/api/me/profile", json={"username": username, "display_name": username.title()},
                            headers=headers).status_code == 200
        body = {"hiked_on": hiked_on, "note": note}
        if photo:
            body["photo_path"] = f"{user_id}/{uuid.uuid4()}.webp"
        assert client.put(f"/api/me/hike-logs/{world['trail']}", json=body, headers=headers).status_code == 201
        changes = {"show_in_community": community, **privacy}
        assert client.patch("/api/me/privacy", json=changes, headers=headers).status_code == 200
        return {"id": user_id, "headers": headers, "photo": body.get("photo_path")}

    return _make


def hikers(client, world, headers=None):  # noqa: F811
    response = client.get(f"/api/trails/{world['trail']}/hikers", headers=headers or {})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def names(body):
    return [person["username"] for person in body["hikers"]]


def set_privacy(client, person, **changes):
    assert client.patch("/api/me/privacy", json=changes, headers=person["headers"]).status_code == 200


# ------------------------------------------------------------- the setting


def test_community_is_off_by_default(client, make_token):
    headers = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    assert client.get("/api/me/privacy", headers=headers).json()["show_in_community"] is False


def test_nobody_is_listed_without_opting_in(client, world, hiker):  # noqa: F811
    hiker("alice", community=False)  # public profile, public journal, a note: still not listed
    assert hikers(client, world) == {"hikers": [], "others": 0, "notes": []}


def test_an_opted_in_hiker_is_listed_with_their_note(client, world, hiker):  # noqa: F811
    alice = hiker("alice")
    body = hikers(client, world)
    assert body["hikers"] == [{"username": "alice", "display_name": "Alice", "avatar_path": None}]
    assert body["others"] == 0
    assert body["notes"] == [{"username": "alice", "display_name": "Alice", "avatar_path": None, "note": "Larches!",
                              "hiked_on": "2026-08-14", "photo_path": alice["photo"]}]
    # Only declared fields: no user id or email.
    text = str(body)
    assert str(alice["id"]) not in text.replace(alice["photo"], "") and "@example.com" not in text


def test_guests_and_signed_in_users_get_the_same_answer(client, world, hiker, make_token):  # noqa: F811
    hiker("alice")
    bob = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    assert hikers(client, world) == hikers(client, world, bob)


def test_unknown_trail_is_404(client):
    assert client.get(f"/api/trails/{uuid.uuid4()}/hikers").status_code == 404


# ------------------------------------------------- every rule, immediately


@pytest.mark.parametrize(
    "change",
    [
        {"show_in_community": False},
        {"is_private": True},
        {"show_journal": False},
    ],
    ids=["community-off", "private", "journal-hidden"],
)
def test_turning_a_setting_off_removes_them_right_away(client, world, hiker, change):  # noqa: F811
    alice = hiker("alice")
    hiker("bob")
    assert sorted(names(hikers(client, world))) == ["alice", "bob"]

    set_privacy(client, alice, **change)
    body = hikers(client, world)
    assert names(body) == ["bob"]
    assert [note["username"] for note in body["notes"]] == ["bob"]

    # Undoing it brings them back: the opt-in itself is kept.
    set_privacy(client, alice, **{key: not value for key, value in change.items()})
    assert sorted(names(hikers(client, world))) == ["alice", "bob"]


@pytest.mark.parametrize("change", [{"is_private": True}, {"show_journal": False}], ids=["private", "journal-hidden"])
def test_opting_in_does_nothing_while_the_journal_isnt_public(client, world, hiker, change):  # noqa: F811
    hiker("alice", **change)
    assert hikers(client, world)["hikers"] == []


def test_no_username_means_not_listed(client, world, hiker, session_factory):  # noqa: F811
    alice = hiker("alice")
    db = session_factory()
    db.get(Profile, alice["id"]).username = None
    db.commit()
    db.close()
    assert hikers(client, world)["hikers"] == []


def test_admin_hidden_profiles_are_not_listed(client, world, hiker, session_factory):  # noqa: F811
    alice = hiker("alice")
    db = session_factory()
    db.add(ProfileModeration(user_id=alice["id"], reason="spam"))
    db.commit()
    db.close()
    assert hikers(client, world) == {"hikers": [], "others": 0, "notes": []}


# ------------------------------------------------------------ what shows


def test_hidden_dates_are_removed_and_dont_set_the_order(client, world, hiker):  # noqa: F811
    hiker("zed", hiked_on="2026-09-30", hide_hike_dates=True)  # newest, but dates hidden
    hiker("amy", hiked_on="2026-07-01", hide_hike_dates=True)
    hiker("old", hiked_on="2025-06-01")
    hiker("new", hiked_on="2026-08-20")
    body = hikers(client, world)
    # Dated hikers newest first, then those who hide dates by username.
    assert names(body) == ["new", "old", "amy", "zed"]
    assert [(note["username"], note["hiked_on"]) for note in body["notes"]] == [
        ("new", "2026-08-20"), ("old", "2025-06-01"), ("amy", None)
    ]


def test_at_most_eight_avatars_and_three_notes(client, world, hiker):  # noqa: F811
    for day in range(1, 13):
        hiker(f"hiker_{day:02}", hiked_on=f"2026-08-{day:02}", note=None if day % 2 else f"Note {day}")
    body = hikers(client, world)
    assert names(body) == [f"hiker_{day:02}" for day in range(12, 4, -1)]
    assert body["others"] == 4
    assert [note["note"] for note in body["notes"]] == ["Note 12", "Note 10", "Note 8"]


def test_hikes_without_a_note_list_the_hiker_but_no_note(client, world, hiker):  # noqa: F811
    hiker("alice", note=None, photo=False)
    body = hikers(client, world)
    assert names(body) == ["alice"] and body["notes"] == []


# --------------------------------------------------------------- reports


def test_report_a_trip_note(client, world, hiker, make_token, outbox):  # noqa: F811
    hiker("alice", note="Buy my stuff at spam.example")
    bob = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    response = client.post("/api/profiles/alice/report",
                           json={"reason": "spam", "details": "Ad", "trail_id": str(world["trail"])}, headers=bob)
    assert response.status_code == 202
    [email] = outbox.sent
    assert email.subject == "Trip note report: @alice (spam)"
    assert "A trip note was reported" in email.text
    assert "Trip note on: Skyline Trail" in email.text and "Note: Buy my stuff at spam.example" in email.text
    # Same one-a-day limit as reporting the profile.
    again = client.post("/api/profiles/alice/report", json={"reason": "spam"}, headers=bob)
    assert again.status_code == 429


@pytest.mark.parametrize("change", [{"show_in_community": False}, {"is_private": True}, {"show_journal": False}])
def test_only_listed_trip_notes_can_be_reported(client, world, hiker, make_token, outbox, change):  # noqa: F811
    alice = hiker("alice")
    set_privacy(client, alice, **change)
    bob = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    response = client.post("/api/profiles/alice/report", json={"reason": "spam", "trail_id": str(world["trail"])},
                           headers=bob)
    assert response.status_code == 404 and "Trip note not found" in response.text
    assert outbox.sent == []


def test_reporting_a_note_that_doesnt_exist(client, world, hiker, make_token, outbox):  # noqa: F811
    hiker("alice", note=None)
    bob = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    for trail in (world["trail"], uuid.uuid4()):
        response = client.post("/api/profiles/alice/report", json={"reason": "spam", "trail_id": str(trail)},
                               headers=bob)
        assert response.status_code == 404
