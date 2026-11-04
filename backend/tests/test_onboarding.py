"""The /welcome setup flow's API: required username, saved progress, skips,
showing once, private preferences and the trail picks they drive.

Row-level security for the new table is tested against the local stack in
test_preferences_policies.py.
"""

import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.main import app
from app.models.trail import Trail
from app.preferences import INTERESTS, ONBOARDING_STEPS, REGION_SLUGS, REGIONS, Preferences, matched_interests, recommend

PROFILE = "/api/me/profile"
PREFS = "/api/me/preferences"
RECS = "/api/me/recommendations"
PRIVACY = "/api/me/privacy"

PRIVATE_KEYS = ("hiking_style", "experience", "interests", "favourite_regions", "onboarding")


@pytest.fixture
def people(make_token):
    def person():
        user_id = uuid.uuid4()
        return user_id, {"Authorization": f"Bearer {make_token(user_id)}"}

    return {"alice": person(), "bob": person()}


def pending(client, who) -> bool:
    response = client.get(PROFILE, headers=who)
    assert response.status_code == 200, response.text
    return response.json()["onboarding_pending"]


def patch_prefs(client, who, **changes):
    response = client.patch(PREFS, json=changes, headers=who)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------- the required step


def test_a_new_account_starts_with_the_flow_pending_and_nothing_answered(client, people):
    _, alice = people["alice"]
    assert pending(client, alice) is True
    assert client.get(PREFS, headers=alice).json() == {
        "hiking_style": None,
        "experience": None,
        "interests": [],
        "favourite_regions": [],
        "onboarding": {"step": None, "status": None, "finished_at": None},
    }


@pytest.mark.parametrize("username", ["", "  ", None])
def test_the_username_step_cant_be_left_empty(client, people, username):
    _, alice = people["alice"]
    assert client.patch(PROFILE, json={"username": username}, headers=alice).status_code == 422
    assert client.get(PROFILE, headers=alice).json()["username"] is None


def test_finishing_without_a_username_still_leaves_the_flow_pending(client, people):
    """Every later step is optional, but the gate keeps asking until there's a username."""
    _, alice = people["alice"]
    patch_prefs(client, alice, onboarding_status="completed")
    assert pending(client, alice) is True
    assert client.patch(PROFILE, json={"username": "alice", "display_name": "Alice"}, headers=alice).status_code == 200
    assert pending(client, alice) is False


def test_reserved_and_taken_usernames_are_refused_on_the_name_step(client, people):
    _, alice = people["alice"]
    _, bob = people["bob"]
    assert client.patch(PROFILE, json={"username": "admin"}, headers=alice).status_code == 422
    assert client.patch(PROFILE, json={"username": "bobby"}, headers=bob).status_code == 200
    assert client.patch(PROFILE, json={"username": "bobby"}, headers=alice).status_code == 409


# ---------------------------------------------------------------- resuming


