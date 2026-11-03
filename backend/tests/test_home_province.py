"""Home province or territory: the owner picks one (or "Prefer not to say"),
and visitors see it, and its badge, only while "Home province" is switched
on in Settings → Privacy. Off by default, enforced by the API."""

import json
import pathlib
import re
import uuid

import pytest

from app.milestones_config import BY_ID
from app.provinces import PROVINCE_BADGE, PROVINCE_CODES

PROFILE = "/api/me/profile"
PRIVACY = "/api/me/privacy"
FEATURED = "/api/me/featured-badges"


@pytest.fixture
def people(make_token):
    def person():
        return {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}

    return {"alice": person(), "bob": person()}


@pytest.fixture
def alice(client, people):
    """A public profile (the new-user defaults) from Alberta."""
    who = people["alice"]
    response = client.patch(PROFILE, json={"username": "alice", "home_province": "AB"}, headers=who)
    assert response.status_code == 200, response.text
    assert response.json()["home_province"] == "AB"
    # Creates the settings row with the new-user defaults, as the signup trigger does.
    settings = client.get(PRIVACY, headers=who).json()
    assert settings["is_private"] is False and settings["show_journal"] is True
    assert settings["show_home_province"] is False
    return who


def public(client, headers=None):
    response = client.get("/api/profiles/alice", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def set_privacy(client, who, **changes):
    response = client.patch(PRIVACY, json=changes, headers=who)
    assert response.status_code == 200, response.text
    return response.json()


def visitor_views(client, people):
    """What a guest and another signed-in user each get."""
    return [public(client), public(client, people["bob"])]


# ------------------------------------------------------------ the owner


def test_everyone_starts_at_prefer_not_to_say_with_the_switch_off(client, people):
    who = people["alice"]
    assert client.get(PROFILE, headers=who).json()["home_province"] is None
    assert client.get(PRIVACY, headers=who).json()["show_home_province"] is False


@pytest.mark.parametrize("code", PROVINCE_CODES)
def test_all_thirteen_can_be_chosen(client, people, code):
    who = people["alice"]
    response = client.patch(PROFILE, json={"home_province": code}, headers=who)
    assert response.status_code == 200 and response.json()["home_province"] == code


@pytest.mark.parametrize("value", ["XX", "ab", "Alberta", "", "WA"])
def test_anything_else_is_refused(client, alice, value):
    assert client.patch(PROFILE, json={"home_province": value}, headers=alice).status_code == 422
    assert client.get(PROFILE, headers=alice).json()["home_province"] == "AB"


def test_prefer_not_to_say_clears_it(client, alice):
    assert client.patch(PROFILE, json={"home_province": None}, headers=alice).json()["home_province"] is None


def test_saving_other_fields_keeps_it(client, alice):
    assert client.patch(PROFILE, json={"bio": "Hi"}, headers=alice).json()["home_province"] == "AB"


# ------------------------------------------------------------ the privacy rule


def test_visitors_dont_see_it_while_the_switch_is_off(client, alice, people):
    for body in visitor_views(client, people):
        assert body["home_province"] is None
        assert "AB" not in json.dumps(body)


def test_visitors_see_it_once_the_switch_is_on(client, alice, people):
    assert set_privacy(client, alice, show_home_province=True)["show_home_province"] is True
    for body in visitor_views(client, people):
        assert body["home_province"] == "AB"


def test_turning_it_off_again_hides_it_on_the_next_request(client, alice, people):
    set_privacy(client, alice, show_home_province=True)
    assert public(client)["home_province"] == "AB"
    set_privacy(client, alice, show_home_province=False)
    assert public(client)["home_province"] is None


def test_a_private_profile_never_shows_it(client, alice, people):
    set_privacy(client, alice, show_home_province=True, is_private=True)
    for body in visitor_views(client, people):
        assert body["home_province"] is None and body["is_private"] is True


def test_the_owner_gets_the_visitor_view_too(client, alice):
    assert public(client, alice)["home_province"] is None


def test_prefer_not_to_say_shows_nothing_even_with_the_switch_on(client, alice):
    set_privacy(client, alice, show_home_province=True)
    client.patch(PROFILE, json={"home_province": None}, headers=alice)
    assert public(client)["home_province"] is None


def test_only_the_owner_can_flip_their_switch(client, alice, people):
    set_privacy(client, people["bob"], show_home_province=True)  # Bob's own setting
    assert client.get(PRIVACY, headers=alice).json()["show_home_province"] is False
    assert public(client)["home_province"] is None


def test_owner_endpoints_need_the_owner(client, alice):
    assert client.get(PROFILE).status_code == 401
    assert client.patch(PRIVACY, json={"show_home_province": True}).status_code == 401


# ------------------------------------------------------------ the badge


def featured_kinds(body):
    return [(b["kind"], b.get("province")) for b in body["badges"]]


def test_the_owner_can_feature_their_province_badge(client, alice):
    response = client.put(FEATURED, json={"badges": [{"province": True}]}, headers=alice)
    assert response.status_code == 200, response.text
    assert featured_kinds(response.json()) == [("province", "AB")]
    # The owner sees it whatever the switch says.
    assert featured_kinds(client.get(FEATURED, headers=alice).json()) == [("province", "AB")]


def test_no_province_no_badge(client, people):
    who = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=who)
    response = client.put(FEATURED, json={"badges": [{"province": True}]}, headers=who)
    assert response.status_code == 422 and "province" in response.json()["detail"]


def test_it_can_only_be_featured_once(client, alice):
    response = client.put(FEATURED, json={"badges": [{"province": True}, {"province": True}]}, headers=alice)
    assert response.status_code == 422


def test_the_province_id_cant_be_smuggled_in_as_a_milestone(client, alice):
    response = client.put(FEATURED, json={"badges": [{"milestone": PROVINCE_BADGE}]}, headers=alice)
    assert response.status_code == 422


def test_visitors_see_the_badge_only_with_the_switch_on(client, alice, people):
    client.put(FEATURED, json={"badges": [{"province": True}]}, headers=alice)
    for body in visitor_views(client, people):
        assert body["featured_badges"] == []
        assert "AB" not in json.dumps(body)
    set_privacy(client, alice, show_home_province=True)
    for body in visitor_views(client, people):
        assert [(b["kind"], b["province"]) for b in body["featured_badges"]] == [("province", "AB")]


def test_clearing_the_province_hides_a_featured_badge(client, alice):
    client.put(FEATURED, json={"badges": [{"province": True}]}, headers=alice)
    set_privacy(client, alice, show_home_province=True)
    client.patch(PROFILE, json={"home_province": None}, headers=alice)
    assert client.get(FEATURED, headers=alice).json()["badges"] == []
    assert public(client)["featured_badges"] == []


def test_a_changed_province_changes_the_badge(client, alice):
    client.put(FEATURED, json={"badges": [{"province": True}]}, headers=alice)
    client.patch(PROFILE, json={"home_province": "NU"}, headers=alice)
    assert featured_kinds(client.get(FEATURED, headers=alice).json()) == [("province", "NU")]


# ------------------------------------------------------------ consistency


def test_no_milestone_uses_the_province_badge_id():
    assert PROVINCE_BADGE not in BY_ID


def test_the_frontend_lists_the_same_thirteen():
    source = (pathlib.Path(__file__).parents[2] / "frontend" / "lib" / "provinces.ts").read_text(encoding="utf-8")
    block = source.split("PROVINCES", 1)[1]
    assert sorted(set(re.findall(r'\bcode: "([A-Z]{2})"', block))) == sorted(PROVINCE_CODES)
