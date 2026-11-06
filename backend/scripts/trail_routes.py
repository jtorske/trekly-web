"""Route geometry, distance, route type, elevation gain and high point for
every active trail.

Successor to backfill_trail_measures.py: that script matched OSM ways by
name over Overpass and kept only the numbers; this one stores the route line
and the elevation profile too, and records where each value came from.

Steps (run from backend/; nothing touches a database until `apply`):

    # 1. Slice OpenStreetMap around each trail from Geofabrik extracts
    #    (download.geofabrik.de/north-america/canada/<province>-latest.osm.pbf).
    #    Local files avoid Overpass rate limits and make reruns repeatable.
    python scripts/trail_routes.py extract --pbf ../osm/*.osm.pbf --out ../osm/slices

    # 2. Build each route from catalog_data/trail_route_specs.json (an OSM
    #    relation, or waypoints routed over the mapped paths), sample NRCan's
    #    MRDEM along it and compare with the published figures in the spec.
    python scripts/trail_routes.py build --osm ../osm/slices --out proposal.json

    # 3. Coverage, flags and gaps, for review.
    python scripts/trail_routes.py report proposal.json --out report.html

    # 4. After review: write catalog_data/trail_routes.json (--db also
    #    updates DATABASE_URL). Any database can later be synced from the
    #    committed file; seed_trails.py overlays it too.
    python scripts/trail_routes.py apply proposal.json [--db]
    python scripts/trail_routes.py sync-db --dry-run

Elevation: MRDEM-30 (Medium Resolution Digital Elevation Model, 30 m, the
bare-earth successor to CDEM), Natural Resources Canada, read over HTTP from
its cloud-optimised GeoTIFF. Contains information licensed under the Open
Government Licence - Canada. Map data © OpenStreetMap contributors (ODbL).
Needs `osmium` (extract) and `rasterio` (build): requirements-dev.txt.
"""

import argparse
import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND))

from app import route_geometry as g  # noqa: E402

SPECS = BACKEND / "catalog_data" / "trail_route_specs.json"
ROUTES = BACKEND / "catalog_data" / "trail_routes.json"
MRDEM = "/vsicurl/https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"

TRAIL_HIGHWAYS = {"path", "footway", "track", "bridleway", "steps", "cycleway", "pedestrian"}
# Roads are kept so routes can follow a road walk or a connector, but cost more.
ROAD_HIGHWAYS = {"unclassified", "service", "residential", "tertiary", "secondary", "living_street"}
FEATURE_KEYS = ("natural", "tourism", "amenity", "mountain_pass", "leisure", "waterway", "place", "historic")
KEEP_TAGS = ("name", "highway", "route", "network", "ref", "roundtrip", "ele", "sac_scale", *FEATURE_KEYS)


def slug(name, province):
    text = unicodedata.normalize("NFKD", f"{name}-{province}").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def search_radius_km(nights):
    nights = nights or 0
    return 15 if nights == 0 else 50 if nights <= 2 else 90 if nights <= 5 else 140


def active_trails():
    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.execute(text(
            "select name, province_code, latitude, longitude, typical_duration_nights, popularity_rank "
            "from trails where retired_at is null order by popularity_rank"
        )).fetchall()
    finally:
        db.close()
    return [
        {"key": slug(r[0], r[1]), "name": r[0], "province_code": r[1], "latitude": float(r[2]),
         "longitude": float(r[3]), "nights": r[4] or 0, "rank": r[5]}
        for r in rows
    ]


# ---------------------------------------------------------------- extract

def _boxes(trails):
    boxes = []
    for t in trails:
        r = search_radius_km(t["nights"])
        dlat = r / 111.0
        dlon = r / (111.0 * math.cos(math.radians(t["latitude"])))
        boxes.append((t["key"], t["latitude"] - dlat, t["latitude"] + dlat, t["longitude"] - dlon, t["longitude"] + dlon))
    return boxes


