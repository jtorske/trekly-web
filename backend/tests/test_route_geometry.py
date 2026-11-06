"""Geometry, smoothing and validation rules behind the trail route data."""

import math
import random

import pytest

from app import route_geometry as g

# ~111 m per 0.001 degree of latitude.
NORTH = [(51.0 + i * 0.001, -116.0) for i in range(11)]  # ~1.11 km straight line


def test_path_length_and_hiked_distance():
    assert g.path_length_m(NORTH) == pytest.approx(1112, abs=2)
    assert g.hiked_distance_km(NORTH, "out_and_back") == pytest.approx(2.224, abs=0.005)
    assert g.hiked_distance_km(NORTH, "point_to_point") == pytest.approx(1.112, abs=0.003)


def square(side_deg=0.01):
    return [(51.0, -116.0), (51.0 + side_deg, -116.0), (51.0 + side_deg, -116.0 + side_deg * 1.6),
            (51.0, -116.0 + side_deg * 1.6), (51.0, -116.0)]


def test_route_type_from_geometry():
    assert g.route_type_for(square()) == "loop"
    assert g.route_type_for(square(), "point_to_point") == "loop"  # closed beats the spec
    assert g.route_type_for(NORTH) == "out_and_back"
    assert g.route_type_for(NORTH, "point_to_point") == "point_to_point"
    assert g.route_type_for(NORTH, "loop") == "out_and_back"  # spec expected a loop; flagged in the report
    with pytest.raises(ValueError):
        g.route_type_for(NORTH, "figure_eight")
    # A short there-and-back scribble is not a loop just because its ends meet.
    assert not g.is_loop([(51.0, -116.0), (51.0005, -116.0), (51.0, -116.0)])


def test_hiked_line_doubles_out_and_back():
    line = g.hiked_line(NORTH, "out_and_back")
    assert line[0] == line[-1] == NORTH[0]
    assert len(line) == 2 * len(NORTH) - 1
    assert g.hiked_line(square(), "loop") == square()


def test_resample_spacing_and_ends():
    points = g.resample(NORTH, 25)
    assert points[0] == NORTH[0]
    assert points[-1] == pytest.approx(NORTH[-1])
    gaps = [g.haversine_m(a, b) for a, b in zip(points, points[1:])]
    assert max(gaps) - min(gaps) < 0.5
    assert sum(gaps) == pytest.approx(g.path_length_m(NORTH), rel=1e-6)


def test_simplify_keeps_corners_drops_collinear():
    line = NORTH + [(51.01, -116.0 + i * 0.001) for i in range(1, 6)]
    simple = g.simplify(line, 5)
    assert simple == [NORTH[0], NORTH[-1], line[-1]]


def test_ascent_ignores_noise_on_flat_ground():
    random.seed(1)
    flat = [1500 + random.uniform(-3, 3) for _ in range(400)]  # 10 km of +/-3 m DEM noise
    assert g.ascent_m(g.smooth(flat)) < 10
    # Unsmoothed, the same noise would add hundreds of metres.
    assert g.ascent_m(flat, threshold_m=0) > 300


def test_ascent_counts_a_steady_climb_in_full():
    climb = [1000 + i * 2 for i in range(250)]  # 2 m per 25 m sample, 498 m
    assert g.ascent_m(g.smooth(climb)) == pytest.approx(498, abs=15)


def test_ascent_counts_each_real_hill():
    random.seed(2)
    # Three rounded 100 m hills, 1 km each, with DEM-like noise.
    hills = [1000 + 50 * (1 - math.cos(2 * math.pi * i / 40)) + random.gauss(0, 1.5) for i in range(121)]
    assert g.ascent_m(g.smooth(hills)) == pytest.approx(300, rel=0.05)


