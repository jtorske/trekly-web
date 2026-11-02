"""Points and ranks: the formula, the thresholds, the new-region bonus,
recalculation when a hike is deleted, and what visitors never see."""

import json

import pytest

from app.milestones import Facts, Hike
from app.milestones_config import TIER_POINTS
from app.models.trail import Trail
from app.points import next_rank, rank_for, score
from app.points_config import RANKS
from tests.test_featured_badges import alice, hike, people, trails  # noqa: F401  (fixtures)


def trail(terrain="easy", region="Banff National Park, AB", nights=0, km=None):
    return Trail(name="t", region=region, country_code="CA", terrain_difficulty=terrain,
                 typical_duration_nights=nights, distance_km=km)


def scored(*trails):
    """Points for hiking these trails, undated, with nothing else done."""
    return score(Facts(hikes=[Hike(t) for t in trails]))


# ------------------------------------------------------------ formula


def test_each_trail_scores_by_difficulty():
    for terrain, points in (("easy", 10), ("moderate", 20), ("difficult", 35), ("extreme", 50)):
        assert scored(trail(terrain)).trails == points


def test_overnights_add_ten_a_night():
    assert scored(trail(nights=3), trail(nights=0)).nights == 30


def test_first_trail_in_each_new_region_earns_the_bonus_once():
    same = scored(trail(region="Banff National Park, AB"), trail(region="Banff National Park, AB"))
    assert same.regions == 15
    two = scored(trail(region="Banff National Park, AB"), trail(region="Jasper National Park, AB"))
    assert two.regions == 30


def test_tier_points_are_bronze_10_silver_25_gold_50():
    assert TIER_POINTS == {"bronze": 10, "silver": 25, "gold": 50}


def test_milestones_score_by_tier():
    # First steps (bronze).
    assert scored(trail()).milestones == 10
    # + Under the stars (bronze).
    assert scored(trail(nights=1)).milestones == 20
    # + Long weekend (silver).
    assert scored(trail(nights=3)).milestones == 10 + 10 + 25
    # + Week in the wild (gold); 6 nights is short of Backcountry regular's 10.
    assert scored(trail(nights=6)).milestones == 10 + 10 + 25 + 50
    # First steps + Park hopper (bronze) + Century (bronze); none overnight.
    five = [trail(region=f"Park {i}", km=20) for i in range(5)]
    assert scored(*five).milestones == 10 * 3
    # Planning milestones score too, with no hikes at all: Planner + Permit hunter (bronze), Lucky break (silver).
    assert score(Facts(plans=1, alerts=1, alert_notified=True)).milestones == 10 + 10 + 25


def test_nothing_hiked_is_zero():
    assert score(Facts()).total == 0


def test_total_adds_the_parts():
    points = scored(trail("moderate", nights=2), trail("easy", region="Jasper National Park, AB"))
    # 20 + 10 trails, 20 nights, 2 regions, First steps + Under the stars (bronze each).
    assert (points.trails, points.nights, points.regions, points.milestones) == (30, 20, 30, 20)
    assert points.total == 100


# ------------------------------------------------------------ thresholds


def test_ranks_start_at_zero_and_only_go_up():
    thresholds = [threshold for threshold, _ in RANKS]
    assert thresholds[0] == 0
    assert thresholds == sorted(set(thresholds))


@pytest.mark.parametrize(
    "points, level, title",
    [(0, 1, "Trailhead Rookie"), (49, 1, "Trailhead Rookie"), (50, 2, "Day Tripper"), (249, 2, "Day Tripper"),
     (250, 3, "Switchback Regular"), (600, 4, "Ridge Walker"), (1100, 5, "Backcountry Ranger"),
     (1799, 5, "Backcountry Ranger"), (1800, 6, "Summit Seeker"), (2800, 7, "Mountain Legend"),
     (99999, 7, "Mountain Legend")],
)
def test_rank_thresholds(points, level, title):
    rank = rank_for(points)
    assert (rank.level, rank.title) == (level, title)


def test_next_rank_and_the_top():
    assert next_rank(rank_for(120)).title == "Switchback Regular"
    assert next_rank(rank_for(2800)) is None


