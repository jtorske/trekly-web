"""Nudges toward the community settings (app/nudges.py, /api/me/nudges).

What matters: a nudge never changes a setting by itself, a dismissal is kept
on the server (so it holds on every device) and is never undone, and turning
a setting on puts its nudges away for good. Client privileges on the table
are checked against the local stack in test_client_privileges.py.
"""

import uuid

import pytest

from app.models.nudge import NudgeDismissal
from app.models.privacy import ProfileModeration

NUDGES = "/api/me/nudges"
PRIVACY = "/api/me/privacy"
ALL = ["hike_share", "activity_card", "hiked_by"]
SETTINGS = ("share_activity", "show_in_community", "is_private", "show_journal")


@pytest.fixture
def person(client, make_token):
    """A new user with a username: public profile, journal shown, sharing off (the defaults)."""

    def _make(username="alice", **privacy):
        user_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {make_token(user_id)}"}
        assert client.patch("/api/me/profile", json={"username": username}, headers=headers).status_code == 200
        # The signup trigger makes the settings row in Postgres; here the API does.
        assert client.get(PRIVACY, headers=headers).status_code == 200
        if privacy:
            assert client.patch(PRIVACY, json=privacy, headers=headers).status_code == 200
        return {"id": user_id, "headers": headers}

    return _make


def active(client, who):
    response = client.get(NUDGES, headers=who["headers"])
    assert response.status_code == 200, response.text
    return response.json()["active"]


def dismiss(client, who, nudge):
    return client.put(f"{NUDGES}/{nudge}/dismissed", headers=who["headers"])


def settings(client, who):
    body = client.get(PRIVACY, headers=who["headers"]).json()
    return {key: body[key] for key in SETTINGS}


def test_a_new_public_user_sees_every_nudge_and_nothing_is_on(client, person):
    alice = person()
    assert active(client, alice) == ALL
    assert settings(client, alice)["share_activity"] is False
    assert settings(client, alice)["show_in_community"] is False


def test_no_nudge_call_changes_a_setting(client, person):
    alice = person()
    before = settings(client, alice)
    active(client, alice)
    for nudge in ALL:
        assert dismiss(client, alice, nudge).status_code == 204
    active(client, alice)
    assert settings(client, alice) == before


def test_a_dismissal_holds_on_every_device_and_for_good(client, person, make_token):
    alice = person()
    assert dismiss(client, alice, "activity_card").status_code == 204
    assert active(client, alice) == ["hike_share", "hiked_by"]
    # Another device: a different token for the same account.
    other_device = {"headers": {"Authorization": f"Bearer {make_token(alice['id'])}"}}
    assert active(client, other_device) == ["hike_share", "hiked_by"]
    # Dismissing again is harmless, and nothing brings it back.
    assert dismiss(client, alice, "activity_card").status_code == 204
    client.patch(PRIVACY, json={"is_private": True}, headers=alice["headers"])
    client.patch(PRIVACY, json={"is_private": False}, headers=alice["headers"])
    assert "activity_card" not in active(client, alice)


def test_dismissals_are_per_user(client, person):
    alice, bob = person("alice"), person("bob")
    for nudge in ALL:
        dismiss(client, alice, nudge)
    assert active(client, alice) == []
    assert active(client, bob) == ALL


def test_turning_feed_sharing_on_puts_its_nudges_away_for_good(client, person):
    alice = person()
    client.patch(PRIVACY, json={"share_activity": True}, headers=alice["headers"])
    assert active(client, alice) == ["hiked_by"]
    client.patch(PRIVACY, json={"share_activity": False}, headers=alice["headers"])
    assert active(client, alice) == ["hiked_by"]


def test_turning_community_features_on_puts_the_hiked_by_nudge_away_for_good(client, person):
    alice = person()
    client.patch(PRIVACY, json={"show_in_community": True}, headers=alice["headers"])
    client.patch(PRIVACY, json={"show_in_community": False}, headers=alice["headers"])
    assert active(client, alice) == ["hike_share", "activity_card"]


def test_saving_a_setting_as_off_puts_nothing_away(client, person):
    alice = person()
    client.patch(PRIVACY, json={"share_activity": False, "show_in_community": False}, headers=alice["headers"])
    assert active(client, alice) == ALL


@pytest.mark.parametrize("privacy", [{"is_private": True}, {"show_journal": False}])
def test_no_nudges_while_the_setting_couldnt_take_effect(client, person, privacy):
    alice = person(**privacy)
    assert active(client, alice) == []
    # Nothing was put away meanwhile: they show once it could take effect.
    client.patch(PRIVACY, json={key: not value for key, value in privacy.items()}, headers=alice["headers"])
    assert active(client, alice) == ALL


def test_no_nudges_without_a_username_or_when_hidden_by_an_admin(client, person, make_token, session_factory):
    nameless = {"headers": {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}}
    assert active(client, nameless) == []
    alice = person()
    db = session_factory()
    db.add(ProfileModeration(user_id=alice["id"], reason="test"))
    db.commit()
    db.close()
    assert active(client, alice) == []


def test_unknown_nudges_and_guests_are_refused(client, person):
    alice = person()
    assert dismiss(client, alice, "everything").status_code == 422
    assert client.get(NUDGES).status_code == 401
    assert client.put(f"{NUDGES}/hiked_by/dismissed").status_code == 401


def test_deleting_the_account_deletes_its_dismissals(client, person, session_factory):
    alice = person()
    dismiss(client, alice, "hiked_by")
    response = client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=alice["headers"])
    assert response.status_code == 204, response.text
    db = session_factory()
    assert db.query(NudgeDismissal).filter_by(user_id=alice["id"]).count() == 0
    db.close()
