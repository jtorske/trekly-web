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
    ("Meadow.jpg", 12000, "park", "Park: 12 km from the route"),
    # A nearby peak named in a shot from town is decided by its geotag...
    ("Mount Bourgeau from Banff.jpg", 15000, "park", "Park: 15 km from the route"),
    ("Mount Bourgeau summit.jpg", 2000, "medium", "2.0 km from the route"),
    # ... and an untagged one is likely at best.
    ("Mount Bourgeau.jpg", None, "medium", "Names Mount Bourgeau, near the trail"),
    ("Somewhere.jpg", None, "park", "Park or region match only"),
])
def test_trail_nearby_park(title, distance, expected, match):
    assert search.classify(photo(title, distance), TERMS, "route") == (expected, match)
    assert search.LABELS[expected] in ("trail", "nearby", "park")


def test_park_wide_landmarks_only_say_park():
    terms = TERMS + [("Mount Edith Cavell", frozenset({"edith", "cavell"}), False, 9000)]
    assert search.classify(photo("Edith Cavell at sunrise", None), terms, "route") == ("park", "Park: names Mount Edith Cavell")
    park = [frozenset({"jasper"})]
    assert search.classify(photo("Jasper National Park", None), TERMS, "route", park) == ("park", "Park: names the park")


def test_older_weak_labels_read_as_park():
    assert search.LABELS["off_topic"] == search.LABELS["low"] == "park"


def pixabay_hit(**extra):
    return {"id": 42, "type": "photo", "pageURL": "https://pixabay.com/photos/maligne-lake-jasper-42/",
            "tags": "maligne lake, jasper, alberta, canada", "heading": "Maligne Lake photo", "imageWidth": 6000,
            "imageHeight": 4000, "largeImageURL": "https://pixabay.com/get/x_1280.jpg",
            "webformatURL": "https://pixabay.com/get/x_640.jpg", "user": "someone", **extra}


def test_pixabay_hits_are_scaled_to_1280_and_ai_images_dropped():
    [c] = search.pixabay_candidates({"hits": [pixabay_hit(), pixabay_hit(id=43, isAiGenerated=True)]})
    assert (c["width"], c["height"]) == (1280, 853)
    assert c["id"] == "pixabay:42" and c["title"] == "Maligne Lake" and c["origin"] == "Pixabay"
    assert c["license"] == "Pixabay Content License" and c["source_url"].startswith("https://pixabay.com/photos/")
    assert "maligne lake jasper" in c["_categories"]


def test_stock_hits_must_name_the_place_its_region_and_canada():
    terms, region = [frozenset({"maligne", "lake"})], [frozenset({"jasper"})]
    [ok] = search.pixabay_candidates({"hits": [pixabay_hit()]})
    assert search.rejection(ok, terms=terms, region=region) is None  # 1280px is allowed for Pixabay
    [abroad] = search.pixabay_candidates({"hits": [pixabay_hit(tags="maligne lake, jasper, oregon, usa")]})
    assert search.rejection(abroad, terms=terms, region=region) is not None
    [no_country] = search.pixabay_candidates({"hits": [pixabay_hit(tags="maligne lake, jasper", pageURL="https://pixabay.com/photos/x-42/")]})
    assert search.rejection(no_country, terms=terms, region=region) == "stock photo doesn't say it's in Canada"


def test_merge_keeps_earlier_candidates_relabels_weak_and_checks_they_load(monkeypatch):
    monkeypatch.setattr(search, "url_loads", lambda url: "broken" not in url)
    def cand(i, conf, url="https://upload.wikimedia.org/a.jpg", width=2000):
        return {"id": f"commons:{i}", "origin": "Wikimedia Commons", "title": f"P{i}.jpg", "source_url": None,
                "confidence": conf, "image_url": url + str(i), "preview_url": url + str(i), "width": width, "score": 1}
    result = {"candidates": [cand(1, "park")], "rejected": {}}
    earlier = {"candidates": [cand(2, "high"), cand(3, "off_topic"), cand(4, "medium", url="https://broken/"), cand(1, "high")]}
    merged = search.merge_earlier(result, earlier, top=5, min_width=1600)
    assert [c["id"] for c in merged["candidates"]] == ["commons:2", "commons:1", "commons:3"]
    assert merged["candidates"][2]["confidence"] == "park"
    assert merged["default_choice"] == "commons:2"
    assert merged["counts"] == {"trail": 1, "nearby": 0, "park": 2}
    assert merged["rejected"]["image no longer loads"] == 1


def test_stock_photos_must_name_a_place_as_a_phrase_in_one_field():
    terms = [("Rock Lake", frozenset({"rock", "lake"}), True), ("Fishing Cove", frozenset({"fishing", "cove"}), True),
             ("Hermit", frozenset({"hermit"}), True), ("Brazeau Lake", frozenset({"brazeau", "lake"}), False, 2000)]
    def stock(title, tags):
        return {"title": title, "description": "", "_categories": tags}
    # Words scattered across tags, or a one-word name, don't count.
    assert search.classify_stock(stock("Turquoise lake", ["rock", "lake", "jasper"]), terms, None) is None
    assert search.classify_stock(stock("Peggy's Cove fishing village", ["fishing village", "cove"]), terms, None) is None
    assert search.classify_stock(stock("The hermit", ["hermit"]), terms, None) is None
    assert search.classify_stock(stock("Morning at Rock Lake", []), terms, None) == ("high", "Names Rock Lake")
    assert search.classify_stock(stock("x", ["brazeau lake"]), terms, None) == ("medium", "Names Brazeau Lake, near the trail")
    assert search.classify_stock(stock("x", ["jasper national park"]), terms, "Jasper National Park") == ("park", "Park: names the park")
