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
from app.preferences import ONBOARDING_STEPS, REGION_SLUGS, REGIONS, Preferences, recommend

PROFILE = "/api/me/profile"
PREFS = "/api/me/preferences"
RECS = "/api/me/recommendations"
PRIVACY = "/api/me/privacy"

PRIVATE_KEYS = ("hiking_style", "experience", "favourite_regions", "onboarding")


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


def choose_experience(client, who, experience="few_seasons"):
    """The experience step's answer, which finishing or skipping the flow also needs."""
    response = client.patch(PREFS, json={"experience": experience}, headers=who)
    assert response.status_code == 200, response.text


def answer_required(client, who):
    """Both required questions after the username: experience, then Public or Private."""
    choose_experience(client, who)
    choose_visibility(client, who)


def choose_visibility(client, who, is_private=False):
    """The privacy step's answer, which finishing or skipping the flow needs."""
    response = client.patch(PRIVACY, json={"is_private": is_private}, headers=who)
    assert response.status_code == 200, response.text


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
        "favourite_regions": [],
        "onboarding": {"step": None, "status": None, "finished_at": None},
    }


@pytest.mark.parametrize("username", ["", "  ", None])
def test_the_username_step_cant_be_left_empty(client, people, username):
    _, alice = people["alice"]
    assert client.patch(PROFILE, json={"username": username}, headers=alice).status_code == 422
    assert client.get(PROFILE, headers=alice).json()["username"] is None


def test_finishing_without_a_username_still_leaves_the_flow_pending(client, people):
    """The gate keeps asking until there's a username."""
    _, alice = people["alice"]
    answer_required(client, alice)
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
    patch_prefs(client, alice, hiking_style="both", experience="few_seasons", onboarding_step="regions")
    # A later visit: same answers, same step.
    again = client.get(PREFS, headers=alice).json()
    assert again["onboarding"] == {"step": "regions", "status": None, "finished_at": None}
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
        # The interests step is gone; its answers aren't taken any more.
        {"onboarding_step": "interests"},
        {"interests": ["alpine_lakes"]},
        {"hiking_style": "running"},
        {"experience": "expert"},
        {"interests": ["alpine_lakes", "nightlife"]},
        {"favourite_regions": ["banff", "narnia"]},
        {"user_id": str(uuid.uuid4())},
    ):
        assert client.patch(PREFS, json=bad, headers=alice).status_code == 422, bad
    assert "interests" not in client.get(PREFS, headers=alice).json()


def test_multi_selects_keep_their_order_once_each_and_can_be_cleared(client, people):
    _, alice = people["alice"]
    saved = patch_prefs(client, alice, favourite_regions=["yoho", "banff", "yoho"])
    assert saved["favourite_regions"] == ["yoho", "banff"]
    assert patch_prefs(client, alice, favourite_regions=[])["favourite_regions"] == []
    assert patch_prefs(client, alice, hiking_style=None)["hiking_style"] is None


def test_all_options_are_accepted(client, people):
    _, alice = people["alice"]
    saved = patch_prefs(client, alice, favourite_regions=list(REGION_SLUGS))
    assert saved["favourite_regions"] == list(REGION_SLUGS)


# ------------------------------------------------------- skipping and once


def test_skip_for_now_ends_the_flow_for_good(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    answer_required(client, alice)
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
    for step in ("home", "style", "experience", "regions", "hiked", "pack", "units", "privacy", "done"):
        patch_prefs(client, alice, onboarding_step=step)
    answer_required(client, alice)
    prefs = patch_prefs(client, alice, onboarding_status="completed")
    assert prefs["hiking_style"] is None and prefs["favourite_regions"] == []
    assert prefs["onboarding"]["status"] == "completed"
    profile = client.get(PROFILE, headers=alice).json()
    assert profile["home_province"] is None and profile["units"] is None and profile["onboarding_pending"] is False


def test_existing_users_see_it_once(client, people):
    """Someone with a username from before the flow existed has no row: pending once, then done."""
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "old_timer"}, headers=alice)
    assert pending(client, alice) is True
    answer_required(client, alice)
    patch_prefs(client, alice, onboarding_status="skipped")
    assert pending(client, alice) is False
    assert pending(client, alice) is False


# ------------------------------------------------- experience is required


@pytest.mark.parametrize("outcome", ["completed", "skipped"])
def test_the_flow_cant_end_without_an_experience_level(client, people, outcome):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    choose_visibility(client, alice)
    response = client.patch(PREFS, json={"onboarding_status": outcome}, headers=alice)
    assert response.status_code == 409
    assert "trail time" in response.json()["detail"]
    # Nothing was saved: not the ending, not the step that came with it.
    assert client.get(PREFS, headers=alice).json()["onboarding"]["status"] is None
    assert pending(client, alice) is True
    # Clearing it in the same request as finishing doesn't get round it.
    choose_experience(client, alice)
    response = client.patch(PREFS, json={"experience": None, "onboarding_status": outcome}, headers=alice)
    assert response.status_code == 409
    assert client.get(PREFS, headers=alice).json()["experience"] == "few_seasons"


