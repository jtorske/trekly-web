import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.account import SavedTrail
from app.models.trail import TERRAIN_DIFFICULTIES, Trail
from app.models.trail_seasonal_condition import TrailSeasonalCondition
from app.trail_catalog import load_catalog, popularity_score, sync_trails

CA_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}


def entry(rank, name=None, country="CA", province="AB", **overrides):
    row = dict(
        rank=rank, name=name or f"Trail {rank:03d}", country_code=country, province_code=province,
        region=f"Somewhere, {province}", latitude=51.0 + rank / 1000, longitude=-116.0,
        elevation_gain_m=500, max_elevation_m=2000, terrain_difficulty="moderate",
        typical_duration_nights=0, climate_zone="alpine", description=None,
    )
    row.update(overrides)
    return row


def catalog(entries):
    return {"meta": {"popularity_source": "editorial"}, "trails": entries}


# 105 Canadian entries (more than the cap) plus US entries that must never show.
SAMPLE = catalog(
    [entry(rank) for rank in range(1, 106)]
    + [entry(200, "Half Dome", country="US", province="CA"), entry(201, "Old Rag", country="US", province="VA")]
)


@pytest.fixture
def legacy_us_trail(session_factory, client):
    """A pre-existing US trail with a bookmark and seasonal conditions."""
    session = session_factory()
    trail = Trail(name="Wonderland Trail", region="Washington", country_code="US", province_code="WA",
                  terrain_difficulty="extreme")
    session.add(trail)
    session.flush()
    user_id = uuid.uuid4()
    session.add(SavedTrail(user_id=user_id, trail_id=trail.id))
    session.add(TrailSeasonalCondition(trail_id=trail.id, season="summer", avg_low_c=5, avg_high_c=20))
    session.commit()
    trail_id = trail.id
    session.close()
    return trail_id, user_id


@pytest.fixture
def synced(session_factory, client, legacy_us_trail):
    session = session_factory()
    result = sync_trails(session, SAMPLE, countries=("CA",), limit=100)
    session.commit()
    session.close()
    return result


def test_sync_keeps_top_canadian_trails_and_retires_the_rest(session_factory, synced, legacy_us_trail):
    session = session_factory()
    live = session.query(Trail).filter(Trail.retired_at.is_(None)).all()
    assert len(live) == 100
    assert {t.country_code for t in live} == {"CA"}
    assert sorted(t.popularity_rank for t in live) == list(range(1, 101))
    assert {t.popularity_source for t in live} == {"editorial"}
    # Out-of-top-100 Canadian entries and US entries are never inserted.
    assert session.query(Trail).filter(Trail.name.in_(["Trail 101", "Half Dome"])).count() == 0
    assert len(synced.inserted) == 100


def test_sync_retires_instead_of_deleting_so_references_survive(session_factory, synced, legacy_us_trail):
    trail_id, user_id = legacy_us_trail
    session = session_factory()
    trail = session.get(Trail, trail_id)
    assert trail is not None and trail.retired_at is not None and trail.popularity_rank is None
    assert session.get(SavedTrail, (user_id, trail_id)) is not None
    assert session.query(TrailSeasonalCondition).filter_by(trail_id=trail_id).count() == 1
    assert synced.retired == ["Wonderland Trail (Washington)"]


def test_sync_is_idempotent(session_factory, synced):
    session = session_factory()
    again = sync_trails(session, SAMPLE, countries=("CA",), limit=100,
                        now=datetime(2030, 1, 1, tzinfo=timezone.utc))
    session.commit()
    assert (again.inserted, again.updated, again.retired, again.unchanged) == ([], [], [], 100)
    assert session.query(Trail).count() == 101  # 100 live + the retired legacy trail