def cmd_extract(args):
    import osmium

    trails = active_trails()
    boxes = _boxes(trails)
    grid = {}  # 0.1-degree cell -> boxes overlapping it
    for box in boxes:
        _, s, n, w, e = box
        for i in range(math.floor(s * 10), math.floor(n * 10) + 1):
            for j in range(math.floor(w * 10), math.floor(e * 10) + 1):
                grid.setdefault((i, j), []).append(box)

    def inside(lat, lon):
        return [k for k, s, n, w, e in grid.get((math.floor(lat * 10), math.floor(lon * 10)), ())
                if s <= lat <= n and w <= lon <= e]

    def tags_of(obj):
        return {k: obj.tags[k] for k in KEEP_TAGS if k in obj.tags}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slices = {key: {"ways": {}, "relations": {}, "features": []} for key, *_ in boxes}

    for pbf in args.pbf:
        print(f"{pbf}: relations", flush=True)
        members, relations = {}, {}
        rel_filter = osmium.filter.TagFilter(("route", "hiking"), ("route", "foot"))
        for r in osmium.FileProcessor(pbf, osmium.osm.RELATION).with_filter(rel_filter):
            ways = [m.ref for m in r.members if m.type == "w"]
            relations[r.id] = {"tags": tags_of(r), "ways": ways}
            for w in ways:
                members.setdefault(w, []).append(r.id)
        print(f"  {len(relations)} hiking relations; ways and features", flush=True)
        member_keys = {}  # way id -> slice keys it touches (route members only)
        processor = (osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY)
                     .with_locations("flex_mem")
                     .with_filter(osmium.filter.KeyFilter("highway", "name")))
        for obj in processor:
            if obj.is_node():
                tags = obj.tags
                if not (tags.get("highway") == "trailhead" or ("name" in tags and any(k in tags for k in FEATURE_KEYS))):
                    continue
                lat, lon = obj.location.lat, obj.location.lon
                for k in inside(lat, lon):
                    slices[k]["features"].append({"id": f"node/{obj.id}", "tags": tags_of(obj),
                                                  "at": [round(lat, 6), round(lon, 6)]})
                continue
            w = obj
            highway = w.tags.get("highway")
            in_route = w.id in members
            feature = "name" in w.tags and any(k in w.tags for k in FEATURE_KEYS)
            pathish = highway in TRAIL_HIGHWAYS or highway in ROAD_HIGHWAYS
            if not (in_route or feature or pathish):
                continue
            coords = [(round(n.lat, 6), round(n.lon, 6)) for n in w.nodes if n.location.valid()]
            if len(coords) < 2:
                continue
            keys = set()
            for p in coords[:: max(1, len(coords) // 8)] + [coords[-1]]:
                keys.update(inside(*p))
            if not keys:
                continue
            record = {"tags": tags_of(w), "coords": coords}
            if pathish or in_route:
                for k in keys:
                    slices[k]["ways"][str(w.id)] = record
            if in_route:
                member_keys[w.id] = keys
            if feature:
                lat = sum(p[0] for p in coords) / len(coords)
                lon = sum(p[1] for p in coords) / len(coords)
                for k in inside(lat, lon):
                    slices[k]["features"].append({"id": f"way/{w.id}", "tags": tags_of(w), "at": [round(lat, 6), round(lon, 6)]})
        # A relation goes into each slice one of its ways touches, as the ordered
        # list of member way ids; the geometry is in the slice's ways.
        for rid, rel in relations.items():
            keys = set().union(*(member_keys.get(w, set()) for w in rel["ways"]))
            for k in keys:
                slices[k]["relations"][str(rid)] = {"tags": rel["tags"], "ways": rel["ways"]}
        print(f"  done", flush=True)

    for key, data in slices.items():
        (out / f"{key}.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    empty = [k for k, d in slices.items() if not d["ways"]]
    print(f"Wrote {len(slices)} slices to {out}; without any mapped paths: {empty or 'none'}")


# ---------------------------------------------------------------- elevation

class Dem:
    """Bilinear samples from MRDEM, one window read per route."""

    def __init__(self, url=MRDEM):
        import rasterio

        self._env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                                 GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="5", VSI_CACHE="TRUE")
        self._env.__enter__()
        self.dataset = rasterio.open(url)

    def sample(self, points):
        import numpy as np
        from rasterio.warp import transform
        from rasterio.windows import Window

        xs, ys = transform("EPSG:4326", self.dataset.crs, [p[1] for p in points], [p[0] for p in points])
        inverse = ~self.dataset.transform
        cols, rows = zip(*(inverse * (x, y) for x, y in zip(xs, ys)))
        cols, rows = np.array(cols) - 0.5, np.array(rows) - 0.5  # pixel centres
        c0, r0 = int(math.floor(cols.min())) - 1, int(math.floor(rows.min())) - 1
        c1, r1 = int(math.ceil(cols.max())) + 2, int(math.ceil(rows.max())) + 2
        nodata = self.dataset.nodata
        data = self.dataset.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), boundless=True,
                                 fill_value=nodata if nodata is not None else -32767)
        out = []
        for c, r in zip(cols - c0, rows - r0):
            i, j = int(math.floor(r)), int(math.floor(c))
            fr, fc = r - i, c - j
            cell = data[i:i + 2, j:j + 2].astype(float)
            if cell.shape != (2, 2) or (nodata is not None and (cell == nodata).any()) or (cell < -1000).any():
                out.append(None)
                continue
            top = cell[0, 0] * (1 - fc) + cell[0, 1] * fc
            bottom = cell[1, 0] * (1 - fc) + cell[1, 1] * fc
            out.append(float(top * (1 - fr) + bottom * fr))
        return out