# ------------------------------------------------------------ the API


def test_my_rank_reports_points_progress_and_next_rank(client, alice):  # noqa: F811
    body = client.get("/api/me/rank", headers=alice).json()
    # Agnes easy 10, Skyline moderate 20 + 2 nights, Sentinel difficult 35, Garibaldi moderate 20;
    # 3 regions; First steps, Under the stars, Monthly regular (June to September: bronze 10 each)
    # and the secret Skyline (silver 25).
    assert body["breakdown"] == {"trails": 85, "nights": 20, "regions": 45, "milestones": 55}
    assert body["points"] == 205
    assert body["rank"] == {"level": 2, "title": "Day Tripper", "threshold": 50}
    assert body["next"] == {"level": 3, "title": "Switchback Regular", "threshold": 250}
    assert body["progress"] == 0.775


def test_rank_is_recalculated_when_a_hike_is_deleted(client, alice, trails):  # noqa: F811
    assert client.delete(f"/api/me/hike-logs/{trails['skyline']}", headers=alice).status_code == 204
    body = client.get("/api/me/rank", headers=alice).json()
    # Skyline's 20 for the trail and 20 for its nights go, with its region (15), Under the stars (10),
    # Skyline (25), and Monthly regular (10): June, August, September is no longer three in a row.
    assert body["points"] == 205 - 20 - 20 - 15 - 10 - 25 - 10
    for trail_id in (trails["sentinel"], trails["garibaldi"], trails["agnes"]):
        client.delete(f"/api/me/hike-logs/{trail_id}", headers=alice)
    body = client.get("/api/me/rank", headers=alice).json()
    assert body["points"] == 0 and body["rank"]["title"] == "Trailhead Rookie"


def test_new_hikes_count_at_once(client, people, trails):  # noqa: F811
    bob = people["bob"]
    assert client.get("/api/me/rank", headers=bob).json()["points"] == 0
    hike(client, bob, trails["wilcox"], "2026-08-01")
    # Easy 10 + a new region 15 + First steps 10.
    assert client.get("/api/me/rank", headers=bob).json()["points"] == 35


def test_my_rank_needs_signing_in(client, trails):  # noqa: F811
    assert client.get("/api/me/rank").status_code == 401


def test_rank_rules_are_public_and_match_the_config(client):
    body = client.get("/api/ranks").json()
    assert body["trail_points"] == {"easy": 10, "moderate": 20, "difficult": 35, "extreme": 50}
    assert (body["points_per_night"], body["new_region_points"]) == (10, 15)
    assert body["tier_points"] == {"bronze": 10, "silver": 25, "gold": 50}
    assert [(r["threshold"], r["title"]) for r in body["ranks"]] == list(RANKS)


# ------------------------------------------------------------ visitors


@pytest.fixture
def alice_public(client, alice):  # noqa: F811
    assert client.patch("/api/me/profile", json={"username": "alice"}, headers=alice).status_code == 200
    assert client.get("/api/me/privacy", headers=alice).status_code == 200
    return alice


def test_visitors_get_the_rank_name_only_never_points(client, alice_public):
    body = client.get("/api/profiles/alice").json()
    assert body["rank"] == {"level": 2, "title": "Day Tripper"}
    text = json.dumps(body)
    for leak in ('"points"', '"progress"', '"breakdown"', '"threshold"', '"next"'):
        assert leak not in text


def test_a_hidden_rank_is_not_sent_at_all(client, alice_public):
    assert client.patch("/api/me/privacy", json={"show_rank": False}, headers=alice_public).status_code == 200
    body = client.get("/api/profiles/alice").json()
    assert body["rank"] is None
    assert "Day Tripper" not in json.dumps(body)
    # The owner still has theirs.
    assert client.get("/api/me/rank", headers=alice_public).json()["rank"]["title"] == "Day Tripper"


def test_a_private_profile_sends_no_rank(client, alice_public):
    assert client.patch("/api/me/privacy", json={"is_private": True}, headers=alice_public).status_code == 200
    assert client.get("/api/profiles/alice").json()["rank"] is None
