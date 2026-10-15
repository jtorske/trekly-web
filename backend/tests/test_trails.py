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
    assert any(t["name"] == "West Coast Trail" for t in trails)