def test_experience_can_come_with_the_request_that_finishes(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    choose_visibility(client, alice)
    saved = patch_prefs(client, alice, experience="new", onboarding_step="done", onboarding_status="completed")
    assert saved["experience"] == "new" and saved["onboarding"]["status"] == "completed"
    assert pending(client, alice) is False


def test_experience_is_checked_before_visibility(client, people):
    """"Skip for now" leads to experience first, then the privacy step; the API asks in that order too."""
    _, alice = people["alice"]
    response = client.patch(PREFS, json={"onboarding_status": "skipped"}, headers=alice)
    assert response.status_code == 409 and "trail time" in response.json()["detail"]
    choose_experience(client, alice)
    response = client.patch(PREFS, json={"onboarding_status": "skipped"}, headers=alice)
    assert response.status_code == 409 and "public or private" in response.json()["detail"]


def test_people_who_finished_before_it_was_required_arent_sent_back(client, people, session_factory):
    """Finished or skipped without an experience level: still done, and they can set it in Settings."""
    from app.models.preferences import ProfilePreferences

    for name, outcome in (("alice", "completed"), ("bob", "skipped")):
        user_id, who = people[name]
        client.patch(PROFILE, json={"username": name}, headers=who)
        db = session_factory()
        db.add(ProfilePreferences(user_id=user_id, favourite_regions=[], onboarding_status=outcome,
                                  onboarding_finished_at=datetime.now(timezone.utc)))
        db.commit()
        db.close()
        assert pending(client, who) is False
        prefs = client.get(PREFS, headers=who).json()
        assert prefs["experience"] is None and prefs["onboarding"]["status"] == outcome
        # Settings → Trail preferences saves style, experience and regions together.
        saved = patch_prefs(client, who, hiking_style="day", experience="seasoned", favourite_regions=["banff"])
        assert saved["experience"] == "seasoned" and saved["onboarding"]["status"] == outcome
        # Saving with it still empty is fine for them too.
        assert patch_prefs(client, who, experience=None)["experience"] is None
        assert pending(client, who) is False


def test_preferences_are_only_your_own(client, people):
    _, alice = people["alice"]
    _, bob = people["bob"]
    patch_prefs(client, alice, hiking_style="overnight")
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
        for value in ("overnight", "seasoned", "tombstone", "kluane"):
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
            for secret in ("tombstone", "kluane", "seasoned"):
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


def test_picks_follow_style_experience_regions_and_home():
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
    from_bc = recommend(trails, Preferences(experience="few_seasons", home_province="BC"), limit=1)
    assert [t.name for t in from_bc] == ["Yoho Lake"]
    # Outside Canada matches no province, so it changes nothing.
    assert recommend(trails, Preferences(home_province="outside"), limit=4) == recommend(trails, Preferences(), limit=4)


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
    patch_prefs(client, alice, experience="new", hiking_style="day")
    assert names()[0] == "Easy falls"
    patch_prefs(client, alice, favourite_regions=["yoho"], experience="few_seasons")
    assert names()[0] == "Iceline"
    assert client.put(f"/api/me/saved-trails/{ids['yoho']}", headers=alice).status_code == 201
    assert "Iceline" not in names()
    assert "Retired lake" not in names()
    assert len(client.get(f"{RECS}?limit=1", headers=alice).json()) == 1


def test_region_list_has_unique_slugs_and_parks():
    assert len(set(REGION_SLUGS)) == len(REGIONS)
    assert len({region.park_name for region in REGIONS}) == len(REGIONS)


# ------------------------------------------------ the privacy choice is required


@pytest.mark.parametrize("outcome", ["completed", "skipped"])
def test_the_flow_cant_end_until_public_or_private_is_chosen(client, people, outcome):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    # Even with every other step done, and even via "Skip for now".
    patch_prefs(client, alice, experience="new", onboarding_step="privacy")
    refused = client.patch(PREFS, json={"onboarding_status": outcome}, headers=alice)
    assert refused.status_code == 409
    assert "public or private" in refused.json()["detail"]
    assert pending(client, alice) is True
    assert client.get(PREFS, headers=alice).json()["onboarding"]["status"] is None
    # Choosing, even the setting they already had, lets it end.
    choose_visibility(client, alice, is_private=True)
    assert patch_prefs(client, alice, onboarding_status=outcome)["onboarding"]["status"] == outcome
    assert pending(client, alice) is False


def test_other_privacy_switches_dont_count_as_the_choice(client, people):
    _, alice = people["alice"]
    client.patch(PROFILE, json={"username": "alice"}, headers=alice)
    choose_experience(client, alice)
    assert client.patch(PRIVACY, json={"show_rank": False}, headers=alice).status_code == 200
    refused = client.patch(PREFS, json={"onboarding_status": "completed"}, headers=alice)
    assert refused.status_code == 409 and "public or private" in refused.json()["detail"]


def test_saving_progress_doesnt_need_the_choice(client, people):
    _, alice = people["alice"]
    assert patch_prefs(client, alice, onboarding_step="hiked", hiking_style="day")["onboarding"]["step"] == "hiked"