def test_profile_counts_return_climbs_for_out_and_back():
    # Up 200 m, down 100 m to the turnaround: the walk back climbs 100 m again.
    line = g.resample([(51.0, -116.0), (51.02, -116.0)], 25)

    def sample(points):
        n = len(points)
        return [1000 + 200 * (i / (n / 2)) if i < n / 2 else 1200 - 100 * ((i - n / 2) / (n / 2)) for i in range(n)]

    profile = g.profile_for(line, "out_and_back", sample)
    # The peak here is a sharp cusp crossed twice; smoothing rounds off
    # about 8 m each time, the accepted cost of not counting DEM noise.
    assert profile.gain_m == pytest.approx(300, abs=20)
    assert profile.high_m == pytest.approx(1200, abs=3)
    assert profile.trailhead_m == pytest.approx(1000, abs=10)
    one_way = g.profile_for(line, "point_to_point", sample)
    assert one_way.gain_m == pytest.approx(200, abs=15)
    assert profile.distances_km[-1] == pytest.approx(2.22, abs=0.01)  # chart runs to the turnaround


def test_profile_needs_dem_coverage():
    assert g.profile_for(NORTH, "loop", lambda points: [None] * len(points)) is None


def test_chart_points_thinned():
    line = g.resample([(51.0, -116.0), (51.5, -116.0)], 25)
    profile = g.profile_for(line, "point_to_point", lambda points: [1000.0] * len(points))
    chart = g.chart_points(profile, max_points=100)
    assert len(chart) == 100
    assert chart[0] == [0.0, 1000] and chart[-1][0] == pytest.approx(55.6, abs=0.1)


def ladder():
    """Two parallel paths joined at both ends, plus a spur."""
    graph = g.Graph()
    west = [(51.0 + i * 0.001, -116.0) for i in range(11)]
    east = [(51.0 + i * 0.001, -115.998) for i in range(11)]
    graph.add_way(west)
    graph.add_way(east)
    graph.add_way([west[0], east[0]])
    graph.add_way([west[-1], east[-1]])
    graph.add_way([west[5], (51.005, -116.01)])  # spur to a lake
    return graph, west, east


def test_route_through_waypoints():
    graph, west, _ = ladder()
    points, notes = g.route_through(graph, [west[0], (51.005, -116.01)])
    assert points[0] == west[0] and points[-1] == (51.005, -116.01)
    assert notes == []


def test_loop_routing_prefers_not_to_retrace():
    graph, west, east = ladder()
    points, _ = g.route_through(graph, [west[0], east[-1], west[0]])
    assert g.is_loop(points)
    # Out one side and back the other, not twice along the same side.
    assert len(set(zip(points, points[1:])) & {(b, a) for a, b in zip(points, points[1:])}) == 0


def test_route_through_rejects_far_waypoints():
    graph, west, _ = ladder()
    points, notes = g.route_through(graph, [west[0], (51.2, -116.0)])
    assert points is None and "from the nearest mapped path" in notes[0]


def test_chain_joins_reversed_and_gapped_members():
    a = [(51.0, -116.0), (51.001, -116.0)]
    b = [(51.003, -116.0), (51.0012, -116.0)]  # reversed, ~22 m gap
    c = [(51.003, -116.0), (51.004, -116.0)]
    line, gap = g.chain([c, a, b], near=(51.0, -116.0))
    assert line[0] == a[0] and line[-1] == c[-1]
    assert gap == pytest.approx(22, abs=2)


@pytest.mark.parametrize("trail, expected", [
    ({"distance_km": 10, "elevation_gain_m": 800, "max_elevation_m": 2400}, []),
    ({"distance_km": 2, "elevation_gain_m": 900}, ["m/km"]),
    ({"distance_km": 12, "elevation_gain_m": 0}, ["too flat"]),
    ({"max_elevation_m": 1200, "trailhead_m": 1500}, ["below the trailhead"]),
    ({"route_type": "loop", "ends_apart_m": 2500}, ["loop ends"]),
    ({"route_type": "loop", "ends_apart_m": 50}, []),
    ({"distance_km": 45, "nights": 0}, ["day hike over 40 km"]),
    ({"distance_km": 45, "nights": 2}, []),
    ({"max_elevation_m": 7000}, ["outside Canada"]),
])
def test_validate(trail, expected):
    flags = g.validate(trail)
    assert len(flags) == len(expected)
    for flag, text in zip(flags, expected):
        assert text in flag


def test_disagreement():
    assert g.disagreement(11.5, 10) == pytest.approx(0.15)
    assert g.disagreement(None, 10) is None
    assert g.disagreement(10, None) is None