def test_sync_updates_existing_rows_matched_on_name_and_province(session_factory, client):
    session = session_factory()
    existing = Trail(name="Trail 001", region="Old region text", country_code="CA", province_code="AB",
                     terrain_difficulty="easy", retired_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    session.add(existing)
    session.commit()
    original_id = existing.id

    result = sync_trails(session, SAMPLE, countries=("CA",), limit=100)
    session.commit()
    assert "Trail 001" in result.updated
    refreshed = session.query(Trail).filter_by(name="Trail 001").one()
    assert refreshed.id == original_id
    assert (refreshed.region, refreshed.terrain_difficulty, refreshed.retired_at) == ("Somewhere, AB", "moderate", None)


def test_limit_and_countries_are_configurable(session_factory, client):
    session = session_factory()
    sync_trails(session, SAMPLE, countries=("CA", "US"), limit=200)
    session.commit()
    live = session.query(Trail).filter(Trail.retired_at.is_(None))
    assert live.count() == 107
    assert live.filter(Trail.country_code == "US").count() == 2

    sync_trails(session, SAMPLE, countries=("CA",), limit=5)
    session.commit()
    assert [t.name for t in live.order_by(Trail.popularity_rank)] == [f"Trail {i:03d}" for i in range(1, 6)]


def test_popularity_score_is_derived_from_rank():
    assert popularity_score(1, 100) == 1
    assert popularity_score(100, 100) == Decimal("0.01")
    assert popularity_score(10, 100) > popularity_score(11, 100)


def test_list_returns_only_canadian_trails_capped_at_100_ordered_by_popularity(client, synced):
    response = client.get("/api/trails", params={"limit": 100})
    assert response.status_code == 200
    trails = response.json()
    assert len(trails) == 100
    assert {t["country_code"] for t in trails} == {"CA"}
    assert [t["popularity_rank"] for t in trails] == list(range(1, 101))
    assert all(t["retired_at"] is None for t in trails)

    assert client.get("/api/trails", params={"limit": 101}).status_code == 422
    assert [t["name"] for t in client.get("/api/trails").json()] == [f"Trail {i:03d}" for i in range(1, 11)]


def test_list_search_keeps_popularity_order_and_hides_retired(client, synced):
    names = [t["name"] for t in client.get("/api/trails", params={"q": "Trail 09", "limit": 100}).json()]
    assert names == [f"Trail {i:03d}" for i in range(90, 100)]
    assert client.get("/api/trails", params={"q": "Wonderland"}).json() == []


def test_list_search_treats_wildcards_as_plain_text(client, session_factory, legacy_us_trail):
    session = session_factory()
    sync_trails(
        session,
        catalog([entry(1, "Lake Agnes"), entry(2, "100% Ridge"), entry(3, "Snake_Path"), entry(4, "Back\\Slash")]),
        countries=("CA",),
        limit=100,
    )
    session.commit()
    session.close()

    def search(q):
        return [t["name"] for t in client.get("/api/trails", params={"q": q, "limit": 100}).json()]

    assert search("%") == ["100% Ridge"]
    assert search("_") == ["Snake_Path"]
    assert search("\\") == ["Back\\Slash"]
    assert search("e_p") == ["Snake_Path"]
    assert search("ag%es") == []


def test_retired_trail_detail_and_bookmark_still_resolve(client, synced, legacy_us_trail, auth_headers):
    trail_id, user_id = legacy_us_trail
    detail = client.get(f"/api/trails/{trail_id}")
    assert detail.status_code == 200
    assert detail.json()["retired_at"] is not None
    assert len(detail.json()["seasonal_conditions"]) == 1

    saved = client.get("/api/me/saved-trails", headers=auth_headers(user_id)).json()
    assert [row["trail"]["name"] for row in saved] == ["Wonderland Trail"]


def test_shipped_catalogue_is_valid():
    data = load_catalog()
    trails = data["trails"]
    assert data["meta"]["popularity_source"] == "editorial"
    assert len(trails) == 100
    assert sorted(t["rank"] for t in trails) == list(range(1, 101))
    assert len({(t["name"], t["province_code"]) for t in trails}) == 100
    for t in trails:
        assert t["country_code"] == "CA", t["name"]
        assert t["province_code"] in CA_PROVINCES, t["name"]
        assert t["terrain_difficulty"] in TERRAIN_DIFFICULTIES, t["name"]
        assert 41.6 <= t["latitude"] <= 83.2 and -141.1 <= t["longitude"] <= -52.6, t["name"]
        # Route type and distance are set together, and only with a source.
        if t["distance_km"] is None:
            assert t["route_type"] is None and t["verification"]["distance_km"] is None, t["name"]
        else:
            assert 0 < t["distance_km"] < 1000, t["name"]
            assert t["route_type"] in ("out_and_back", "loop", "point_to_point"), t["name"]
            source = t["verification"]["distance_km"]
            assert source.get("osm") or source.get("osm_named_ways"), t["name"]
            # An out-and-back shows the round trip: twice the mapped length.
            factor = 2 if t["route_type"] == "out_and_back" else 1
            assert abs(t["distance_km"] - source["mapped_km"] * factor) < 0.06, t["name"]
    assert any(t["name"] == "West Coast Trail" for t in trails)


def test_shipped_catalogue_parks_are_classified():
    trails = load_catalog()["trails"]
    for t in trails:
        assert t["park_type"] in ("national", "provincial", "regional", "none"), t["name"]
        if t["park_type"] != "none":
            assert t["park_name"], t["name"]
    by_name = {t["name"]: t for t in trails}
    assert (by_name["Lake Agnes Tea House"]["park_name"], by_name["Lake Agnes Tea House"]["park_type"]) == (
        "Banff National Park", "national")
    # Quebec's parcs nationaux are provincial parks.
    assert all(t["park_type"] == "provincial" for t in trails if t["region"].startswith("Parc national"))
    # Locals search by Kananaskis, so it stands in for the parks inside it.
    assert all(
        (t["park_name"], t["park_type"]) == ("Kananaskis Country", "provincial")
        for t in trails if t["region"].startswith("Kananaskis Country")
    )
    signal_hill = next(t for t in trails if t["region"].startswith("Signal Hill"))
    assert (signal_hill["park_name"], signal_hill["park_type"]) == ("Signal Hill National Historic Site", "none")


def test_list_filters_by_trip_type(client, synced, session_factory):
    session = session_factory()
    for trail in session.query(Trail).filter(Trail.name.in_(["Trail 002", "Trail 005"])):
        trail.typical_duration_nights = 2
    session.query(Trail).filter(Trail.name == "Trail 007").one().typical_duration_nights = None
    session.commit()
    session.close()

    def names(**params):
        return [t["name"] for t in client.get("/api/trails", params={"limit": 100, **params}).json()]

    assert names(trip="overnight") == ["Trail 002", "Trail 005"]
    day = names(trip="day")
    assert "Trail 002" not in day and "Trail 007" not in day and len(day) == 97
    assert names(trip="overnight", q="Trail 005") == ["Trail 005"]
    assert names(trip="overnight", terrain="extreme") == []
    assert client.get("/api/trails", params={"trip": "weekend"}).status_code == 422


PARK_ROWS = [
    # rank, name, province, park, park type, terrain, nights, lat, lng
    (1, "Lake Agnes", "AB", "Banff National Park", "national", "easy", 0, 51.42, -116.21),
    (2, "Sulphur Skyline", "AB", "Jasper National Park", "national", "moderate", 0, 52.97, -117.68),
    (3, "Rawson Lake", "AB", "Kananaskis Country", "provincial", "moderate", 0, 50.62, -115.16),
    (4, "Joffre Lakes", "BC", "Joffre Lakes Provincial Park", "provincial", "moderate", 0, 50.37, -122.50),
    (5, "Berg Lake", "BC", "Mount Robson Provincial Park", "provincial", "difficult", 3, 53.04, -119.21),
    (6, "Grouse Grind", "BC", "Grouse Mountain Regional Park", "regional", "difficult", 0, 49.38, -123.08),
    (7, "Mount Cheam", "BC", None, "none", "moderate", 0, 49.17, -121.68),
    (8, "Signal Hill", "NL", "Signal Hill National Historic Site", "none", "easy", 0, 47.57, -52.68),
]


@pytest.fixture
def parks_catalogue(session_factory, client):
    session = session_factory()
    sync_trails(
        session,
        catalog([
            entry(rank, name, province=province, park_name=park, park_type=kind, terrain_difficulty=terrain,
                  typical_duration_nights=nights, latitude=lat, longitude=lng)
            for rank, name, province, park, kind, terrain, nights, lat, lng in PARK_ROWS
        ]),
        countries=("CA",),
        limit=100,
    )
    session.commit()
    session.close()


def search(client, **body):
    response = client.post("/api/trails/search", json={"limit": 100, **body})
    assert response.status_code == 200, response.text
    return response.json()


def result_names(result):
    return [t["name"] for t in result["trails"]]


def counts_by(facet, key):
    return {option[key]: option["count"] for option in facet}


def test_sync_copies_park_fields(session_factory, parks_catalogue):
    session = session_factory()
    trail = session.query(Trail).filter_by(name="Rawson Lake").one()
    assert (trail.park_name, trail.park_type) == ("Kananaskis Country", "provincial")
    session.close()


def test_list_filters_by_province_park_type_and_park(client, parks_catalogue):
    def listed(**params):
        return [t["name"] for t in client.get("/api/trails", params={"limit": 100, **params}).json()]

    assert listed(province="NL") == ["Signal Hill"]
    assert listed(province=["NL", "ab"]) == ["Lake Agnes", "Sulphur Skyline", "Rawson Lake", "Signal Hill"]
    assert listed(park_type="national") == ["Lake Agnes", "Sulphur Skyline"]
    # "other" is regional parks plus trails in no park.
    assert listed(park_type="other") == ["Grouse Grind", "Mount Cheam", "Signal Hill"]
    assert listed(park_type=["national", "other"], province="BC") == ["Grouse Grind", "Mount Cheam"]
    assert listed(park=["Banff National Park", "Signal Hill National Historic Site"]) == ["Lake Agnes", "Signal Hill"]
    assert listed(q="kananaskis") == ["Rawson Lake"]
    assert client.get("/api/trails", params={"park_type": "regional"}).status_code == 422
    first = client.get("/api/trails", params={"limit": 1}).json()[0]
    assert (first["park_name"], first["park_type"]) == ("Banff National Park", "national")


def test_search_combines_filters_with_trip_terrain_and_query(client, parks_catalogue):
    assert result_names(search(client, provinces=["BC"], terrain="moderate")) == ["Joffre Lakes", "Mount Cheam"]
    assert result_names(search(client, park_types=["provincial"], trip="overnight")) == ["Berg Lake"]
    assert result_names(search(client, q="lake", provinces=["AB"], park_types=["national"])) == ["Lake Agnes"]
    empty = search(client, parks=["Banff National Park"], provinces=["BC"])
    assert (empty["trails"], empty["total"]) == ([], 0)


def test_search_total_counts_past_the_limit(client, parks_catalogue):
    result = search(client, provinces=["BC"], limit=2)
    assert result_names(result) == ["Joffre Lakes", "Berg Lake"]
    assert result["total"] == 4


def test_facet_counts_apply_every_other_filter(client, parks_catalogue):
    facets = search(client)["facets"]
    assert facets["provinces"] == [{"code": "AB", "count": 3}, {"code": "BC", "count": 4}, {"code": "NL", "count": 1}]
    assert facets["park_types"] == [
        {"type": "national", "count": 2}, {"type": "provincial", "count": 3}, {"type": "other", "count": 3}]
    assert [p["name"] for p in facets["parks"]] == [
        "Banff National Park", "Grouse Mountain Regional Park", "Jasper National Park", "Joffre Lakes Provincial Park",
        "Kananaskis Country", "Mount Robson Provincial Park", "Signal Hill National Historic Site"]
    assert facets["parks"][-1] == {
        "name": "Signal Hill National Historic Site", "park_type": "none", "province_codes": ["NL"], "count": 1}

    # Picking Alberta leaves the province counts alone (their own filter is
    # left out) but narrows every other facet; options at 0 stay listed.
    facets = search(client, provinces=["AB"])["facets"]
    assert counts_by(facets["provinces"], "code") == {"AB": 3, "BC": 4, "NL": 1}
    assert counts_by(facets["park_types"], "type") == {"national": 2, "provincial": 1, "other": 0}
    parks = counts_by(facets["parks"], "name")
    assert parks["Banff National Park"] == 1 and parks["Joffre Lakes Provincial Park"] == 0
    assert len(parks) == 7

    # Two filters at once: each facet sees the other one, plus terrain.
    facets = search(client, provinces=["BC"], park_types=["provincial"], terrain="moderate")["facets"]
    assert counts_by(facets["provinces"], "code") == {"AB": 1, "BC": 1, "NL": 0}
    assert counts_by(facets["park_types"], "type") == {"national": 0, "provincial": 1, "other": 1}
    parks = counts_by(facets["parks"], "name")
    assert parks["Joffre Lakes Provincial Park"] == 1 and parks["Kananaskis Country"] == 0

    # The park facet leaves out the park filter, so other parks stay pickable.
    facets = search(client, parks=["Banff National Park"])["facets"]
    assert counts_by(facets["parks"], "name")["Jasper National Park"] == 1
    assert counts_by(facets["provinces"], "code") == {"AB": 1, "BC": 0, "NL": 0}


def test_near_filters_by_radius_and_reports_distance(client, parks_catalogue):
    canmore = {"lat": 51.09, "lng": -115.36}
    everything = search(client, near=canmore)
    assert everything["total"] == 8
    away = {t["name"]: t["distance_away_km"] for t in everything["trails"]}
    assert 55 < away["Lake Agnes"] < 75 and away["Signal Hill"] > 4000

    near = search(client, near={**canmore, "radius_km": 100})
    assert result_names(near) == ["Lake Agnes", "Rawson Lake"]
    assert near["total"] == 2
    # The radius narrows the counts too.
    assert counts_by(near["facets"]["provinces"], "code") == {"AB": 2, "BC": 0, "NL": 0}
    assert result_names(search(client, near={**canmore, "radius_km": 100}, park_types=["provincial"])) == [
        "Rawson Lake"]

    assert search(client)["trails"][0]["distance_away_km"] is None
    for bad in ({"lat": 91, "lng": 0}, {"lat": 0, "lng": 0, "radius_km": 0}):
        assert client.post("/api/trails/search", json={"near": bad}).status_code == 422


def test_search_hides_retired_trails_from_results_and_facets(client, parks_catalogue, legacy_us_trail):
    result = search(client, q="Wonderland")
    assert result["total"] == 0
    assert "WA" not in {p["code"] for p in result["facets"]["provinces"]}
