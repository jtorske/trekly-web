"""Seasonal picks follow app/season.py: winter picks are winter trails, no fall picks in November."""

from datetime import date

import pytest

from app.models.trail import Trail
from app.models.trail_seasonal_condition import TrailSeasonalCondition
from app.picks import picks
from app.routers.trails import live_trails

SRC = "https://parks.canada.ca/winter"


@pytest.fixture
def db_trails(db):
    def add(rank, name, acts=(), tags=(), highs=None):
        t = Trail(name=name, region="Banff National Park, AB", country_code="CA", province_code="AB",
                  terrain_difficulty="easy", popularity_rank=rank, winter_activities=list(acts),
                  winter_source_url=SRC if acts else None, tags=list(tags))
        db.add(t)
        db.flush()
        for season, high in (highs or {}).items():
            db.add(TrailSeasonalCondition(trail_id=t.id, season=season, avg_low_c=high - 10, avg_high_c=high))
        return t
    add(1, "Alpine Pass", highs={"fall": 12, "winter": 2, "summer": 20, "spring": 8})
    add(2, "Snowshoe Lake", acts=["snowshoe"], highs={"fall": 10, "winter": -5, "summer": 18})
    add(3, "Groomed Road", acts=["xc_ski"], tags=["winter_only"], highs={"summer": 30, "fall": 30})
    db.flush()
    return db


def seasonal(db, day):
    found = [p for p in picks(db, day, [], live_trails()) if p.kind == "seasonal"]
    return found[0] if found else None


def test_winter_pick_is_a_winter_trail_and_never_says_safe(db_trails):
    for day in (date(2026, 11, 24), date(2026, 12, 1), date(2027, 1, 12), date(2027, 3, 30)):
        pick = seasonal(db_trails, day)
        assert pick.title == "A winter pick"
        assert pick.trail.name in ("Snowshoe Lake", "Groomed Road")
        assert "safe" not in pick.text.lower()
        assert "Check conditions" in pick.text


def test_winter_pick_text_names_the_listed_activities(db_trails):
    names = {seasonal(db_trails, date(2027, 1, d)).trail.name: seasonal(db_trails, date(2027, 1, d)).text
             for d in (5, 12)}
    texts = set(names.values())
    assert any("snowshoeing" in t for t in texts) or any("cross-country skiing" in t for t in texts)


def test_no_fall_pick_in_november(db_trails):
    assert seasonal(db_trails, date(2026, 11, 3)) is None


def test_fall_pick_in_october_skips_winter_only_trails(db_trails):
    pick = seasonal(db_trails, date(2026, 10, 5))
    assert pick.title == "A fall pick"
    assert pick.trail.name != "Groomed Road"


def test_summer_pick_skips_winter_only_trails(db_trails):
    # Groomed Road is the warmest in summer but is a winter-only ski track.
    for d in (6, 13, 20, 27):
        assert seasonal(db_trails, date(2027, 7, d)).trail.name != "Groomed Road"
