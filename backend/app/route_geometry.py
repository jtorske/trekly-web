"""Pure geometry for trail routes: routing, measuring, smoothing, validation.

Points are (lat, lon) tuples in degrees; distances are metres unless a name
says km. Nothing here touches the network or a DEM, so it's all unit-tested
(tests/test_route_geometry.py). scripts/trail_routes.py does the fetching.

Definitions (also shown in the "How ranks work" dialog and trail pages):
- distance_km is what a hiker covers: the round trip for an out-and-back,
  the full loop, or the one-way length of a point-to-point.
- elevation_gain_m is the total climbing over that same hike (cumulative
  ascent of the smoothed profile), so an out-and-back counts the climbs on
  the way back too.
- max_elevation_m is the highest point on the route.
"""

import heapq
import math
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6371008.8
LOOP_CLOSE_M = 200  # ends this close together make a loop
SAMPLE_STEP_M = 25  # elevation sample spacing along the hiked line
SMOOTH_WINDOW_M = 100  # moving-average window before counting ascent
ASCENT_THRESHOLD_M = 4  # hysteresis: rises smaller than this are noise
DAY_HIKE_MAX_KM = 40


# ---------------------------------------------------------------- distance

def haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def path_length_m(points):
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def cumulative_m(points):
    out, total = [0.0], 0.0
    for i in range(1, len(points)):
        total += haversine_m(points[i - 1], points[i])
        out.append(total)
    return out


def is_loop(points, close_m=LOOP_CLOSE_M):
    return len(points) > 2 and haversine_m(points[0], points[-1]) <= close_m and path_length_m(points) > 4 * close_m


def route_type_for(points, line_kind="out_and_back"):
    """loop when the ends meet; otherwise the spec's choice for a line.

    A spec that expects a loop but whose geometry doesn't close falls back to
    out-and-back (the validation report flags the mismatch)."""
    if line_kind not in ("out_and_back", "point_to_point", "loop"):
        raise ValueError(f"bad line kind {line_kind!r}")
    if is_loop(points):
        return "loop"
    return "out_and_back" if line_kind == "loop" else line_kind


def hiked_line(points, route_type):
    """The line a hiker actually walks: out and back doubles the route."""
    if route_type == "out_and_back":
        return list(points) + list(reversed(points))[1:]
    return list(points)


def hiked_distance_km(points, route_type):
    return path_length_m(hiked_line(points, route_type)) / 1000


def resample(points, step_m=SAMPLE_STEP_M):
    """Evenly spaced points along the line (both ends kept)."""
    if len(points) < 2:
        return list(points)
    cum = cumulative_m(points)
    total = cum[-1]
    if total == 0:
        return [points[0]]
    n = max(1, round(total / step_m))
    out, j = [], 0
    for i in range(n + 1):
        target = total * i / n
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j]
        f = 0.0 if seg == 0 else (target - cum[j]) / seg
        a, b = points[j], points[j + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


# ---------------------------------------------------------------- simplify

def _xy(p, ref_lat):
    k = math.cos(math.radians(ref_lat))
    return (math.radians(p[1]) * k * EARTH_RADIUS_M, math.radians(p[0]) * EARTH_RADIUS_M)


def _segment_distance(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def simplify(points, tolerance_m=5.0):
    """Douglas-Peucker, iterative so long routes don't hit the recursion limit."""
    if len(points) < 3:
        return list(points)
    ref = sum(p[0] for p in points) / len(points)
    xy = [_xy(p, ref) for p in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        best, index = 0.0, None
        for k in range(i + 1, j):
            d = _segment_distance(xy[k], xy[i], xy[j])
            if d > best:
                best, index = d, k
        if index is not None and best > tolerance_m:
            keep[index] = True
            stack.extend(((i, index), (index, j)))
    return [p for p, k in zip(points, keep) if k]


# ---------------------------------------------------------------- elevation

def smooth(values, step_m=SAMPLE_STEP_M, window_m=SMOOTH_WINDOW_M):
    """Centred moving average over window_m; None values are skipped."""
    half = max(0, round(window_m / step_m / 2))
    out = []
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - half): i + half + 1] if v is not None]
        out.append(sum(chunk) / len(chunk) if chunk else None)
    return out


