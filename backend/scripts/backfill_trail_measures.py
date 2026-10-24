"""Backfill missing trail distance, route type and elevation in the catalogue.

Fills only null fields in catalog_data/trails_canada.json; existing values
(OSM, legacy or manual) are never overwritten.

- distance_km / route_type: a hiking route relation, or path ways named
  after the trail, from OpenStreetMap (Overpass). Accepted only when the
  mapped feature is one clean line or loop (no branches, no gaps) and its
  length is plausible for the trip, the same rule as the first pass.
- max_elevation_m / elevation_gain_m: Natural Resources Canada's CDEM,
  sampled along the accepted route geometry. Gain follows the catalogue's
  definition: the high point minus the trailhead elevation.

Two steps, so nothing changes until a proposal has been reviewed:

    python scripts/backfill_trail_measures.py propose --out proposal.json
    python scripts/backfill_trail_measures.py apply proposal.json

`propose` only reads remote services and writes the proposal file. Overpass
responses are cached (--cache) so a rerun never repeats a query. Requests go
one at a time with pauses, and back off on 429/504 as Overpass asks.
`apply` edits the catalogue JSON only; run seed_trails.py to sync a database.
"""

import argparse
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "catalog_data" / "trails_canada.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
CDEM_PROFILE = "https://geogratis.gc.ca/services/elevation/cdem/profile"
USER_AGENT = "Trekly-catalogue-backfill/1.0 (jtorske27@gmail.com)"
FIELDS = ("distance_km", "route_type", "max_elevation_m", "elevation_gain_m")

OVERPASS_PAUSE_S = 5
OVERPASS_BACKOFF_S = (30, 60, 120, 240)
CDEM_PAUSE_S = 1
LOOP_CLOSE_M = 200
GENERIC_WORDS = {"trail", "trails", "the", "loop", "hike", "route", "via", "to", "and", "path", "de", "la", "du", "des"}


# ---------------------------------------------------------------- geometry

def haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def path_length_m(points):
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def _key(point):
    return (round(point[0], 6), round(point[1], 6))


def _components(adjacency):
    seen, out = set(), []
    for node in adjacency:
        if node in seen:
            continue
        stack, part = [node], {}
        seen.add(node)
        while stack:
            current = stack.pop()
            part[current] = adjacency[current]
            for n in adjacency[current]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(part)
    return out


def chain(ways, near=None):
    """Order way geometries into one clean line or loop, or return None.

    Clean means connected, no node shared by more than two segments, and
    either two loose ends (a line) or none (a loop). With `near`, only the
    connected piece closest to that point is used, so same-named paths
    elsewhere in the search area don't disqualify the trail.
    """
    adjacency = {}
    for geometry in ways:
        for a, b in zip(geometry, geometry[1:]):
            ka, kb = _key(a), _key(b)
            if ka == kb:
                continue
            adjacency.setdefault(ka, set()).add(kb)
            adjacency.setdefault(kb, set()).add(ka)
    if adjacency and near is not None:
        adjacency = min(_components(adjacency), key=lambda part: min(haversine_m(k, near) for k in part))
    if not adjacency or any(len(n) > 2 for n in adjacency.values()):
        return None
    ends = [k for k, n in adjacency.items() if len(n) == 1]
    if len(ends) not in (0, 2):
        return None
    start = ends[0] if ends else next(iter(adjacency))
    ordered, previous, current = [start], None, start
    while True:
        nxt = [n for n in adjacency[current] if n != previous]
        if not nxt or (not ends and nxt[0] == start):
            break
        previous, current = current, nxt[0]
        ordered.append(current)
    if len(ordered) != len(adjacency):
        return None  # more than one component
    if not ends:
        ordered.append(start)
    return ordered


def simplify(points, max_points=80):
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


# ---------------------------------------------------------------- remote

def _cache_path(cache_dir, query):
    return cache_dir / (hashlib.sha256(query.encode()).hexdigest()[:20] + ".json")


def overpass(query, cache_dir):
    cached = _cache_path(cache_dir, query)
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    body = urllib.parse.urlencode({"data": query}).encode()
    for attempt, wait in enumerate((0, *OVERPASS_BACKOFF_S)):
        if wait:
            print(f"    overpass busy, waiting {wait}s (retry {attempt})", flush=True)
            time.sleep(wait)
        request = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read())
            cached.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(OVERPASS_PAUSE_S)
            return data
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
    return None


def cdem_profile(points, steps):
    """Altitudes (m) along the line, from NRCan's CDEM; None where no data."""
    path = "LINESTRING(" + ",".join(f"{lon:.6f} {lat:.6f}" for lat, lon in points) + ")"
    url = f"{CDEM_PROFILE}?{urllib.parse.urlencode({'path': path, 'steps': steps})}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in (0, 10, 30):
        time.sleep(wait or CDEM_PAUSE_S)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return [p.get("altitude") for p in json.loads(response.read())]
        except (urllib.error.URLError, TimeoutError):
            continue
    return None


