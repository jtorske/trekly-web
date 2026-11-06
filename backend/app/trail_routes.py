"""Measured trail routes from catalog_data/trail_routes.json.

Written by scripts/trail_routes.py apply. Each entry, keyed by trail name and
province, holds the four trail measures with where each value came from
("measured" from OpenStreetMap + NRCan MRDEM, or "published" by the park),
and, when the mapped line matches the park's figures, the route itself: the
line, trailhead, high point and elevation profile.

scripts/seed_trails.py passes routes_by_name() to the catalogue sync, which
overlays the measures onto catalogue entries so seeding keeps them. The trail
page reads the route through GET /api/trails/{id}/route.
"""

import json
from functools import lru_cache
from pathlib import Path

ROUTES_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trail_routes.json"


@lru_cache
def load_routes(path: Path = ROUTES_PATH) -> dict:
    if not path.exists():
        return {"meta": {}, "trails": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def routes_by_name(path: Path = ROUTES_PATH) -> dict[tuple[str, str | None], dict]:
    return {(t["name"], t["province_code"]): t for t in load_routes(path)["trails"].values()}


def route_for(name: str, province_code: str | None, path: Path = ROUTES_PATH) -> dict | None:
    return routes_by_name(path).get((name, province_code))