# ---------------------------------------------------------------- build

def load_slice(osm_dir, key):
    path = Path(osm_dir) / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def graph_for(data, prefer_ways=()):
    """Path network from a slice. Roads cost more than paths; ways the spec
    names (prefer_ways) cost less, so a route sticks to the named trail."""
    graph = g.Graph()
    prefer = {str(w) for w in prefer_ways}
    for wid, way in data["ways"].items():
        highway = way["tags"].get("highway")
        penalty = 3.0 if highway in ROAD_HIGHWAYS else 1.0
        if wid in prefer:
            penalty = 0.5
        name = way["tags"].get("name") or f"({highway})"
        graph.add_way([tuple(p) for p in way["coords"]], penalty, name, int(wid))
    return graph


def relation_line(data, relation_ids, near):
    ways = []
    for rid in relation_ids:
        rel = data["relations"].get(str(rid))
        if rel is None:
            return None, f"relation {rid} isn't in the OSM slice"
        ways += [data["ways"][str(w)]["coords"] for w in rel["ways"] if str(w) in data["ways"]]
    line, gap = g.chain([[tuple(p) for p in w] for w in ways], near=near)
    if line is None:
        return None, "relation has no mapped ways"
    return line, (f"largest gap between relation members {gap:.0f} m" if gap and gap > 50 else None)


def cut(line, start, end):
    """The part of a line between the points nearest start and end."""
    i = min(range(len(line)), key=lambda k: g.haversine_m(line[k], start))
    j = min(range(len(line)), key=lambda k: g.haversine_m(line[k], end))
    return line[i:j + 1] if i <= j else list(reversed(line[j:i + 1]))