def ascent_m(values, threshold_m=ASCENT_THRESHOLD_M):
    """Cumulative climb, ignoring wiggles smaller than threshold_m.

    Hysteresis: a rise only counts once it clears the threshold above the
    lowest point since the last counted climb, so DEM noise on flat ground
    adds nothing while a real, steady climb counts in full.
    """
    known = [v for v in values if v is not None]
    if not known:
        return 0.0
    total, anchor, rising = 0.0, known[0], False
    for v in known[1:]:
        if rising:
            if v > anchor:
                total += v - anchor
                anchor = v
            elif anchor - v >= threshold_m:
                rising, anchor = False, v
        else:
            if v < anchor:
                anchor = v
            elif v - anchor >= threshold_m:
                total += v - anchor
                rising, anchor = True, v
    return total


@dataclass
class Profile:
    distances_km: list
    elevations_m: list  # smoothed, as drawn on the chart
    gain_m: int
    high_m: int
    high_index: int  # index into the (one-way) route samples
    trailhead_m: int
    low_m: int


def profile_for(route_points, route_type, sample, step_m=SAMPLE_STEP_M):
    """Elevation profile and gain for a route.

    `sample(points)` returns raw DEM elevations (None where there's no data).
    The chart shows the route as mapped (one way for an out-and-back, with
    the x-axis running to the turnaround); gain is counted over the hiked
    line, so the return leg's climbs count.
    """
    points = resample(route_points, step_m)
    raw = sample(points)
    if sum(v is not None for v in raw) < max(5, 0.9 * len(raw)):
        return None
    smoothed = smooth(raw, step_m)
    hiked = smoothed + list(reversed(smoothed))[1:] if route_type == "out_and_back" else smoothed
    known = [(v, i) for i, v in enumerate(raw) if v is not None]
    high, high_index = max(known)
    cum = cumulative_m(points)
    first = next(v for v in smoothed if v is not None)
    return Profile(
        distances_km=[c / 1000 for c in cum],
        elevations_m=smoothed,
        gain_m=round(ascent_m(hiked)),
        high_m=round(high),
        high_index=high_index,
        trailhead_m=round(first),
        low_m=round(min(v for v, _ in known)),
    )


def chart_points(profile, max_points=600):
    """[[km, m], ...] thinned to at most max_points for the trail page chart."""
    pairs = [(d, e) for d, e in zip(profile.distances_km, profile.elevations_m) if e is not None]
    if len(pairs) > max_points:
        step = (len(pairs) - 1) / (max_points - 1)
        pairs = [pairs[round(i * step)] for i in range(max_points)]
    return [[round(d, 3), round(e)] for d, e in pairs]


# ---------------------------------------------------------------- routing

