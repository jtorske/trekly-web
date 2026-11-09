"""The route-aware rules in scripts/find_trail_photos.py (no network)."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "find_trail_photos", Path(__file__).resolve().parent.parent / "scripts" / "find_trail_photos.py"
)
search = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(search)

# About 11 km due north from 51.0, -116.0.
LINE = [(51.0, -116.0), (51.05, -116.0), (51.1, -116.0)]


def test_distance_to_a_route_is_measured_to_its_nearest_segment():
    # 0.01 deg of longitude at 51 N is about 700 m.
    assert search.distance_to_line((51.07, -116.01), LINE) == pytest.approx(700, rel=0.02)
    assert search.distance_to_line((51.05, -116.0), LINE) < 1
    # Past the end, it's the distance to the end point.
    assert search.distance_to_line((51.11, -116.0), LINE) == pytest.approx(1112, rel=0.02)


def test_route_samples_every_3_km_plus_the_ends_and_extras():
    line = [(51.0 + i * 0.001, -116.0) for i in range(101)]  # ~11 km
    points = search.sample_points(line, extra=[(51.03, -116.02)])
    assert points[0] == line[0] and line[-1] in points
    assert (51.03, -116.02) in points
    assert 5 <= len(points) <= 7


def test_landmarks_need_a_name_of_their_own():
    park = set(search.fold("Jasper National Park").split()) | search.REGION_FILLER
    assert search.is_landmark("Brazeau Lake", park)
    assert search.is_landmark("Mount Fryatt", park)
    assert not search.is_landmark("Falls", park)
    assert not search.is_landmark("Jasper National Park", park)
    assert not search.is_landmark("Mount Jasper", park)  # the park's own name
    assert not search.is_landmark("Marmot Basin Ski Resort", park)
    assert search.clean_place("Mount Revelstoke's") == "Mount Revelstoke"
    assert search.clean_place("Lake Louise, Alberta") == "Lake Louise"


def test_campground_codes_and_qualifiers_are_dropped():
    links = {("T", "AB"): [{"name": "Jo9 Johnston Canyon"}, {"name": "Pachena Bay (North)"},
                           {"name": "Gordon River - South"}, {"name": "Backcountry Campground"}]}
    assert search.campground_names({"name": "T", "province_code": "AB"}, links) == [
        "Johnston Canyon", "Pachena Bay", "Gordon River", "Backcountry Campground"]
    park = search.REGION_FILLER
    assert not search.is_campground_name("Backcountry Campground", park)


def photo(title, distance_m):
    return {"title": title, "description": "", "_categories": [], "distance_m": distance_m}


TERMS = [
    ("Brazeau Lake", frozenset({"brazeau", "lake"}), True),
    ("Mount Bourgeau", frozenset({"mount", "bourgeau"}), False),  # 2 km off the route
]


@pytest.mark.parametrize("title,distance,expected,match", [
    ("Brazeau Lake at dawn.jpg", 9000, "high", "Names Brazeau Lake"),
    ("Meadow.jpg", 400, "high", "0.4 km from the route"),
    ("Meadow.jpg", 2500, "medium", "2.5 km from the route"),
    ("Meadow.jpg", 12000, "off_topic", "Regional: 12 km from the route"),
    # A nearby peak named in a shot from town is decided by its geotag...
    ("Mount Bourgeau from Banff.jpg", 15000, "off_topic", "Regional: 15 km from the route"),
    ("Mount Bourgeau summit.jpg", 2000, "medium", "2.0 km from the route"),
    # ... and an untagged one is likely at best.
    ("Mount Bourgeau.jpg", None, "medium", "Names Mount Bourgeau, near the trail"),
    ("Somewhere.jpg", None, "off_topic", "Park or region match only"),
])
def test_strong_likely_weak(title, distance, expected, match):
    assert search.classify(photo(title, distance), TERMS, "route") == (expected, match)
    assert search.LABELS[expected] in ("strong", "likely", "weak")