def geometry_for(spec, data):
    """(points, notes) for a spec; points None when it can't be built."""
    method = spec.get("method")
    if method == "relation":
        waypoints = [tuple(w) for w in spec.get("waypoints", [])]
        near = waypoints[0] if waypoints else tuple(spec["near"])
        line, note = relation_line(data, spec["relation"], near)
        if line is None:
            return None, [note]
        if len(waypoints) >= 2:
            line = cut(line, waypoints[0], waypoints[-1])
        return line, [note] if note else []
    if method == "waypoints":
        prefer = list(spec.get("prefer_ways", ()))
        for rid in spec.get("prefer_relations", ()):
            prefer += (data["relations"].get(str(rid)) or {}).get("ways", [])
        names = set(spec.get("prefer_names", ()))
        prefer += [wid for wid, w in data["ways"].items() if w["tags"].get("name") in names]
        if spec.get("within_relations"):
            members = {str(w) for rid in spec["within_relations"]
                       for w in (data["relations"].get(str(rid)) or {}).get("ways", [])}
            data = {**data, "ways": {wid: w for wid, w in data["ways"].items() if wid in members}}
        graph = graph_for(data, prefer)
        points, notes = g.route_through(graph, [tuple(w) for w in spec["waypoints"]],
                                        snap_limit_m=spec.get("snap_limit_m", 400))
        if points:
            spec["_along"] = g.names_along(graph, points)
            spec["_ways"] = g.ways_along(graph, points)
        return points, notes
    if method == "named":
        names = set(spec["names"])
        named = {"ways": {wid: w for wid, w in data["ways"].items() if w["tags"].get("name") in names}}
        if not named["ways"]:
            return None, [f"no OSM ways named {sorted(names)}"]
        graph = graph_for(named).component(tuple(spec.get("near") or spec.get("from") or spec["_point"]))
        if spec.get("line") == "loop":
            # Out to the far side of the named loop and back the other way.
            start = graph.nearest(tuple(spec.get("from") or spec["_point"]))[0]
            dist = graph.distances(start)
            far = max(dist, key=dist.get)
            points, notes = g.route_through(graph, [start, far, start])
            if points:
                spec["_along"] = g.names_along(graph, points)
                spec["_ways"] = g.ways_along(graph, points)
            return points, notes
        points = g.longest_route(graph, _pt(spec.get("from")), _pt(spec.get("to")))
        if not points:
            return None, ["named ways don't form a route"]
        notes = []
        for end, label in ((spec.get("from"), "start"), (spec.get("to"), "end")):
            if end and g.haversine_m(tuple(end), points[0 if label == "start" else -1]) > 300:
                notes.append(f"named trail's {label} is {g.haversine_m(tuple(end), points[0 if label == 'start' else -1]):.0f} m from the spec point")
        spec["_along"] = g.names_along(graph, points)
        spec["_ways"] = g.ways_along(graph, points)
        return points, notes
    return None, [spec.get("note") or "no geometry method in the spec"]


def _pt(value):
    return tuple(value) if value else None


def adjust(points, spec, dem):
    """Spec post-processing: trim an approach, or start a loop at its lowest point."""
    if spec.get("trim_start_km"):
        cum = g.cumulative_m(points)
        points = [p for p, c in zip(points, cum) if c >= spec["trim_start_km"] * 1000]
    if spec.get("rotate_to_lowest") and dem and len(points) > 2 and points[0] == points[-1]:
        heights = dem.sample(points[:-1])
        i = min(range(len(heights)), key=lambda k: heights[k] if heights[k] is not None else 1e9)
        points = points[i:-1] + points[:i + 1]
    return points