@dataclass
class Graph:
    """Undirected path network from OSM ways, keyed by rounded node coordinates."""
    edges: dict = field(default_factory=dict)  # node -> {neighbour: cost}
    lengths: dict = field(default_factory=dict)  # (a, b) -> metres
    names: dict = field(default_factory=dict)  # (a, b) -> way name, for review output
    way_ids: dict = field(default_factory=dict)  # (a, b) -> OSM way id, for provenance

    def add_way(self, geometry, penalty=1.0, name=None, way_id=None):
        for a, b in zip(geometry, geometry[1:]):
            ka, kb = _node(a), _node(b)
            if ka == kb:
                continue
            length = haversine_m(ka, kb)
            cost = length * penalty
            for x, y in ((ka, kb), (kb, ka)):
                if cost < self.edges.setdefault(x, {}).get(y, math.inf):
                    self.edges[x][y] = cost
                    self.lengths[(x, y)] = length
                    if name:
                        self.names[(x, y)] = name
                    if way_id is not None:
                        self.way_ids[(x, y)] = way_id

    def nearest(self, point):
        if not self.edges:
            return None, math.inf
        node = min(self.edges, key=lambda n: haversine_m(n, point))
        return node, haversine_m(node, point)

    def distances(self, start):
        """Shortest real distance (m, not cost) from start to every reachable node."""
        dist, queue = {start: 0.0}, [(0.0, start)]
        while queue:
            d, node = heapq.heappop(queue)
            if d > dist.get(node, math.inf):
                continue
            for n in self.edges.get(node, {}):
                nd = d + self.lengths[(node, n)]
                if nd < dist.get(n, math.inf):
                    dist[n] = nd
                    heapq.heappush(queue, (nd, n))
        return dist

    def component(self, near):
        """Subgraph connected to the node nearest `near`."""
        start, _ = self.nearest(near)
        seen, stack = {start}, [start]
        while stack:
            for n in self.edges[stack.pop()]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        sub = Graph()
        for a in seen:
            sub.edges[a] = dict(self.edges[a])
            for b in sub.edges[a]:
                sub.lengths[(a, b)] = self.lengths[(a, b)]
                if (a, b) in self.names:
                    sub.names[(a, b)] = self.names[(a, b)]
                if (a, b) in self.way_ids:
                    sub.way_ids[(a, b)] = self.way_ids[(a, b)]
        return sub

    def shortest_path(self, start, end, avoid=frozenset(), avoid_factor=4.0):
        """Dijkstra from start to end. Edges in `avoid` cost avoid_factor more,
        so a loop's second half prefers not to retrace the first."""
        dist, previous, queue = {start: 0.0}, {}, [(0.0, start)]
        while queue:
            d, node = heapq.heappop(queue)
            if node == end:
                break
            if d > dist.get(node, math.inf):
                continue
            for n, cost in self.edges.get(node, {}).items():
                if (node, n) in avoid:
                    cost *= avoid_factor
                nd = d + cost
                if nd < dist.get(n, math.inf):
                    dist[n], previous[n] = nd, node
                    heapq.heappush(queue, (nd, n))
        if end not in dist:
            return None
        path = [end]
        while path[-1] != start:
            path.append(previous[path[-1]])
        return path[::-1]


def names_along(graph, points):
    """[(name, km), ...]: the named ways a route follows, in order."""
    out = []
    for a, b in zip(points, points[1:]):
        name = graph.names.get((a, b), "(unnamed)")
        km = graph.lengths.get((a, b), haversine_m(a, b)) / 1000
        if out and out[-1][0] == name:
            out[-1][1] += km
        else:
            out.append([name, km])
    return [(n, round(k, 2)) for n, k in out if k >= 0.05]


def ways_along(graph, points):
    """OSM way ids a route follows, in order, each once."""
    out = []
    for a, b in zip(points, points[1:]):
        wid = graph.way_ids.get((a, b))
        if wid is not None and wid not in out:
            out.append(wid)
    return out


def _node(p):
    return (round(p[0], 6), round(p[1], 6))


def route_through(graph, waypoints, snap_limit_m=400):
    """Route over the graph through each waypoint in order.

    Returns (points, notes). Fails (None) when a waypoint is further than
    snap_limit_m from the network or two waypoints aren't connected.
    """
    nodes, notes = [], []
    for i, w in enumerate(waypoints):
        node, d = graph.nearest(w)
        if node is None or d > snap_limit_m:
            return None, [f"waypoint {i + 1} is {d:.0f} m from the nearest mapped path"]
        if d > 100:
            notes.append(f"waypoint {i + 1} snapped {d:.0f} m to the path")
        nodes.append(node)
    points, used = [nodes[0]], set()
    for a, b in zip(nodes, nodes[1:]):
        leg = graph.shortest_path(a, b, avoid=used)
        if leg is None:
            return None, notes + ["waypoints aren't connected by mapped paths"]
        used.update(zip(leg, leg[1:]))
        used.update(zip(leg[1:], leg))
        points.extend(leg[1:])
    return points, notes