# ---------------------------------------------------------------- matching

def name_parts(name):
    """Distinctive pieces of a trail name to match OSM names against."""
    parts = re.split(r"\s*(?:/|\bto\b|\bvia\b|\s-\s|,)\s*", name, flags=re.I)
    out = []
    for part in parts:
        words = [w for w in re.findall(r"[\w'’.]+", part) if w.lower() not in GENERIC_WORDS]
        if words and len(" ".join(words)) >= 4:
            out.append(" ".join(words))
    return out or [name]


def destination_part(name, parts):
    """Where the hike ends: X in "X via Y", otherwise the last part (B in "A to B")."""
    return parts[:1] if re.search(r"\bvia\b", name, re.I) else parts[-1:]


def _regex(parts):
    return "|".join(re.escape(p).replace("\\ ", " ") for p in parts).replace('"', "")


DESTINATION_KEYS = "natural|tourism|amenity|mountain_pass|leisure|waterway"


def search_query(trail, radius_m, parts):
    lat, lon = trail["latitude"], trail["longitude"]
    pattern = _regex(parts)
    destination = _regex(destination_part(trail["name"], parts))
    return (
        f'[out:json][timeout:120];('
        f'relation(around:{radius_m},{lat},{lon})[route~"^(hiking|foot)$"][name~"{pattern}",i];'
        f'way(around:{radius_m},{lat},{lon})[highway~"^(path|footway|track|bridleway)$"][name~"{pattern}",i];'
        f'nwr(around:{radius_m},{lat},{lon})[name~"{destination}",i][~"^({DESTINATION_KEYS})$"~"."];'
        f');out geom;'
    )


def _way_geometry(element):
    return [(p["lat"], p["lon"]) for p in element.get("geometry") or []]


def _is_trail_way(element):
    return element["type"] == "way" and re.match(
        r"^(path|footway|track|bridleway)$", element.get("tags", {}).get("highway", "")
    )


def destination_points(data):
    """Points of named destination features (a pass, lake, hut, peak...)."""
    points = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        if not any(k in tags for k in DESTINATION_KEYS.split("|")) or "highway" in tags or "route" in tags:
            continue
        if element["type"] == "node":
            points.append((element["lat"], element["lon"]))
        else:
            points.extend(_way_geometry(element))
            for member in element.get("members", []):
                points.extend(_way_geometry(member))
    return points


def candidates(data, parts, near=None):
    """Clean chains from the response: each relation, then the named ways together."""
    found = []
    for element in data.get("elements", []):
        if element["type"] != "relation" or "route" not in element.get("tags", {}):
            continue
        ways = [_way_geometry(m) for m in element.get("members", []) if m.get("type") == "way" and m.get("geometry")]
        points = chain(ways, near)
        if points:
            found.append({
                "source": {"osm": [f"relation/{element['id']}"]},
                "name": element.get("tags", {}).get("name", ""),
                "roundtrip_no": element.get("tags", {}).get("roundtrip") == "no",
                "points": points,
            })
    ways = [e for e in data.get("elements", []) if _is_trail_way(e)]
    if ways:
        points = chain([_way_geometry(w) for w in ways], near)
        if points:
            names = sorted({w.get("tags", {}).get("name", "") for w in ways})
            found.append({
                "source": {"osm_named_ways": names, "way_count": len(ways)},
                "name": " / ".join(names),
                "roundtrip_no": False,
                "points": points,
            })
    return found


def plausible(one_way_km, nights, route_type):
    total = one_way_km * 2 if route_type == "out_and_back" else one_way_km
    if nights == 0:
        return 1 <= total <= 40
    return 5 <= total <= 160


def infer_route_type(candidate, one_way_km, nights):
    points = candidate["points"]
    if haversine_m(points[0], points[-1]) <= LOOP_CLOSE_M:
        return "loop", "ends meet: treated as a loop"
    if candidate["roundtrip_no"] or (nights >= 2 and one_way_km >= 20):
        return "point_to_point", "inferred: long multi-day line (or roundtrip=no), treated as one way"
    return "out_and_back", "inferred: single line, treated as an out-and-back"


TRIM_WITHIN_M = 400