def build_one(spec, data, dem):
    result = {"key": spec["key"], "name": spec["name"], "method": spec.get("method"), "notes": [], "measured": {}}
    points, notes = geometry_for(spec, data) if data else (None, [spec.get("note") or "no OSM slice"])
    if points:
        points = adjust(points, spec, dem)
    result["notes"] += notes
    if not points:
        return result
    route_type = g.route_type_for(points, spec.get("line", "out_and_back"))
    if spec.get("line") == "loop" and route_type != "loop":
        result["notes"].append(f"spec expects a loop but the route's ends are {g.haversine_m(points[0], points[-1]):.0f} m apart")
    result["measured"] = {"distance_km": round(g.hiked_distance_km(points, route_type), 1), "route_type": route_type,
                          "ends_apart_m": round(g.haversine_m(points[0], points[-1]))}
    result["geometry"] = [[round(p[0], 5), round(p[1], 5)] for p in g.simplify(points, 4)]
    profile = g.profile_for(points, route_type, dem.sample) if dem else None
    if profile is None:
        result["notes"].append("no elevation sampled" if dem is None else "MRDEM samples missing along the route")
        return result
    result["measured"].update({
        "elevation_gain_m": profile.gain_m, "max_elevation_m": profile.high_m,
        "trailhead_m": profile.trailhead_m, "low_m": profile.low_m,
        "ascent_one_way_m": round(g.ascent_m(profile.elevations_m)),
    })
    samples = g.resample(points)
    high = samples[profile.high_index]
    result["high_point"] = [round(high[0], 6), round(high[1], 6), profile.high_m]
    result["profile"] = g.chart_points(profile)
    return result


def choose(result, spec):
    """Final value per field: measured, unless it's missing or more than 15%
    off a published figure, in which case the published figure is used.

    A published gain marked one_way (Parks Canada usually quotes the climb
    to the destination) is compared with the outbound ascent only."""
    published = spec.get("published") or {}
    measured = result["measured"]
    final, flags = {}, []
    method = (f"{'OSM route relation' if spec.get('method') == 'relation' else 'OSM paths'}"
              f" + NRCan MRDEM, measured {date.today().isoformat()}")
    distance_off = g.disagreement(measured.get("distance_km"), (published.get("distance_km") or {}).get("value"))
    # A route more than 15% off the published length is probably the wrong
    # line, so its elevations aren't trusted either (unless the spec says the
    # line is right and only simplified, e.g. a switchback trail drawn straight).
    suspect = distance_off is not None and distance_off > 0.15 and not spec.get("trust_elevation")
    if suspect:
        flags.append("geometry doesn't match the published length; measured elevations not used")
    for field in ("distance_km", "route_type", "elevation_gain_m", "max_elevation_m"):
        pub = published.get(field)
        mine = measured.get(field)
        if suspect and field in ("elevation_gain_m", "max_elevation_m"):
            mine = None
        if field == "route_type":
            if suspect and pub:
                mine = None
            value = mine or (pub or {}).get("value")
            if value:
                final[field] = {"value": value, "kind": "measured" if mine else "published",
                                "source": method if mine else pub["url"]}
            continue
        compare = mine
        if field == "elevation_gain_m" and measured.get("route_type") == "out_and_back" and (pub or {}).get("one_way")                 and mine is not None:
            # Parks usually quote the climb in the uphill direction: on the way
            # out to a summit, or on the way back from a trail that descends
            # to a lake or the coast.
            out = measured.get("ascent_one_way_m") or 0
            compare = max(out, mine - out)
        off = g.disagreement(compare, (pub or {}).get("value"))
        if mine is not None and (off is None or off <= 0.15):
            final[field] = {"value": mine, "kind": "measured", "source": method}
            if pub:
                final[field]["published"] = {"value": pub["value"], "url": pub["url"]}
        elif pub:
            final[field] = {"value": pub["value"], "kind": "published", "source": pub["url"]}
            if mine is not None:
                final[field]["measured"] = mine
                flags.append(f"{field}: measured {compare} vs published {pub['value']} ({off:.0%} apart), using published")
    return final, flags