def longest_route(graph, start=None, end=None):
    """The longest end-to-end path through a (named-trail) network.

    With neither end given, the two dead ends furthest apart; with `start`,
    the dead end furthest from it; with both, the path between them. This
    is how a named trail's own ways become its route: the trail runs from
    one end of the named network to the other.
    """
    if start is not None:
        start = graph.nearest(start)[0]
    if end is not None:
        end = graph.nearest(end)[0]
    leaves = [n for n, e in graph.edges.items() if len(e) == 1] or list(graph.edges)[:1]
    if start is None and end is None:
        best = (-1, None, None)
        for leaf in leaves:
            dist = graph.distances(leaf)
            far = max(leaves, key=lambda n: dist.get(n, -1))
            if dist.get(far, -1) > best[0]:
                best = (dist[far], leaf, far)
        start, end = best[1], best[2]
    elif end is None:
        dist = graph.distances(start)
        end = max(leaves, key=lambda n: dist.get(n, -1))
    elif start is None:
        dist = graph.distances(end)
        start = max(leaves, key=lambda n: dist.get(n, -1))
    if start is None or end is None or start == end:
        return None
    return graph.shortest_path(start, end)


# ---------------------------------------------------------------- chaining

def chain(ways, near=None):
    """Join way geometries into one line, bridging small gaps.

    Unlike a strict chain, this tolerates the messiness of real route
    relations (members out of order or reversed, tiny gaps between them):
    ways are greedily joined end-to-end, nearest end first, starting from
    the end nearest `near`. Returns (points, largest_gap_m).
    """
    pieces = [list(w) for w in ways if len(w) >= 2]
    if not pieces:
        return None, None
    if near is None:
        near = pieces[0][0]
    # Start with the piece whose end is nearest `near`, oriented away from it.
    best = min(range(len(pieces)), key=lambda i: min(haversine_m(pieces[i][0], near), haversine_m(pieces[i][-1], near)))
    first = pieces.pop(best)
    if haversine_m(first[-1], near) < haversine_m(first[0], near):
        first.reverse()
    line, largest = first, 0.0
    while pieces:
        tail = line[-1]
        i = min(range(len(pieces)), key=lambda k: min(haversine_m(pieces[k][0], tail), haversine_m(pieces[k][-1], tail)))
        piece = pieces.pop(i)
        if haversine_m(piece[-1], tail) < haversine_m(piece[0], tail):
            piece.reverse()
        gap = haversine_m(piece[0], tail)
        largest = max(largest, gap)
        line.extend(piece[1:] if gap < 1 else piece)
    return line, largest


# ---------------------------------------------------------------- validation

def validate(trail):
    """Plausibility flags for one trail's final values.

    `trail` keys: distance_km, route_type, elevation_gain_m, max_elevation_m,
    trailhead_m (measured start elevation, if any), nights, ends_apart_m
    (distance between the route's ends, if geometry exists).
    Returns a list of short human-readable flags; empty means plausible.
    """
    flags = []
    km, gain, high = trail.get("distance_km"), trail.get("elevation_gain_m"), trail.get("max_elevation_m")
    nights = trail.get("nights") or 0
    if km is not None and gain is not None and km > 0:
        per_km = gain / km
        # The Grouse Grind, the steepest trail in the catalogue, climbs about
        # 320 m/km (800 m in 2.5 km); past 350 m/km the number is suspect.
        if per_km > 350:
            flags.append(f"gain {gain} m over {km} km is {per_km:.0f} m/km, steeper than any real trail")
    if gain is not None and km is not None and km >= 5 and gain < 5:
        flags.append(f"gain {gain} m over {km} km looks too flat")
    trailhead = trail.get("trailhead_m")
    if high is not None and trailhead is not None and high < trailhead:
        flags.append(f"high point {high} m is below the trailhead ({trailhead} m)")
    ends = trail.get("ends_apart_m")
    if trail.get("route_type") == "loop" and ends is not None and ends > LOOP_CLOSE_M:
        flags.append(f"loop ends {ends:.0f} m apart")
    if nights == 0 and km is not None and km > DAY_HIKE_MAX_KM:
        flags.append(f"day hike over {DAY_HIKE_MAX_KM} km ({km} km)")
    if high is not None and not (0 <= high <= 6000):
        flags.append(f"high point {high} m is outside Canada's range")
    return flags


def disagreement(measured, published):
    """Relative difference of measured from published (0.2 = 20%)."""
    if measured is None or not published:
        return None
    return abs(measured - published) / published
