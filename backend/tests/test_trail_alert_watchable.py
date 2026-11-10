"""Which trails an availability alert can watch, as the trail endpoints report it.

The "Add an alert" dialog, Explore's cards and the trail page read
has_watchable_campgrounds (and how a trail is booked, to say why not) from the
trail endpoints, so the browser never fetches campgrounds per trail.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.backcountry.watchable import WATCHABLE_SITE, is_watchable
from app.models.backcountry import BackcountryPark, BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailBookingSystem, TrailCampground

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


@pytest.fixture
def trails(session_factory, client):
    """Overnight trails ranked by popularity, each linked to one kind of site."""
    db = session_factory()
    park = BackcountryPark(provider="parks_canada", provider_park_id="1", name="Jasper", province_code="AB",
                           region="Western", last_synced_at=NOW)
    db.add(park)
    db.flush()
    resource = iter(range(1, 100))

    def site(**overrides):
        values = dict(
            provider="parks_canada", provider_resource_id=str(-next(resource)), provider_location_id="-2147483638",
            provider_map_id="-2147483400", provider_booking_category_id="7", park_id=park.id, province_code="AB",
            booking_unit="Jasper - Backcountry", name="Site", raw_name="Site", kind="zone", is_publicly_listed=True,
            raw={}, last_synced_at=NOW,
        )
        values.update(overrides)
        row = BackcountrySite(**values)
        db.add(row)
        db.flush()
        return row

    def trail(rank, name, park_type, sites=(), booking=(), province="AB", covers="all"):
        row = Trail(name=name, region=f"Somewhere, {province}", country_code="CA", province_code=province,
                    park_name=f"{name} Park", park_type=park_type, terrain_difficulty="moderate",
                    typical_duration_nights=2, popularity_rank=rank)
        db.add(row)
        db.flush()
        for order, linked in enumerate(sites, start=1):
            db.add(TrailCampground(trail_id=row.id, site_id=linked.id, route_order=order, confidence="exact",
                                   source="test"))
        for position, (system, confirmed) in enumerate(booking):
            db.add(TrailBookingSystem(trail_id=row.id, system=system, covers=covers, confirmed=confirmed,
                                      position=position))
        return row

    rows = {
        # Most popular first, so "watchable first" visibly reorders them.
        "permit": trail(1, "West Coast Trail", "national", [site(kind="trail_permit")], [("parks_canada", True)]),
        "bc": trail(2, "Garibaldi Lake", "provincial", booking=[("bc_parks", True)], province="BC"),
        "skyline": trail(3, "Skyline Trail", "national", [site(), site(kind="trail_permit")], [("parks_canada", True)]),
        "retired": trail(4, "Retired Route", "national", [site(retired_at=NOW)], [("parks_canada", True)]),
        "unlisted": trail(5, "Unlisted Route", "national", [site(is_publicly_listed=False)]),
        "no_map": trail(6, "Grey Owl Trail", "national", [site(provider_map_id=None)], [("parks_canada", False)]),
        "unconfirmed": trail(7, "Grizzly Lake", "provincial", booking=[("yukon_parks", False)], province="YT"),
        "fcfs": trail(8, "Sunshine Coast Trail", "none", booking=[("none", True)], province="BC"),
        "egypt": trail(9, "Egypt Lake", "national", [site(provider_booking_category_id=None), site()]),
        "hut": trail(10, "Kokanee Glacier", "provincial", booking=[("bc_parks", False), ("alpine_club_of_canada", True)],
                     province="BC", covers="partial"),
    }
    db.commit()
    ids = {key: row.id for key, row in rows.items()}
    db.close()
    return ids


def by_name(items):
    return {item["name"]: item for item in items}


def test_trail_search_says_which_trails_alerts_can_watch(client, trails):
    found = by_name(client.get("/api/trails", params={"trip": "overnight", "limit": 20}).json())
    watchable = {name for name, item in found.items() if item["has_watchable_campgrounds"]}
    # Retired, unlisted, off-map and permit-only sites don't count; one good site is enough.
    assert watchable == {"Skyline Trail", "Egypt Lake"}


def test_trail_search_says_how_unwatchable_trails_are_booked(client, trails):
    found = by_name(client.get("/api/trails", params={"limit": 20}).json())
    assert found["Garibaldi Lake"]["booked_through"] == {"system": "bc_parks", "name": "BC Parks"}
    assert found["Sunshine Coast Trail"]["booked_through"]["system"] == "none"
    # An unconfirmed system isn't named.
    assert found["Grizzly Lake"]["booked_through"] is None
    assert found["Grey Owl Trail"]["booked_through"] is None
    # A system that books only part of the route (a hut) isn't named.
    assert found["Kokanee Glacier"]["booked_through"] is None
    # Parks Canada books the West Coast Trail as a permit, which alerts don't watch.
    assert found["West Coast Trail"]["trail_permit"] is True
    assert found["West Coast Trail"]["has_watchable_campgrounds"] is False
    assert found["Garibaldi Lake"]["trail_permit"] is False


def test_watchable_trails_sort_first_then_by_popularity(client, trails):
    names = [t["name"] for t in client.get("/api/trails", params={"sort": "watchable", "limit": 20}).json()]
    assert names[:2] == ["Skyline Trail", "Egypt Lake"]
    assert names[2:] == ["West Coast Trail", "Garibaldi Lake", "Retired Route", "Unlisted Route",
                         "Grey Owl Trail", "Grizzly Lake", "Sunshine Coast Trail", "Kokanee Glacier"]
    default = [t["name"] for t in client.get("/api/trails", params={"limit": 20}).json()]
    assert default[0] == "West Coast Trail"


def test_trail_search_filters_on_watchable(client, trails):
    only = client.get("/api/trails", params={"watchable": "true", "limit": 20}).json()
    assert {t["name"] for t in only} == {"Skyline Trail", "Egypt Lake"}
    without = client.get("/api/trails", params={"watchable": "false", "limit": 20}).json()
    assert len(without) == 8 and not any(t["has_watchable_campgrounds"] for t in without)
    # The limit applies after sorting, so a short list still leads with watchable trails.
    short = client.get("/api/trails", params={"sort": "watchable", "limit": 1}).json()
    assert [t["name"] for t in short] == ["Skyline Trail"]


def test_search_still_finds_unwatchable_trails(client, trails):
    found = client.get("/api/trails", params={"q": "garibaldi", "sort": "watchable"}).json()
    assert [(t["name"], t["has_watchable_campgrounds"]) for t in found] == [("Garibaldi Lake", False)]


def test_explore_search_and_trail_page_carry_the_field(client, trails):
    explore = by_name(client.post("/api/trails/search", json={"limit": 20}).json()["trails"])
    assert explore["Skyline Trail"]["has_watchable_campgrounds"] is True
    assert explore["Garibaldi Lake"]["has_watchable_campgrounds"] is False
    assert explore["Garibaldi Lake"]["booked_through"]["name"] == "BC Parks"

    page = client.get(f"/api/trails/{trails['skyline']}").json()
    assert page["has_watchable_campgrounds"] is True
    assert client.get(f"/api/trails/{trails['permit']}").json()["trail_permit"] is True


def test_campgrounds_say_which_ones_can_be_watched(client, trails):
    campgrounds = client.get(f"/api/trails/{trails['skyline']}/campgrounds").json()["campgrounds"]
    assert sorted((c["kind"], c["watchable"]) for c in campgrounds) == [("trail_permit", False), ("zone", True)]


def test_other_trail_lists_are_unchanged(client, trails):
    """Saved trails, hike logs and profiles share the list item but not the alert fields."""
    from app.schemas.trail import TrailListItemOut

    assert "has_watchable_campgrounds" not in TrailListItemOut.model_fields


def test_the_sql_rule_matches_the_python_rule(session_factory, trails):
    db = session_factory()
    sites = db.scalars(select(BackcountrySite)).all()
    in_sql = set(db.scalars(select(BackcountrySite.id).where(WATCHABLE_SITE)))
    assert {s.id for s in sites if is_watchable(s)} == in_sql
    assert 0 < len(in_sql) < len(sites)
    db.close()


def test_one_query_per_fact_not_per_trail(client, trails, engine):
    from sqlalchemy import event

    statements = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert len(client.get("/api/trails", params={"limit": 20}).json()) == 10
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    queries = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    # The trails (with their photos and route maps), then watchable, permits and
    # booking systems for all of them at once: never one per trail.
    assert len(queries) <= 6, queries
