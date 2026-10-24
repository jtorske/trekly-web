"""Geometry rules of scripts/backfill_trail_measures.py (no network)."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "backfill_trail_measures", Path(__file__).resolve().parent.parent / "scripts" / "backfill_trail_measures.py"
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)

# Points ~111 m apart along a meridian.
LINE = [(51.0 + i * 0.001, -116.0) for i in range(11)]


def trail(role="start", lat=51.0, lon=-116.0, nights=0):
    return {"latitude": lat, "longitude": lon, "typical_duration_nights": nights,
            "verification": {"coordinates": {"role": role}}}


def test_chain_joins_ways_in_order():
    points = backfill.chain([LINE[5:], LINE[:6]])
    assert points in (LINE, list(reversed(LINE)))


def test_chain_rejects_branches_and_gaps():
    branch = [LINE[5], (51.005, -115.99)]
    assert backfill.chain([LINE, branch]) is None
    assert backfill.chain([LINE[:4], LINE[6:]]) is None


def test_chain_keeps_the_piece_nearest_the_trail():
    elsewhere = [(52.0 + i * 0.001, -117.0) for i in range(5)]
    points = backfill.chain([LINE, elsewhere], near=(51.0, -116.0))
    assert len(points) == len(LINE)


def test_chain_closes_a_loop():
    loop = [(51.0, -116.0), (51.001, -116.0), (51.001, -115.999), (51.0, -115.999), (51.0, -116.0)]
    points = backfill.chain([loop])
    assert points[0] == points[-1] and len(points) == 5


def test_trim_cuts_at_the_named_destination_but_keeps_the_start():
    points, note = backfill.trim(LINE, trail(lat=51.002), destinations=[(51.007, -116.0)])
    assert points[0] == LINE[0] and points[-1] == LINE[7]
    assert note == "cut at the destination"


def test_trim_uses_the_coordinate_when_it_is_the_destination():
    points, note = backfill.trim(LINE, trail(role="destination", lat=51.006), destinations=[])
    assert points[-1] == LINE[6] and note == "cut at the destination"


def test_trim_ignores_far_destinations_and_loops():
    points, note = backfill.trim(LINE, trail(), destinations=[(51.5, -116.0)])
    assert points == LINE and note is None
    loop = LINE + [LINE[0]]
    assert backfill.trim(loop, trail(), destinations=[(51.005, -116.0)]) == (loop, None)


@pytest.mark.parametrize("one_way, nights, route_type, ok", [
    (3.3, 0, "out_and_back", True),
    (25, 0, "out_and_back", False),   # 50 km is not a day hike
    (0.3, 0, "loop", False),
    (75.9, 6, "point_to_point", True),
    (2, 3, "point_to_point", False),
])
def test_plausible_lengths(one_way, nights, route_type, ok):
    assert backfill.plausible(one_way, nights, route_type) is ok


def test_name_parts_split_destinations():
    assert backfill.name_parts("Johnston Canyon to the Ink Pots") == ["Johnston Canyon", "Ink Pots"]
    assert backfill.name_parts("Sentinel Pass via Larch Valley") == ["Sentinel Pass", "Larch Valley"]
    assert backfill.name_parts("Egypt Lake / Healy Pass") == ["Egypt Lake", "Healy Pass"]


def test_destination_part():
    assert backfill.destination_part("Sentinel Pass via Larch Valley", ["Sentinel Pass", "Larch Valley"]) == ["Sentinel Pass"]
    assert backfill.destination_part("Johnston Canyon to the Ink Pots", ["Johnston Canyon", "Ink Pots"]) == ["Ink Pots"]