def test_progress_and_answers_survive_leaving_and_coming_back(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    patch_prefs(client, alice, hiking_style="both", experience="few_seasons", onboarding_step="interests")
    # A later visit: same answers, same step.
    again = client.get(PREFS, headers=alice).json()
    assert again["onboarding"] == {"step": "interests", "status": None, "finished_at": None}
    assert again["hiking_style"] == "both" and again["experience"] == "few_seasons"
    assert pending(client, alice) is True


@pytest.mark.parametrize("step", ONBOARDING_STEPS)
def test_every_step_can_be_saved_as_the_resume_point(client, people, step):
    _, alice = people["alice"]
    assert patch_prefs(client, alice, onboarding_step=step)["onboarding"]["step"] == step


def test_unknown_steps_and_answers_are_refused(client, people):
    _, alice = people["alice"]
    for bad in (
        {"onboarding_step": "bonus"},
        {"hiking_style": "running"},
        {"experience": "expert"},
        {"interests": ["alpine_lakes", "nightlife"]},
        {"favourite_regions": ["banff", "narnia"]},
        {"interests": "alpine_lakes"},
        {"user_id": str(uuid.uuid4())},
    ):
        assert client.patch(PREFS, json=bad, headers=alice).status_code == 422, bad
    assert client.get(PREFS, headers=alice).json()["interests"] == []


def test_multi_selects_keep_their_order_once_each_and_can_be_cleared(client, people):
    _, alice = people["alice"]
    saved = patch_prefs(client, alice, interests=["waterfalls", "summits", "waterfalls"], favourite_regions=["yoho", "banff"])
    assert saved["interests"] == ["waterfalls", "summits"]
    assert saved["favourite_regions"] == ["yoho", "banff"]
    assert patch_prefs(client, alice, interests=[])["interests"] == []
    assert patch_prefs(client, alice, hiking_style=None)["hiking_style"] is None


def test_all_options_are_accepted(client, people):
    _, alice = people["alice"]
    saved = patch_prefs(client, alice, interests=list(INTERESTS), favourite_regions=list(REGION_SLUGS))
    assert saved["interests"] == list(INTERESTS) and saved["favourite_regions"] == list(REGION_SLUGS)


# ------------------------------------------------------- skipping and once


def test_skip_for_now_ends_the_flow_for_good(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    saved = patch_prefs(client, alice, onboarding_step="home", onboarding_status="skipped")
    assert saved["onboarding"]["status"] == "skipped" and saved["onboarding"]["finished_at"]
    assert pending(client, alice) is False
    # Finishing later doesn't rewrite how it ended, and it can't be reopened.
    assert patch_prefs(client, alice, onboarding_status="completed")["onboarding"]["status"] == "skipped"
    assert client.patch(PREFS, json={"onboarding_status": None}, headers=alice).status_code == 422
    assert pending(client, alice) is False


def test_skipping_single_steps_saves_nothing_but_the_step(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    for step in ("home", "style", "experience", "interests", "regions", "units", "privacy", "done"):
        patch_prefs(client, alice, onboarding_step=step)
    prefs = patch_prefs(client, alice, onboarding_status="completed")
    assert prefs["hiking_style"] is None and prefs["interests"] == [] and prefs["favourite_regions"] == []
    assert prefs["onboarding"]["status"] == "completed"
    profile = client.get(PROFILE, headers=alice).json()
    assert profile["home_province"] is None and profile["units"] is None and profile["onboarding_pending"] is False


def test_existing_users_see_it_once(client, people):
    """Someone with a username from before the flow existed has no row: pending once, then done."""
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "old_timer"}, headers=alice)
    assert pending(client, alice) is True
    patch_prefs(client, alice, onboarding_status="skipped")
    assert pending(client, alice) is False
    assert pending(client, alice) is False


def test_preferences_are_only_your_own(client, people):
    _, alice = people["alice"]
    _, bob = people["bob"]
    patch_prefs(client, alice, hiking_style="overnight", interests=["solitude"])
    assert client.get(PREFS, headers=bob).json()["hiking_style"] is None
    assert client.get(PREFS).status_code == 401
    assert client.patch(PREFS, json={"hiking_style": "day"}).status_code == 401
    assert client.get(RECS).status_code == 401


def test_deleting_the_account_deletes_the_preferences(client, people, session_factory):
    from app.models.preferences import ProfilePreferences

    alice_id, alice = people["alice"]
    patch_prefs(client, alice, hiking_style="day")
    assert client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=alice).status_code == 204
    db = session_factory()
    assert db.get(ProfilePreferences, alice_id) is None
    db.close()


# --------------------------------------------------- never shown to visitors


@pytest.fixture
def alice_public(client, people):
    """A public profile whose owner answered every question."""
    _, alice = people["alice"]
    assert client.patch(PROFILE, json={"username": "alice", "display_name": "Alice"}, headers=alice).status_code == 200
    assert client.get(PRIVACY, headers=alice).json()["is_private"] is False
    patch_prefs(
        client,
        alice,
        hiking_style="overnight",
        experience="seasoned",
        interests=["solitude", "wildlife"],
        favourite_regions=["tombstone", "kluane"],
        onboarding_step="privacy",
    )
    return alice


