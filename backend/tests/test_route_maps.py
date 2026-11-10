"""scripts/route_maps.py without the network: framing, hashing, upload plan."""

import importlib.util
import uuid
from pathlib import Path

import numpy as np

from app.models.trail import Trail
from app.models.trail_photo import TrailPhoto, TrailRouteMap

_spec = importlib.util.spec_from_file_location(
    "route_maps", Path(__file__).resolve().parent.parent / "scripts" / "route_maps.py"
)
maps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(maps)

ROUTE = {"line": [[51.0, -116.0], [51.05, -116.02], [51.1, -116.0]],
         "trailhead": [51.0, -116.0, 1500], "high_point": [51.1, -116.0, 2400]}


def test_the_route_fits_its_box_in_every_size():
    # Metres in a projected CRS: a 9 km x 3 km route.
    line = np.array([[0.0, 0.0], [3000.0, 4000.0], [0.0, 9000.0]])
    for variant, size in (("hero", maps.HERO), ("thumb", maps.THUMB)):
        bounds, mpp = maps.frame(line, size, maps.ROUTE_BOX[variant])
        px = np.array(maps.to_pixels(line, bounds, mpp, 1))
        x0, y0, x1, y1 = maps.ROUTE_BOX[variant]
        w, h = size
        assert px[:, 0].min() >= x0 * w - 1 and px[:, 0].max() <= x1 * w + 1
        assert px[:, 1].min() >= y0 * h - 1 and px[:, 1].max() <= y1 * h + 1


def test_short_routes_still_show_country_around_them():
    line = np.array([[0.0, 0.0], [200.0, 100.0]])
    bounds, _ = maps.frame(line, maps.HERO, maps.ROUTE_BOX["hero"])
    assert bounds[2] - bounds[0] >= maps.MIN_SPAN_M


def test_the_hash_changes_with_the_route_only():
    same = maps.route_hash({**ROUTE, "profile": [[0, 1500]]})
    assert maps.route_hash(ROUTE) == same and len(same) == 12
    moved = {**ROUTE, "line": ROUTE["line"] + [[51.2, -116.1]]}
    assert maps.route_hash(moved) != same


def test_contour_interval_keeps_the_map_readable():
    assert maps.contour_interval(150) == 5
    assert maps.contour_interval(900) == 25
    assert maps.contour_interval(2500) == 100


def test_upload_plan_says_what_is_new_redrawn_unchanged_and_shown(session_factory):
    session = session_factory()
    a = Trail(name="A", region="R, AB", country_code="CA", province_code="AB", terrain_difficulty="easy")
    b = Trail(name="B", region="R, AB", country_code="CA", province_code="AB", terrain_difficulty="easy")
    c = Trail(name="C", region="R, AB", country_code="CA", province_code="AB", terrain_difficulty="easy")
    session.add_all([a, b, c])
    session.flush()
    session.add(TrailRouteMap(trail_id=b.id, hero_path=f"{b.id}/route-map-aaaaaaaaaaaa-hero.webp",
                              thumb_path=f"{b.id}/route-map-aaaaaaaaaaaa-thumb.webp", hero_width=1600,
                              hero_height=1000, route_hash="aaaaaaaaaaaa"))
    session.add(TrailRouteMap(trail_id=c.id, hero_path=f"{c.id}/route-map-cccccccccccc-hero.webp",
                              thumb_path=f"{c.id}/route-map-cccccccccccc-thumb.webp", hero_width=1600,
                              hero_height=1000, route_hash="cccccccccccc"))
    session.add(TrailPhoto(trail_id=c.id, source="commons", photographer="P", license="CC BY 2.0",
                           source_url="https://commons.wikimedia.org/wiki/File:X.jpg",
                           hero_path=f"{c.id}/{uuid.uuid4()}-hero.webp", thumb_path=f"{c.id}/{uuid.uuid4()}-thumb.webp",
                           hero_width=1600, hero_height=1000, approved_by=uuid.uuid4()))
    session.commit()
    entry = lambda name, digest: {"name": name, "province_code": "AB", "hash": digest}  # noqa: E731
    plan = maps.plan_upload(session, {"a": entry("A", "111111111111"), "b": entry("B", "bbbbbbbbbbbb"),
                                      "c": entry("C", "cccccccccccc"), "z": entry("Gone", "000000000000")})
    assert [t.name for t, *_ in plan["new"]] == ["A"]
    assert [t.name for t, *_ in plan["changed"]] == ["B"]
    assert [t.name for t, *_ in plan["unchanged"]] == ["C"]
    assert plan["unmatched"] == ["Gone"]
    # C has a photo, so its map waits in the wings.
    assert plan["shown"] == ["A", "B"]
    session.close()
