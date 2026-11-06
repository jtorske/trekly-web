"""Trail route data: the routes file, the catalogue overlay, the DB sync and the route endpoint."""

import importlib.util
import json
from pathlib import Path

import pytest

from app import trail_routes
from app.models.trail import Trail
from app.trail_catalog import sync_trails
from tests.test_trails import catalog, entry

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trail_routes.py"
spec = importlib.util.spec_from_file_location("trail_routes_script", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def proposal(**overrides):
    """A built trail as scripts/trail_routes.py build writes it."""
    row = {
        "key": "rawson-lake-ab", "name": "Rawson Lake", "province_code": "AB", "rank": 1, "nights": 0,
        "notes": [], "flags": [], "choice_flags": [], "osm_ways": [123, 456], "osm_relations": [],
        "measured": {"distance_km": 7.9, "route_type": "out_and_back", "elevation_gain_m": 330,
                     "max_elevation_m": 2014, "trailhead_m": 1714},
        "final": {
            "distance_km": {"value": 7.9, "kind": "measured", "source": "OSM paths + NRCan MRDEM",
                            "published": {"value": 7.8, "url": "https://example.test/rawson"}},
            "route_type": {"value": "out_and_back", "kind": "measured", "source": "OSM paths + NRCan MRDEM"},
            "elevation_gain_m": {"value": 330, "kind": "measured", "source": "OSM paths + NRCan MRDEM"},
            "max_elevation_m": {"value": 2014, "kind": "measured", "source": "OSM paths + NRCan MRDEM"},
        },
        "geometry": [[50.6175, -115.1255], [50.5919, -115.1514]],
        "high_point": [50.5919, -115.1514, 2014],
        "profile": [[0.0, 1714], [3.9, 2014]],
    }
    row.update(overrides)
    return row


def test_route_entry_keeps_sources_and_route():
    route = script.route_entry(proposal())
    assert route["distance_km"] == 7.9 and route["elevation_gain_m"] == 330
    assert route["sources"]["distance_km"] == {
        "kind": "measured", "method": "OSM paths + NRCan MRDEM", "url": "https://www.openstreetmap.org/way/123",
        "published": {"value": 7.8, "url": "https://example.test/rawson"},
    }
    assert route["sources"]["max_elevation_m"]["elevation_url"].endswith("mrdem-30-dtm.tif")
    assert route["route"]["trailhead"] == [50.6175, -115.1255, 1714]
    assert route["route"]["profile"][-1] == [3.9, 2014]


def test_suspect_geometry_has_no_route_and_published_sources():
    suspect = proposal(
        choice_flags=["geometry doesn't match the published length; measured elevations not used"],
        final={"distance_km": {"value": 24.6, "kind": "published", "source": "https://example.test/park", "measured": 10.1},
               "route_type": {"value": "loop", "kind": "measured", "source": "OSM paths"}},
    )
    route = script.route_entry(suspect)
    assert route["route"] is None
    assert route["sources"]["distance_km"] == {"kind": "published", "url": "https://example.test/park", "measured": 10.1}
    assert "elevation_gain_m" not in route


def test_lake_ohara_description_mentions_the_road_walk():
    route = script.route_entry(proposal(key="elizabeth-parker-hut-lake-o-hara-bc"))
    assert "11 km road" in route["description"]


def test_catalogue_sync_overlays_route_measures(db):
    routes = {("Trail 001", "AB"): {"distance_km": 12.3, "route_type": "loop", "elevation_gain_m": 640,
                                    "max_elevation_m": 2410, "description": "Updated."}}
    sync_trails(db, catalog([entry(1), entry(2)]), countries=("CA",), limit=100, routes=routes)
    one = db.query(Trail).filter_by(name="Trail 001").one()
    two = db.query(Trail).filter_by(name="Trail 002").one()
    assert (float(one.distance_km), one.route_type, one.elevation_gain_m, one.max_elevation_m) == (12.3, "loop", 640, 2410)
    assert one.description == "Updated."
    assert two.elevation_gain_m == 500  # untouched: no route entry


def test_sync_db_updates_matches_only_and_never_retires(db):
    sync_trails(db, catalog([entry(1), entry(2)]), countries=("CA",), limit=100)
    trails = {"a": {"name": "Trail 001", "province_code": "AB", "distance_km": 9.4, "route_type": "out_and_back",
                    "elevation_gain_m": 777, "max_elevation_m": 2222},
              "b": {"name": "Not In The Database", "province_code": "AB", "distance_km": 1.0}}
    changed = script.sync_db(db, trails)
    assert [name for name, _ in changed] == ["Trail 001"]
    assert db.query(Trail).filter(Trail.retired_at.isnot(None)).count() == 0
    again = script.sync_db(db, trails)
    assert again == []  # idempotent


@pytest.fixture
def routes_file(tmp_path, monkeypatch):
    path = tmp_path / "trail_routes.json"
    path.write_text(json.dumps({"meta": {}, "trails": {"x": script.route_entry(proposal(name="Trail 001"))}}),
                    encoding="utf-8")
    trail_routes.load_routes.cache_clear()
    trail_routes.routes_by_name.cache_clear()
    original = trail_routes.route_for
    monkeypatch.setattr("app.routers.trails.route_for", lambda name, province: original(name, province, path))
    yield path
    trail_routes.load_routes.cache_clear()
    trail_routes.routes_by_name.cache_clear()


def test_route_endpoint(client, session_factory, routes_file):
    session = session_factory()
    sync_trails(session, catalog([entry(1), entry(2)]), countries=("CA",), limit=100)
    session.commit()
    measured = session.query(Trail).filter_by(name="Trail 001").one().id
    other = session.query(Trail).filter_by(name="Trail 002").one().id
    session.close()

    body = client.get(f"/api/trails/{measured}/route").json()
    assert body["line"][0] == [50.6175, -115.1255]
    assert body["high_point"] == [50.5919, -115.1514, 2014]
    assert body["sources"]["distance_km"]["kind"] == "measured"

    empty = client.get(f"/api/trails/{other}/route").json()
    assert empty == {"line": None, "trailhead": None, "high_point": None, "profile": [], "sources": {}}
    assert client.get("/api/trails/00000000-0000-0000-0000-000000000000/route").status_code == 404


def test_grouse_grind_description_uses_the_official_length():
    route = script.route_entry(proposal(key="grouse-grind-bc"))
    assert "2.5 km" in route["description"]


def test_unsourced_values_are_noted_not_overwritten():
    route = script.route_entry(proposal(key="sunshine-coast-trail-bc", final={
        "distance_km": {"value": 180.0, "kind": "published", "source": "https://sunshinecoasttrail.com/"}}))
    assert route["unsourced"]["fields"] == ["elevation_gain_m", "max_elevation_m"]
    assert "elevation_gain_m" not in route  # the catalogue's old value stays in place
