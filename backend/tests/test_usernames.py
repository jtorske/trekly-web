"""Usernames are required, unique (case-insensitive) and never reserved,
enforced by the API whatever the form sends. The database's own copy of
these rules is tested in test_username_rules_db.py."""

import uuid

import pytest

from app.models.account import Profile
from app.models.privacy import ProfileSettings
from app.usernames import RESERVED_USERNAMES, base_from_hint, load_reserved

REQUESTED_RESERVED = {
    "admin", "administrator", "support", "help", "trekly", "api", "u", "settings", "login", "signup",
    "about", "privacy", "terms", "journal", "gear", "explore", "staff", "moderator", "root", "system",
}


@pytest.fixture
def alice():
    return uuid.uuid4()


@pytest.fixture
def bob():
    return uuid.uuid4()


@pytest.fixture
def headers(make_token):
    return lambda user_id: {"Authorization": f"Bearer {make_token(user_id)}"}


def take(session_factory, username):
    session = session_factory()
    session.add(Profile(id=uuid.uuid4(), username=username))
    session.commit()
    session.close()


def test_reserved_list_comes_from_the_config_file():
    assert RESERVED_USERNAMES == load_reserved()
    assert REQUESTED_RESERVED <= RESERVED_USERNAMES


@pytest.mark.parametrize("name", sorted(REQUESTED_RESERVED))
def test_reserved_names_are_rejected_on_save(client, headers, alice, name):
    for variant in (name, name.upper()):
        response = client.patch("/api/me/profile", json={"username": variant}, headers=headers(alice))
        assert response.status_code == 422
        # "u" is also too short, which is said first.
        assert ("reserved" if len(name) >= 3 else "3–30") in response.json()["detail"][0]["msg"]


def test_duplicate_usernames_are_rejected_whatever_the_case(client, headers, alice, bob):
    assert client.patch("/api/me/profile", json={"username": "lake_agnes"}, headers=headers(alice)).status_code == 200
    for variant in ("lake_agnes", "Lake_Agnes", " LAKE_AGNES "):
        clash = client.patch("/api/me/profile", json={"username": variant}, headers=headers(bob))
        assert clash.status_code == 409
        assert clash.json()["detail"] == "That username is taken."


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_username_cannot_be_removed(client, headers, alice, value):
    client.patch("/api/me/profile", json={"username": "keeper"}, headers=headers(alice))
    response = client.patch("/api/me/profile", json={"username": value}, headers=headers(alice))
    assert response.status_code == 422
    assert client.get("/api/me/profile", headers=headers(alice)).json()["username"] == "keeper"


def test_choosing_a_username_leaves_privacy_settings_alone(client, headers, session_factory, alice):
    session = session_factory()
    session.add(ProfileSettings(user_id=alice, is_private=True, show_journal=False))
    session.commit()
    session.close()

    assert client.patch("/api/me/profile", json={"username": "quiet_one"}, headers=headers(alice)).status_code == 200

    session = session_factory()
    settings = session.get(ProfileSettings, alice)
    assert settings.is_private is True and settings.show_journal is False
    session.close()
    assert client.get("/api/me/profile", headers=headers(alice)).json()["visibility"] == "private"


def test_check_reports_available_taken_reserved_and_malformed(client, session_factory):
    take(session_factory, "taken_name")

    def check(name):
        response = client.get("/api/usernames/check", params={"username": name})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        return response.json()

    free = check("Free_Name")
    assert free == {"username": "free_name", "available": True, "message": "@free_name is available."}
    assert check("TAKEN_NAME") == {"username": "taken_name", "available": False, "message": "That username is taken."}
    assert check("admin")["available"] is False and "reserved" in check("admin")["message"]
    assert check("Trekly")["available"] is False
    for bad in ("ab", "has space", "dash-name", "x" * 31):
        assert check(bad)["available"] is False
        assert check(bad)["message"] == "Use 3–30 lowercase letters, numbers or underscores."


def test_check_needs_no_sign_in_and_reveals_no_owner(client, session_factory):
    take(session_factory, "someone")
    body = client.get("/api/usernames/check", params={"username": "someone"}).json()
    assert set(body) == {"username", "available", "message"}


@pytest.mark.parametrize(
    "hint, expected",
    [
        ("Jordan Torske", "jordan_torske"),
        ("jordan.torske@example.com", "jordan_torske"),
        ("  Zoë  O'Brien ", "zoe_o_brien"),
        ("Al", "al_hiker"),
        ("", "hiker"),
        ("日本", "hiker"),
        ("A" * 60, "a" * 26),
    ],
)
def test_base_from_hint(hint, expected):
    assert base_from_hint(hint) == expected


def test_suggest_adds_a_number_when_taken(client, session_factory):
    def suggest(hint):
        return client.get("/api/usernames/suggest", params={"hint": hint}).json()["username"]

    assert suggest("Jordan Torske") == "jordan_torske"
    take(session_factory, "jordan_torske")
    take(session_factory, "jordan_torske2")
    assert suggest("Jordan Torske") == "jordan_torske3"
    assert suggest("jordan.torske@example.com") == "jordan_torske3"
    # Never suggests a reserved name.
    assert suggest("Admin") == "admin2"