def cmd_build(args):
    specs = json.loads(SPECS.read_text(encoding="utf-8")) if SPECS.exists() else {}
    trails = {t["key"]: t for t in active_trails()}
    if args.only:
        trails = {k: v for k, v in trails.items() if k in args.only or str(v["rank"]) in args.only}
    dem = None if args.no_dem else Dem()
    previous = {}
    if args.merge and Path(args.out).exists():
        previous = {p["key"]: p for p in json.loads(Path(args.out).read_text(encoding="utf-8"))}
    for key, trail in trails.items():
        spec = {**specs.get(key, {"note": "no spec yet"}), "key": key, "name": trail["name"],
                "_point": (trail["latitude"], trail["longitude"])}
        data = load_slice(args.osm, key) if spec.get("method") else None
        result = build_one(spec, data, dem)
        result["final"], result["choice_flags"] = choose(result, spec)
        values = {f: v["value"] for f, v in result["final"].items()}
        result["flags"] = g.validate({**values, "nights": trail["nights"],
                                      "trailhead_m": result["measured"].get("trailhead_m"),
                                      "ends_apart_m": result["measured"].get("ends_apart_m")})
        result.update(rank=trail["rank"], nights=trail["nights"], province_code=trail["province_code"],
                      spec_note=spec.get("note"))
        m = result["measured"]
        print(f"#{trail['rank']:>3} {trail['name'][:36]:36} {m.get('distance_km', '-'):>6} km {m.get('route_type', '-'):14}"
              f" +{m.get('elevation_gain_m', '-')} top {m.get('max_elevation_m', '-')} th {m.get('trailhead_m', '-')}"
              f"  {'; '.join(result['notes'] + result['flags'] + result['choice_flags'])}", flush=True)
        if spec.get("_along") and args.verbose:
            print("        " + " > ".join(f"{n} {k}" for n, k in spec["_along"]), flush=True)
        result["along"] = spec.get("_along")
        result["osm_ways"] = spec.get("_ways") or []
        result["osm_relations"] = spec.get("relation") or spec.get("prefer_relations") or spec.get("within_relations") or []
        previous[key] = result
    ordered = sorted(previous.values(), key=lambda p: p["rank"])
    Path(args.out).write_text(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------- report

FIELDS = ("distance_km", "route_type", "elevation_gain_m", "max_elevation_m")


def gap_reason(proposal, field):
    notes = proposal["notes"] + proposal["choice_flags"]
    if not proposal.get("geometry"):
        return "; ".join(notes) or "no route built"
    if any("measured elevations not used" in n for n in notes) and field in ("elevation_gain_m", "max_elevation_m"):
        km = proposal["measured"].get("distance_km")
        pub = ((proposal["final"].get("distance_km") or {}).get("value"))
        return (f"OSM route ({km} km) doesn't match the published {pub} km, so its elevations aren't trusted, "
                "and no official figure was found")
    if field == "route_type":
        return "route geometry suspect and no published route type"
    return "; ".join(notes) or "no value"


def summarize(proposals):
    total = len(proposals)
    coverage = {}
    for field in FIELDS:
        kinds = [(p["final"].get(field) or {}).get("kind") for p in proposals]
        coverage[field] = {"measured": kinds.count("measured"), "published": kinds.count("published"), "total": total}
    gaps = [{"rank": p["rank"], "name": p["name"], "field": f, "reason": gap_reason(p, f)}
            for p in proposals for f in FIELDS if f not in p["final"]]
    flagged = [{"rank": p["rank"], "name": p["name"], "flags": p["flags"], "choices": p["choice_flags"]}
               for p in proposals if p["flags"] or p["choice_flags"]]
    compared = sum(1 for p in proposals if any((p["final"].get(f) or {}).get("published") or
                                               (p["final"].get(f) or {}).get("kind") == "published" for f in FIELDS))
    return {"coverage": coverage, "gaps": gaps, "flagged": flagged, "compared_with_official": compared, "total": total}


def cmd_report(args):
    proposals = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    summary = summarize(proposals)
    for field, c in summary["coverage"].items():
        have = c["measured"] + c["published"]
        print(f"{field:18} {have}/{c['total']} ({have / c['total']:.0%})  measured {c['measured']}, published {c['published']}")
    print(f"\nChecked against an official figure: {summary['compared_with_official']} of {summary['total']}")
    print(f"\nFlagged ({len(summary['flagged'])}):")
    for f in summary["flagged"]:
        print(f"  #{f['rank']} {f['name']}: {'; '.join(f['flags'] + f['choices'])}")
    print(f"\nGaps ({len(summary['gaps'])}):")
    for gap in summary["gaps"]:
        print(f"  #{gap['rank']} {gap['name']} {gap['field']}: {gap['reason']}")
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- apply

DEM_URL = "https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"
# Description updates that go with a measuring decision (user, 2026-11-04).
DESCRIPTIONS = {
    "elizabeth-parker-hut-lake-o-hara-bc": (
        "A short but stunning alpine lake basin, day-hike or overnight friendly. Measured from Le Relais to "
        "Elizabeth Parker Hut; walking the 11 km road in from the parking lot instead of taking the bus is optional."
    ),
    # Metro Vancouver's official length (the old text said 2.9 km).
    "grouse-grind-bc": "Relentless 2.5 km stair-climb up the face of Grouse Mountain, Vancouver's outdoor gym.",
}
# Values kept from the old catalogue because no route or official figure
# confirmed them yet (user, 2026-11-04: keep until the gap pass).
UNSOURCED = {
    "sunshine-coast-trail-bc": {
        "fields": ["elevation_gain_m", "max_elevation_m"],
        "note": "Gain 3,600 m and high point 1,181 m (Tin Hat Mountain) are the old catalogue figures, unsourced; "
                "the mapped route is too incomplete to measure. Fix in the gap pass.",
    },
}


def osm_url(proposal):
    if proposal.get("osm_relations"):
        return f"https://www.openstreetmap.org/relation/{proposal['osm_relations'][0]}"
    if proposal.get("osm_ways"):
        return f"https://www.openstreetmap.org/way/{proposal['osm_ways'][0]}"
    return "https://www.openstreetmap.org/"


def route_entry(proposal):
    """One trail's record in catalog_data/trail_routes.json."""
    trusted = bool(proposal.get("geometry")) and not any(
        "measured elevations not used" in flag for flag in proposal["choice_flags"])
    sources = {}
    for field, value in proposal["final"].items():
        if value["kind"] == "measured":
            source = {"kind": "measured", "method": value["source"], "url": osm_url(proposal)}
            if field in ("elevation_gain_m", "max_elevation_m"):
                source["elevation_url"] = DEM_URL
            if value.get("published"):
                source["published"] = value["published"]
        else:
            source = {"kind": "published", "url": value["source"]}
            if value.get("measured") is not None:
                source["measured"] = value["measured"]
        sources[field] = source
    entry = {
        "name": proposal["name"],
        "province_code": proposal["province_code"],
        **{field: proposal["final"][field]["value"] for field in FIELDS if field in proposal["final"]},
        "sources": sources,
        "osm": {"relations": proposal.get("osm_relations") or [], "ways": proposal.get("osm_ways") or []},
        "route": None,
    }
    if trusted:
        line = proposal["geometry"]
        measured = proposal["measured"]
        entry["route"] = {
            "line": line,
            "trailhead": [line[0][0], line[0][1], measured.get("trailhead_m")],
            "high_point": proposal.get("high_point"),
            # [[km along the route, metres]], one way for an out-and-back.
            "profile": proposal.get("profile") or [],
        }
    if proposal["key"] in DESCRIPTIONS:
        entry["description"] = DESCRIPTIONS[proposal["key"]]
    if proposal["key"] in UNSOURCED:
        entry["unsourced"] = UNSOURCED[proposal["key"]]
    return entry


def sync_db(db, trails):
    """Write the measures onto existing active trails, matched by name and
    province. Unlike seed_trails.py this never inserts or retires a trail, so
    it's safe whichever catalogue file the database was seeded from."""
    from app.models.trail import Trail

    changed = []
    for entry in trails.values():
        trail = (db.query(Trail).filter(Trail.name == entry["name"], Trail.province_code == entry["province_code"],
                                        Trail.retired_at.is_(None)).one_or_none())
        if trail is None:
            continue
        wanted = {f: entry.get(f) for f in FIELDS}
        if entry.get("description"):
            wanted["description"] = entry["description"]
        diff = {}
        for field, value in wanted.items():
            if value is None:
                continue
            current = getattr(trail, field)
            same = (float(current) == float(value)) if field == "distance_km" and current is not None else current == value
            if not same:
                diff[field] = (current, value)
                setattr(trail, field, value)
        if diff:
            changed.append((entry["name"], diff))
    db.flush()
    return changed


def cmd_apply(args):
    proposals = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    trails = {p["key"]: route_entry(p) for p in proposals}
    payload = {
        "meta": {
            "generated": date.today().isoformat(),
            "definitions": {
                "distance_km": "what a hiker covers: the round trip, the loop, or the one-way length",
                "elevation_gain_m": "total climbing over that hike, including climbs on the way back of an out-and-back",
                "max_elevation_m": "highest point on the route",
            },
            "attribution": [
                "Map data © OpenStreetMap contributors, ODbL (Geofabrik extracts).",
                "Elevation: MRDEM-30, Natural Resources Canada. Contains information licensed under the "
                "Open Government Licence – Canada.",
            ],
        },
        "trails": trails,
    }
    ROUTES.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    with_route = sum(1 for t in trails.values() if t["route"])
    print(f"Wrote {len(trails)} trails ({with_route} with a route) to {ROUTES} ({ROUTES.stat().st_size // 1024} KB)")
    if args.db:
        write_db(trails, args.dry_run)


def cmd_sync_db(args):
    """Write the committed catalog_data/trail_routes.json onto DATABASE_URL."""
    write_db(json.loads(ROUTES.read_text(encoding="utf-8"))["trails"], args.dry_run)


def write_db(trails, dry_run):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        changed = sync_db(db, trails)
        for name, diff in changed:
            print(f"  {name}: " + ", ".join(f"{f} {a} -> {b}" for f, (a, b) in diff.items() if f != "description")
                  + (" (+ description)" if "description" in diff else ""))
        print(f"{len(changed)} trails updated")
        if dry_run:
            db.rollback()
            print("Dry run: rolled back, nothing written.")
        else:
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract", help="slice OSM extracts around each active trail")
    extract.add_argument("--pbf", nargs="+", required=True)
    extract.add_argument("--out", required=True)
    build = sub.add_parser("build", help="build routes and measures from the specs")
    build.add_argument("--osm", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--only", nargs="*", help="trail keys or ranks")
    build.add_argument("--no-dem", action="store_true")
    build.add_argument("--verbose", "-v", action="store_true", help="print the named ways each route follows")
    build.add_argument("--merge", action="store_true", help="update only these trails in an existing --out")
    report = sub.add_parser("report", help="coverage, flags and gaps for a proposal")
    report.add_argument("proposal")
    report.add_argument("--out", help="also write the summary as JSON")
    apply = sub.add_parser("apply", help="write catalog_data/trail_routes.json (and, with --db, the trail rows)")
    apply.add_argument("proposal")
    apply.add_argument("--db", action="store_true", help="also update the trails in DATABASE_URL")
    apply.add_argument("--dry-run", action="store_true", help="with --db: report, then roll back")
    sync = sub.add_parser("sync-db", help="write catalog_data/trail_routes.json onto the trails in DATABASE_URL")
    sync.add_argument("--dry-run", action="store_true", help="report, then roll back")
    args = parser.parse_args()
    {"extract": cmd_extract, "build": cmd_build, "report": cmd_report, "apply": cmd_apply,
     "sync-db": cmd_sync_db}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
