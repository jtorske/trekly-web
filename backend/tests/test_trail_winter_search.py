"""Explore's winter mode: season filter, winter-first order, activity and ATES filters, API fields."""

import pytest

from app.models.trail import Trail

ATES = "https://parks.canada.ca/ates"
SRC = "https://parks.canada.ca/winter"


@pytest.fixture
def winter_catalogue(session_factory, client):
    session = session_factory()
    rows = [
        # (rank, name, activities, ates, tags)
        (1, "Summer Classic", [], "unknown", []),
        (2, "Rated Pass", [], "challenging", []),
        (3, "Ski Touring Approach", [], "simple", []),  # rated Simple but not a winter route
        (4, "Snowshoe Lake", ["snowshoe"], "simple", []),
        (5, "Winter Walk", ["winter_hike"], "unknown", []),
        (6, "Groomed Road", ["xc_ski", "snowshoe"], "simple", ["winter_only"]),
    ]
    for rank, name, acts, ates, tags in rows:
        session.add(Trail(
            name=name, region="Banff National Park, AB", country_code="CA", province_code="AB",
            terrain_difficulty="easy", popularity_rank=rank, latitude=51.2, longitude=-115.6,
            winter_activities=acts, avalanche_exposure=ates,
            avalanche_source_url=ATES if ates != "unknown" else None,
            winter_source_url=SRC if acts else None, tags=tags,
        ))
    session.commit()
    session.close()


def names(response):
    body = response.json()
    trails = body["trails"] if isinstance(body, dict) else body
    return [t["name"] for t in trails]


def test_no_season_lists_everything_by_popularity(client, winter_catalogue):
    assert names(client.get("/api/trails", params={"limit": 10})) == [
        "Summer Classic", "Rated Pass", "Ski Touring Approach", "Snowshoe Lake", "Winter Walk", "Groomed Road"]


def test_summer_hides_winter_only_trails(client, winter_catalogue):
    listed = names(client.get("/api/trails", params={"limit": 10, "season": "summer"}))
    assert "Groomed Road" not in listed and len(listed) == 5
    body = client.post("/api/trails/search", json={"limit": 10, "season": "summer"}).json()
    assert body["total"] == 5


def test_winter_lists_winter_trails_first(client, winter_catalogue):
    assert names(client.get("/api/trails", params={"limit": 10, "season": "winter"})) == [
        "Snowshoe Lake", "Winter Walk", "Groomed Road", "Summer Classic", "Rated Pass", "Ski Touring Approach"]
    assert names(client.post("/api/trails/search", json={"limit": 10, "season": "winter"}))[:3] == [
        "Snowshoe Lake", "Winter Walk", "Groomed Road"]


def test_activity_filter_matches_any(client, winter_catalogue):
    snow = names(client.get("/api/trails", params={"limit": 10, "winter_activity": "snowshoe"}))
    assert snow == ["Snowshoe Lake", "Groomed Road"]
    either = client.post("/api/trails/search", json={"limit": 10, "winter_activities": ["xc_ski", "winter_hike"]})
    assert names(either) == ["Winter Walk", "Groomed Road"]


def test_simple_terrain_never_includes_unknown_or_non_winter_trails(client, winter_catalogue):
    listed = names(client.get("/api/trails", params={"limit": 10, "simple_terrain": True}))
    assert listed == ["Snowshoe Lake", "Groomed Road"]
    assert "Winter Walk" not in listed          # unknown exposure
    assert "Ski Touring Approach" not in listed  # Simple, but not recommended in winter
    body = client.post("/api/trails/search", json={"limit": 10, "simple_terrain": True, "season": "winter"}).json()
    assert [t["name"] for t in body["trails"]] == ["Snowshoe Lake", "Groomed Road"] and body["total"] == 2


def test_list_items_carry_winter_fields(client, winter_catalogue):
    trails = {t["name"]: t for t in client.get("/api/trails", params={"limit": 10}).json()}
    assert trails["Groomed Road"]["winter_activities"] == ["xc_ski", "snowshoe"]
    assert trails["Groomed Road"]["winter_only"] is True
    assert trails["Summer Classic"]["avalanche_exposure"] == "unknown"
    assert trails["Summer Classic"]["winter_activities"] == []
    assert trails["Summer Classic"]["winter_only"] is False


def test_detail_carries_winter_details(client, session_factory, winter_catalogue):
    session = session_factory()
    trail = session.query(Trail).filter_by(name="Snowshoe Lake").one()
    trail.winter_notes, trail.winter_report_url = "Icy at the start.", "https://parks.canada.ca/conditions"
    trail.winter_route_ends = "The lake (3 km return)."
    session.commit()
    trail_id = trail.id
    session.close()
    detail = client.get(f"/api/trails/{trail_id}").json()
    assert detail["avalanche_exposure"] == "simple" and detail["avalanche_source_url"] == ATES
    assert detail["winter_notes"] == "Icy at the start."
    assert detail["winter_report_url"] == "https://parks.canada.ca/conditions"
    assert detail["winter_route_ends"] == "The lake (3 km return)."
    assert detail["winter_source_url"] == SRC


def test_bad_filter_values_are_rejected(client, winter_catalogue):
    assert client.get("/api/trails", params={"season": "fall"}).status_code == 422
    assert client.get("/api/trails", params={"winter_activity": "ski_touring"}).status_code == 422