def trim(points, trail, destinations):
    """Cut an oriented line to trailhead → destination where both are known.

    OSM trails named after a pass or lake often continue past it (Sentinel
    Pass carries on into Paradise Valley), which would overstate the hike.
    Returns (points, note); loops are left whole.
    """
    if points[0] == points[-1]:
        return points, None
    # The start isn't cut: a "start" coordinate is often a lake or canyon
    # beside the trailhead rather than the trailhead itself.
    here = (trail["latitude"], trail["longitude"])
    role = (trail.get("verification") or {}).get("coordinates", {}).get("role", "start")
    targets = destinations if role == "start" else [here]
    if targets and len(points) > 2:
        j = min(range(1, len(points)), key=lambda k: min(haversine_m(points[k], t) for t in targets))
        if j < len(points) - 1 and min(haversine_m(points[j], t) for t in targets) <= TRIM_WITHIN_M:
            return points[: j + 1], "cut at the destination"
    return points, None


def orient(points, trail):
    """Start the line at the trailhead end (or the loop at its nearest point)."""
    here = (trail["latitude"], trail["longitude"])
    role = (trail.get("verification") or {}).get("coordinates", {}).get("role", "start")
    if points[0] == points[-1]:
        i = min(range(len(points) - 1), key=lambda j: haversine_m(points[j], here))
        return points[i:-1] + points[:i + 1]
    near_start = haversine_m(points[0], here) <= haversine_m(points[-1], here)
    trailhead_first = near_start if role != "destination" else not near_start
    return points if trailhead_first else list(reversed(points))


def elevation_for(points, route_type, trail):
    line = orient(points, trail)
    length = path_length_m(line)
    steps = max(20, min(400, int(length / 50)))
    altitudes = cdem_profile(simplify(line), steps)
    known = [a for a in (altitudes or []) if a is not None]
    if len(known) < 10 or altitudes[0] is None:
        return None
    high = max(known)
    ascent, low = 0.0, altitudes[0]
    for a in known:  # cumulative ascent with a 5 m hysteresis, for review only
        if a < low:
            low = a
        elif a - low >= 5:
            ascent += a - low
            low = a
    return {
        "max_elevation_m": round(high),
        "elevation_gain_m": max(0, round(high - altitudes[0])),
        "trailhead_m": round(altitudes[0]),
        "cumulative_ascent_m": round(ascent * (2 if route_type == "loop" else 1)),
        "samples": len(known),
    }


# ---------------------------------------------------------------- steps

def known_geometry_query(trail):
    distance = (trail.get("verification") or {}).get("distance_km") or {}
    lat, lon = trail["latitude"], trail["longitude"]
    if distance.get("osm"):
        ids = ",".join(ref.split("/")[1] for ref in distance["osm"])
        return f"[out:json][timeout:120];relation(id:{ids});out geom;", None
    if distance.get("osm_named_ways"):
        names = distance["osm_named_ways"]
        pattern = "|".join("^" + re.escape(n).replace("\\ ", " ") + "$" for n in names)
        return (f'[out:json][timeout:120];way(around:30000,{lat},{lon})'
                f'[highway~"^(path|footway|track|bridleway)$"][name~"{pattern}"];out geom;'), names
    return None, None


def propose_one(trail, cache_dir):
    missing = [f for f in FIELDS if trail.get(f) is None]
    result = {"rank": trail["rank"], "name": trail["name"], "missing": missing, "set": {}, "notes": []}
    nights = trail["typical_duration_nights"] or 0

    if trail.get("distance_km") is None:
        parts = name_parts(trail["name"])
        radius = 8000 if nights == 0 else 30000
        data = overpass(search_query(trail, radius, parts), cache_dir)
        if data is None:
            result["status"] = "unresolved"
            result["notes"].append("Overpass unavailable after retries")
            return result
        here = (trail["latitude"], trail["longitude"])
        destinations = destination_points(data)
        best = None
        for candidate in candidates(data, parts, near=here):
            points, cut = trim(orient(candidate["points"], trail), trail, destinations)
            candidate = {**candidate, "points": points, "cut": cut}
            one_way = path_length_m(points) / 1000
            if cut and "destination" in cut:
                route_type, why = "out_and_back", "inferred: line cut at the named destination, treated as an out-and-back"
            else:
                route_type, why = infer_route_type(candidate, one_way, nights)
            if plausible(one_way, nights, route_type):
                score = (candidate["source"].get("osm") is not None, -abs(len(candidate["name"]) - len(trail["name"])))
                if best is None or score > best[0]:
                    best = (score, candidate, one_way, route_type, why)
        if best is None:
            count = len([e for e in data.get("elements", [])])
            result["status"] = "unresolved"
            result["notes"].append(
                f"no clean, plausible OSM line or loop named like {parts} ({count} OSM elements matched)"
            )
            return result
        _, candidate, one_way, route_type, why = best
        distance = one_way * 2 if route_type == "out_and_back" else one_way
        result["set"]["distance_km"] = round(distance, 1)
        result["set"]["route_type"] = route_type
        result["verification_distance"] = {
            **candidate["source"],
            "mapped_km": round(one_way, 2),
            "method": f"auto backfill {date.today().isoformat()}",
            **({"note": "out and back: distance_km is the round trip, twice the mapped one-way length"}
               if route_type == "out_and_back" else {}),
        }
        if candidate["cut"]:
            result["verification_distance"]["trimmed"] = candidate["cut"]
        result["route_note"] = why
        result["osm_name"] = candidate["name"]
        points = candidate["points"]
    else:
        query, _ = known_geometry_query(trail)
        data = overpass(query, cache_dir) if query else None
        found = candidates(data, [], near=(trail["latitude"], trail["longitude"])) if data else []
        if not found:
            result["status"] = "unresolved"
            result["notes"].append("couldn't rebuild the recorded OSM geometry for elevation sampling")
            return result
        points = found[0]["points"]
        route_type = trail["route_type"]
        mapped = ((trail.get("verification") or {}).get("distance_km") or {}).get("mapped_km")
        rebuilt = path_length_m(points) / 1000
        if mapped and abs(rebuilt - mapped) > 0.15 * mapped:
            result["status"] = "unresolved"
            result["notes"].append(f"rebuilt OSM geometry is {rebuilt:.2f} km, recorded {mapped} km; not sampled")
            return result

    if trail.get("max_elevation_m") is None or trail.get("elevation_gain_m") is None:
        elevation = elevation_for(points, route_type, trail)
        if elevation is None:
            result["notes"].append("CDEM profile unavailable or incomplete")
        else:
            result["elevation_check"] = elevation
            for field in ("max_elevation_m", "elevation_gain_m"):
                if trail.get(field) is None:
                    result["set"][field] = elevation[field]
    still = [f for f in missing if f not in result["set"]]
    result["status"] = "filled" if not still else ("partial" if result["set"] else "unresolved")
    result["still_missing"] = still
    return result


