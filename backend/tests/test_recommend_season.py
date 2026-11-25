"""Recommendations follow the season: winter trails first in winter, no winter-only trails in summer."""

import uuid
from types import SimpleNamespace

from app.preferences import Preferences, recommend


def trail(name, rank, park, acts=(), winter_only=False, nights=0, terrain="moderate"):
    return SimpleNamespace(id=uuid.uuid4(), name=name, popularity_rank=rank, park_name=park, province_code="AB",
                           typical_duration_nights=nights, terrain_difficulty=terrain,
                           winter_activities=list(acts), is_winter_only=winter_only)


TRAILS = [
    trail("Alpine Pass", 1, "Banff National Park"),
    trail("Glacier Viewpoint", 2, "Jasper National Park"),
    trail("Snowshoe Lake", 3, "Yoho National Park", acts=["snowshoe"]),
    trail("Groomed Road", 4, "Mount Revelstoke National Park", acts=["xc_ski"], winter_only=True),
    trail("Valley Walk", 5, "Kootenay National Park"),
]


def names(trails):
    return [t.name for t in trails]


def test_winter_puts_winter_trails_first_even_against_answers():
    # A day-hiker who loves Banff still sees the winter trails first in winter.
    prefs = Preferences(hiking_style="day", favourite_regions=("banff",), season="winter")
    assert names(recommend(TRAILS, prefs, limit=3))[:2] == ["Snowshoe Lake", "Groomed Road"]


def test_summer_leaves_out_winter_only_trails():
    picked = names(recommend(TRAILS, Preferences(season="summer"), limit=5))
    assert "Groomed Road" not in picked and "Snowshoe Lake" in picked


def test_no_season_keeps_the_old_order():
    assert names(recommend(TRAILS, Preferences(), limit=5)) == [
        "Alpine Pass", "Glacier Viewpoint", "Snowshoe Lake", "Groomed Road", "Valley Walk"]