def test_public_profile_never_includes_the_new_fields(client, alice_public, people):
    _, bob = people["bob"]
    for headers in ({}, bob, alice_public):  # the owner gets the visitor view too
        response = client.get("/api/profiles/alice", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        for key in (*PRIVATE_KEYS, "onboarding_step", "onboarding_status", "onboarding_pending"):
            assert key not in body
        for value in ("overnight", "seasoned", "solitude", "wildlife", "tombstone", "kluane"):
            assert value not in response.text.lower(), value


def _route_paths():
    for route in app.routes:
        if "GET" in getattr(route, "methods", set()) and route.path.startswith("/api/"):
            yield route.path


def test_no_get_endpoint_shows_preferences_to_visitors(client, alice_public, people):
    _, bob = people["bob"]
    paths = sorted(set(_route_paths()))
    assert "/api/me/preferences" in paths
    for path in paths:
        url = re.sub(r"\{(\w+)\}", lambda m: "alice" if m.group(1) == "username" else str(uuid.uuid4()), path)
        for headers in ({}, bob):
            try:
                response = client.get(url, headers=headers)
            except Exception:  # noqa: BLE001  (a crash returns nothing, so nothing leaks)
                continue
            text = response.text.lower()
            for secret in ("tombstone", "kluane", "seasoned", '"solitude"'):
                assert secret not in text, f"{secret} leaked from GET {url}"


# ---------------------------------------------------------- recommendations


def _trail(**fields):
    defaults = dict(
        id=uuid.uuid4(),
        name="Trail",
        description=None,
        tags=[],
        typical_duration_nights=0,
        terrain_difficulty="moderate",
        distance_km=8,
        route_type="out_and_back",
        park_name=None,
        province_code="AB",
        popularity_rank=10,
    )
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def test_interests_match_names_descriptions_tags_and_trip_shape():
    larch = _trail(name="Larch Valley", tags=["larch"])
    falls = _trail(name="Johnston Canyon", description="Two waterfalls on a catwalk.")
    lake = _trail(name="Lake Agnes Teahouse")
    traverse = _trail(name="Rockwall", typical_duration_nights=3, route_type="point_to_point", popularity_rank=80)
    family = _trail(name="Marsh Loop", terrain_difficulty="easy", distance_km=2)
    assert matched_interests(larch, INTERESTS) == ["larches"]
    assert matched_interests(falls, INTERESTS) == ["waterfalls"]
    assert matched_interests(lake, INTERESTS) == ["alpine_lakes"]
    assert matched_interests(traverse, INTERESTS) == ["solitude", "traverses"]
    assert matched_interests(family, INTERESTS) == ["family"]


def test_picks_follow_style_experience_interests_regions_and_home():
    trails = [
        _trail(name="Busy hard day", terrain_difficulty="difficult", popularity_rank=1),
        _trail(name="Easy lake stroll", terrain_difficulty="easy", distance_km=3, popularity_rank=30),
        _trail(name="Big overnight", typical_duration_nights=2, terrain_difficulty="difficult", popularity_rank=2),
        _trail(name="Yoho Lake", park_name="Yoho National Park", province_code="BC", popularity_rank=50),
    ]
    beginner = recommend(trails, Preferences(hiking_style="day", experience="new"), limit=2)
    assert [t.name for t in beginner] == ["Easy lake stroll", "Yoho Lake"]
    backpacker = recommend(trails, Preferences(hiking_style="overnight", experience="seasoned"), limit=1)
    assert [t.name for t in backpacker] == ["Big overnight"]
    yoho_fan = recommend(trails, Preferences(favourite_regions=("yoho",)), limit=1)
    assert [t.name for t in yoho_fan] == ["Yoho Lake"]
    lake_lover = recommend(trails, Preferences(interests=("alpine_lakes",), home_province="BC"), limit=1)
    assert [t.name for t in lake_lover] == ["Yoho Lake"]


def test_no_answers_means_most_popular_first_and_at_most_two_per_park():
    trails = [_trail(name=f"Banff {i}", park_name="Banff National Park", popularity_rank=i) for i in range(1, 5)]
    trails.append(_trail(name="Elsewhere", popularity_rank=20))
    picks = recommend(trails, Preferences(), limit=5)
    assert [t.name for t in picks] == ["Banff 1", "Banff 2", "Elsewhere"]


def test_recommendations_endpoint_uses_the_answers_and_skips_saved_trails(client, people, session_factory):
    _, alice = people["alice"]
    db = session_factory()
    rows = {
        "hard": Trail(name="Hard summit", region="Rockies", country_code="CA", terrain_difficulty="extreme", popularity_rank=1),
        "easy": Trail(name="Easy falls", region="Rockies", country_code="CA", terrain_difficulty="easy", distance_km=3,
                      popularity_rank=5),
        "yoho": Trail(name="Iceline", region="Rockies", country_code="CA", terrain_difficulty="moderate",
                      park_name="Yoho National Park", province_code="BC", popularity_rank=9),
        "gone": Trail(name="Retired lake", region="Rockies", country_code="CA", terrain_difficulty="easy",
                      popularity_rank=2, retired_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    }
    db.add_all(rows.values())
    db.commit()
    ids = {key: str(row.id) for key, row in rows.items()}
    db.close()

    names = lambda: [t["name"] for t in client.get(RECS, headers=alice).json()]  # noqa: E731
    assert names() == ["Hard summit", "Easy falls", "Iceline"]  # popularity, nothing answered
    patch_prefs(client, alice, experience="new", hiking_style="day", interests=["waterfalls"])
    assert names()[0] == "Easy falls"
    patch_prefs(client, alice, favourite_regions=["yoho"], interests=[], experience="few_seasons")
    assert names()[0] == "Iceline"
    assert client.put(f"/api/me/saved-trails/{ids['yoho']}", headers=alice).status_code == 201
    assert "Iceline" not in names()
    assert "Retired lake" not in names()
    assert len(client.get(f"{RECS}?limit=1", headers=alice).json()) == 1


def test_region_list_has_unique_slugs_and_parks():
    assert len(set(REGION_SLUGS)) == len(REGIONS)
    assert len({region.park_name for region in REGIONS}) == len(REGIONS)