def cmd_propose(args):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    trails = [t for t in catalog["trails"] if any(t.get(f) is None for f in FIELDS)]
    if args.only:
        trails = [t for t in trails if t["rank"] in args.only]
    proposals = []
    for i, trail in enumerate(trails, 1):
        print(f"[{i}/{len(trails)}] #{trail['rank']} {trail['name']}", flush=True)
        proposal = propose_one(trail, cache_dir)
        print(f"    {proposal['status']}: {proposal['set']} {'; '.join(proposal['notes'])}", flush=True)
        proposals.append(proposal)
        Path(args.out).write_text(json.dumps(proposals, indent=1, ensure_ascii=False), encoding="utf-8")
    counts = {f: sum(1 for p in proposals if f in p["set"]) for f in FIELDS}
    print(f"\nTrails considered: {len(proposals)}  fills per field: {counts}")


def cmd_apply(args):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    proposals = {p["rank"]: p for p in json.loads(Path(args.proposal).read_text(encoding="utf-8"))}
    today = date.today().isoformat()
    changed = 0
    for trail in catalog["trails"]:
        proposal = proposals.get(trail["rank"])
        if not proposal or not proposal["set"]:
            continue
        verification = trail.setdefault("verification", {})
        flags = verification.setdefault("flags", [])
        for field, value in proposal["set"].items():
            if trail.get(field) is not None:
                continue  # filled since the proposal was made; never overwrite
            trail[field] = value
            changed += 1
            flags[:] = [f for f in flags if not f.startswith(f"{field}:")]
        if "distance_km" in proposal["set"]:
            verification["distance_km"] = proposal["verification_distance"]
            if proposal.get("route_note", "").startswith("inferred"):
                flags.append(f"route_type: {proposal['route_note']}")
        check = proposal.get("elevation_check")
        if check:
            for field in ("max_elevation_m", "elevation_gain_m"):
                if field in proposal["set"]:
                    verification[field] = {
                        "source": "nrcan_cdem",
                        "note": f"sampled along the OSM route {today}; trailhead {check['trailhead_m']} m",
                    }
    catalog["meta"].setdefault("elevation_source", (
        "Elevations marked nrcan_cdem in verification: Canadian Digital Elevation Model, Natural Resources "
        "Canada, sampled along the OSM route. Contains information licensed under the Open Government "
        "Licence – Canada."
    ))
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Applied {changed} field values to {CATALOG.name}. Run scripts/seed_trails.py --dry-run next.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose", help="query OSM and CDEM, write a proposal; changes nothing")
    propose.add_argument("--out", required=True)
    propose.add_argument("--cache", default=".overpass-cache")
    propose.add_argument("--only", type=int, nargs="*", help="limit to these catalogue ranks")
    apply = sub.add_parser("apply", help="write a reviewed proposal into the catalogue JSON")
    apply.add_argument("proposal")
    args = parser.parse_args()
    {"propose": cmd_propose, "apply": cmd_apply}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
