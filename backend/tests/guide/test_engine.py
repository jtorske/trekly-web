"""Unit tests for Trekly Guide's engine: estimates, profile, scoring, readiness."""

from datetime import date

import pytest

from app.guide import recommend as rec
from app.guide.estimate import format_hours, naismith_hours, scenery_of, this_weekend
from app.guide.profile import (
    STATED_BASELINES,
    HikeRecord,
    StatedPreferences,
    build_profile,
    pace_from,
)
from app.guide.readiness import NOT_YET, READY, STRETCH, readiness
from app.guide.rules import blocker
from app.guide.recommend import WEIGHTS, GuideRequest, recommend
from tests.guide.conftest import make_trail

SUMMER = date(2026, 7, 11)
WINTER = date(2027, 1, 16)
MAY = date(2027, 5, 15)


def hike(trail, on=None, minutes=None):
    return HikeRecord(trail, on, minutes)


def profile_with(*hikes, **prefs):
    return build_profile(list(hikes), StatedPreferences(**prefs))


# The standard "intermediate" history: biggest day 12 km / 800 m.
HA_LING = make_trail("Ha Ling", distance_km=7.2, elevation_gain_m=762, max_elevation_m=2462)
BIG = make_trail("Big Day", distance_km=12.0, elevation_gain_m=800, max_elevation_m=2300)
MID = make_trail("Mid Day", distance_km=9.0, elevation_gain_m=500, max_elevation_m=1900)


@pytest.fixture
def intermediate():
    return profile_with(
        hike(HA_LING, date(2026, 6, 1), 200),
        hike(BIG, date(2026, 6, 20), 300),
        hike(MID, date(2026, 7, 1), 180),
        experience_level="few_seasons",
    )


# ---- estimate -------------------------------------------------------------

def test_naismith():
    assert naismith_hours(10, 600) == pytest.approx(3.0)
    assert naismith_hours(5, None) == pytest.approx(1.0)
    assert naismith_hours(None, 500) is None


def test_this_weekend():
    assert this_weekend(date(2026, 11, 24)) == date(2026, 11, 28)  # Tuesday
    assert this_weekend(date(2026, 11, 28)) == date(2026, 11, 28)  # Saturday
    assert this_weekend(date(2026, 11, 29)) == date(2026, 11, 28)  # Sunday


def test_format_hours():
    assert format_hours(0.4) == "25 min"
    assert format_hours(3.26) == "3.5 h"
    assert format_hours(5.0) == "5 h"


def test_scenery_from_name_and_tags():
    trail = make_trail("Bow Glacier Falls", description="Past a lake to the falls.", tags=("larch",))
    assert {"glaciers", "waterfalls", "lakes", "larches"} <= scenery_of(trail)


# ---- profile --------------------------------------------------------------

def test_pace_defaults_with_fewer_than_three_timed_hikes():
    pace = pace_from([hike(BIG, minutes=300), hike(MID, minutes=180)])
    assert (pace.factor, pace.confidence, pace.timed_hikes) == (1.0, "low", 2)


def test_pace_is_median_ratio_to_naismith(intermediate):
    # Naismith: Ha Ling 2.71 h, Big 3.73 h, Mid 2.63 h; logged 3.33, 5, 3 h.
    ratios = sorted([200 / 60 / naismith_hours(7.2, 762), 300 / 60 / naismith_hours(12, 800),
                     180 / 60 / naismith_hours(9, 500)])
    assert intermediate.pace.factor == pytest.approx(round(ratios[1], 2))
    assert intermediate.pace.confidence == "medium"


def test_pace_is_clamped_and_high_confidence_at_six():
    slow = [hike(make_trail(f"T{i}", distance_km=5, elevation_gain_m=0), minutes=600) for i in range(6)]
    pace = pace_from(slow)
    assert pace.factor == 1.6 and pace.confidence == "high"
    fast = [hike(make_trail(f"F{i}", distance_km=10, elevation_gain_m=0), minutes=60) for i in range(3)]
    assert pace_from(fast).factor == 0.6


def test_pace_ignores_overnights():
    trips = [hike(make_trail(f"O{i}", nights=2), minutes=2000) for i in range(4)]
    assert pace_from(trips).timed_hikes == 0


def test_experience_maxima_and_typical(intermediate):
    exp = intermediate.experience
    assert exp.basis == "history"
    assert (exp.max_distance_km, exp.max_gain_m, exp.max_high_point_m) == (12.0, 800, 2462)
    assert exp.max_distance_trail == "Big Day" and exp.max_high_point_trail == "Ha Ling"
    assert exp.typical_distance_km == 9.0 and exp.typical_gain_m == 762


def test_typical_uses_last_ten_dated_hikes():
    old = [hike(make_trail(f"Old{i}", distance_km=30, elevation_gain_m=1500), date(2020, 1, i + 1)) for i in range(5)]
    new = [hike(make_trail(f"New{i}", distance_km=6, elevation_gain_m=300), date(2026, 1, i + 1)) for i in range(10)]
    exp = profile_with(*old, *new).experience
    assert exp.typical_distance_km == 6.0 and exp.max_distance_km == 30.0


def test_overnights_count_per_day():
    trip = make_trail("Trip", distance_km=45.0, elevation_gain_m=1500, nights=2)
    exp = profile_with(hike(trip), hike(MID)).experience
    assert exp.max_distance_km == 15.0 and exp.max_gain_m == 500
    assert exp.overnight_count == 1 and exp.max_nights == 2


def test_stated_baseline_under_two_hikes():
    exp = profile_with(hike(BIG), experience_level="seasoned").experience
    assert exp.basis == "stated"
    assert (exp.max_distance_km, exp.max_gain_m) == STATED_BASELINES["seasoned"]


def test_history_off_ignores_hikes_saved_and_gear(intermediate):
    hikes = list(intermediate.hikes)
    off = build_profile(hikes, StatedPreferences(experience_level="new", use_history=False),
                        saved_trail_ids=[BIG.id], gear_categories=["tents"])
    assert off.experience.basis == "stated" and off.hiked_trail_ids == frozenset()
    assert off.saved_trail_ids == frozenset() and off.gear_categories == frozenset()
    assert off.pace.factor == 1.0


def test_winter_experience_from_dated_winter_hikes():
    route = make_trail("Snowy", winter_activities=("snowshoe",))
    p = profile_with(hike(route, date(2026, 1, 10)), hike(MID, date(2026, 2, 1)), hike(BIG, date(2026, 7, 1)))
    assert (p.winter.winter_hikes, p.winter.winter_route_hikes) == (2, 1)


# ---- scoring weights ------------------------------------------------------

def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100.0
    assert WEIGHTS["fit"] == max(WEIGHTS.values())


@pytest.mark.parametrize("band, ratio, expected", [
    ("similar", 0.9, 1.0), ("similar", 0.7, 1.0), ("similar", 1.1, 1.0),
    ("similar", 0.5, 0.5), ("similar", 1.3, 0.5), ("similar", 1.6, 0.0),
    ("easier", 0.5, 1.0), ("easier", 0.85, 0.75), ("easier", 0.1, 0.6),
    ("push", 1.2, 1.0), ("push", 1.0, 0.75), ("push", 0.7, 0.0),
])
def test_band_scores(band, ratio, expected):
    assert rec._band_score(ratio, band) == pytest.approx(expected)


def test_total_is_weighted_sum():
    parts = {name: 1.0 for name in WEIGHTS}
    assert rec.total(parts) == 100.0
    parts["fit"] = 0.5
    assert rec.total(parts) == pytest.approx(100 - 22.5)


def test_fit_drives_ranking(intermediate):
    close = make_trail("Close", distance_km=8.5, elevation_gain_m=650)  # ~0.9 of typical
    far = make_trail("Far", distance_km=4.0, elevation_gain_m=200)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER), [far, close])
    assert [r.trail.name for r in result.results] == ["Close", "Far"]


# ---- recommend filters ----------------------------------------------------

def test_never_above_130_percent_of_max(intermediate):
    over_km = make_trail("Too Long", distance_km=15.7, elevation_gain_m=500)  # 15.7 > 12 * 1.3
    over_gain = make_trail("Too Steep", distance_km=8, elevation_gain_m=1050)  # 1050 > 1040
    edge = make_trail("Edge", distance_km=15.6, elevation_gain_m=1040)
    for difficulty in ("easier", "similar", "push"):
        names = {r.trail.name for r in recommend(intermediate, GuideRequest(on_date=SUMMER, difficulty=difficulty),
                                                 [over_km, over_gain, edge]).results}
        assert not names & {"Too Long", "Too Steep"}


def test_push_targets_above_max(intermediate):
    step = make_trail("Step Up", distance_km=14.0, elevation_gain_m=950)
    same = make_trail("Same", distance_km=9.0, elevation_gain_m=600)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, difficulty="push"), [same, step])
    assert result.results[0].trail.name == "Step Up"
    assert "A step up" in result.results[0].reasons[0]
    assert "17% farther" in result.results[0].reasons[0]


def test_easier_never_above_typical(intermediate):
    harder = make_trail("Harder", distance_km=10.0, elevation_gain_m=500)
    easy = make_trail("Easy", distance_km=5.0, elevation_gain_m=250)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, difficulty="easier"), [harder, easy])
    assert [r.trail.name for r in result.results] == ["Easy"]


def test_hiked_excluded_unless_asked(intermediate):
    names = lambda req: {r.trail.name for r in recommend(intermediate, req, [HA_LING, BIG, MID]).results}  # noqa: E731
    assert names(GuideRequest(on_date=SUMMER)) == set()
    assert names(GuideRequest(on_date=SUMMER, include_hiked=True)) == {"Ha Ling", "Big Day", "Mid Day"}


def test_nothing_fits_explains_which_filter(intermediate):
    result = recommend(intermediate, GuideRequest(on_date=SUMMER), [HA_LING])
    assert result.results == [] and "Include trails you've done" in result.notes[0]


def test_dog_never_banned_unknown_noted_leash_first(intermediate):
    leash = make_trail("Leash", dog_policy="on_leash", distance_km=5, popularity_rank=90)
    banned = make_trail("No Dogs", dog_policy="not_allowed", distance_km=8)
    unknown = make_trail("Unknown", dog_policy="unknown", distance_km=8, popularity_rank=1)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, dog=True), [leash, banned, unknown])
    assert [r.trail.name for r in result.results] == ["Leash", "Unknown"]
    assert result.results[0].dog_note.startswith("Dogs allowed on a leash")
    assert result.results[1].dog_note.startswith("Check dog rules")
    no_dog = recommend(intermediate, GuideRequest(on_date=SUMMER), [leash, banned, unknown])
    assert len(no_dog.results) == 3 and all(r.dog_note is None for r in no_dog.results)


def test_winter_needs_official_route_and_avoid_means_simple_or_none(intermediate):
    none = make_trail("Flat Snowshoe", winter_activities=("snowshoe",), avalanche_exposure="none", distance_km=8)
    simple = make_trail("Simple One", winter_activities=("snowshoe",), avalanche_exposure="simple", distance_km=8)
    unknown = make_trail("Unrated", winter_activities=("snowshoe",), avalanche_exposure="unknown", distance_km=8)
    summer_only = make_trail("Summer Only", distance_km=8, avalanche_exposure="none")
    pool = [none, simple, unknown, summer_only]
    default = recommend(intermediate, GuideRequest(on_date=WINTER, activity="snowshoe"), pool)
    assert {r.trail.name for r in default.results} == {"Flat Snowshoe", "Simple One"}
    assert all("avalanche.ca" in r.reasons[1] for r in default.results)
    # Turning avoid off adds unrated trails, but an off-season trail never.
    loose = recommend(intermediate, GuideRequest(on_date=WINTER, activity="snowshoe", avoid_avalanche=False), pool)
    assert {r.trail.name for r in loose.results} == {"Flat Snowshoe", "Simple One", "Unrated"}


def test_serious_avalanche_terrain_never_recommended_even_with_avoid_off(intermediate):
    winter_profile = profile_with(*intermediate.hikes)
    pool = [make_trail(f"{x} One", winter_activities=("snowshoe",), avalanche_exposure=x, distance_km=8)
            for x in ("simple", "challenging", "complex")]
    for avoid in (True, False):
        request = GuideRequest(on_date=WINTER, activity="snowshoe", avoid_avalanche=avoid)
        assert [r.trail.name for r in recommend(winter_profile, request, pool).results] == ["simple One"]
    # Same in May for a summer hike.
    summer_pool = [make_trail("Complex Summer", avalanche_exposure="complex", distance_km=8)]
    assert recommend(winter_profile, GuideRequest(on_date=MAY), summer_pool).results == []
    assert recommend(winter_profile, GuideRequest(on_date=SUMMER), summer_pool).results


def test_day_hikes_unless_style_includes_overnights(intermediate):
    trip = make_trail("Trip", nights=1, distance_km=18, elevation_gain_m=900)
    assert recommend(intermediate, GuideRequest(on_date=SUMMER), [trip]).results == []
    both = build_profile(list(intermediate.hikes), StatedPreferences(hiking_style="both"))
    assert recommend(both, GuideRequest(on_date=SUMMER), [trip]).results


def test_nights_capped_by_longest_trip(intermediate):
    long_trip = make_trail("Week", nights=3, distance_km=36, elevation_gain_m=1500)  # 9 km/day
    short_trip = make_trail("Two", nights=2, distance_km=27, elevation_gain_m=1200)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, length="overnight"), [long_trip, short_trip])
    assert [r.trail.name for r in result.results] == ["Two"]  # no overnights yet: up to 2 nights


def test_gentle_profile_never_gets_a_not_yet_grade():
    newbie = profile_with(experience_level="new")
    hard = make_trail("Hard Short", terrain="difficult", distance_km=4, elevation_gain_m=300)
    assert blocker(newbie, hard, SUMMER) == "terrain"
    assert recommend(newbie, GuideRequest(on_date=SUMMER), [hard]).results == []


def test_winter_hike_means_winter_hike_activity(intermediate):
    walk = make_trail("Winter Walk", winter_activities=("winter_hike",), avalanche_exposure="none", distance_km=8)
    shoe = make_trail("Shoe Only", winter_activities=("snowshoe",), avalanche_exposure="none", distance_km=8)
    result = recommend(intermediate, GuideRequest(on_date=WINTER, activity="hike"), [walk, shoe])
    assert [r.trail.name for r in result.results] == ["Winter Walk"]


def test_winter_activity_off_season_explains(intermediate):
    shoe = make_trail("Shoe", winter_activities=("snowshoe",), distance_km=8)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, activity="snowshoe"), [shoe])
    assert result.results == [] and "Dec-Mar" in result.notes[0]


def test_winter_only_trails_hidden_in_summer(intermediate):
    winter_only = make_trail("Ski Loop", tags=("winter_only",), distance_km=8)
    assert recommend(intermediate, GuideRequest(on_date=SUMMER), [winter_only]).results == []


def test_shoulder_season_keeps_alpine_to_no_avalanche_terrain_by_default(intermediate):
    alpine = make_trail("Alpine", climate_zone="alpine", distance_km=9, elevation_gain_m=600)
    valley = make_trail("Valley", climate_zone="temperate", distance_km=9, elevation_gain_m=600)
    default = recommend(intermediate, GuideRequest(on_date=MAY), [alpine, valley])
    assert [r.trail.name for r in default.results] == ["Valley"]
    # Opting out brings alpine back, marked down with a snow note.
    loose = recommend(intermediate, GuideRequest(on_date=MAY, avoid_avalanche=False), [alpine, valley])
    assert [r.trail.name for r in loose.results] == ["Valley", "Alpine"]
    assert "snow can linger" in loose.results[1].reasons[1]
    # Summer: no avalanche filter.
    assert len(recommend(intermediate, GuideRequest(on_date=SUMMER), [alpine, valley]).results) == 2


def test_length_uses_their_pace(intermediate):
    # 9 km / 500 m: Naismith 2.63 h; at their pace (>1) it's past "short".
    trail = make_trail("Middling", distance_km=9.0, elevation_gain_m=500)
    assert intermediate.pace.factor > 1.15
    assert recommend(intermediate, GuideRequest(on_date=SUMMER, length="short"), [trail]).results == []
    assert recommend(intermediate, GuideRequest(on_date=SUMMER, length="half_day"), [trail]).results


def test_overnight_length(intermediate):
    trip = make_trail("Trip", nights=1, distance_km=18, elevation_gain_m=900)
    day = make_trail("Day", distance_km=9)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER, length="overnight"), [trip, day])
    assert [r.trail.name for r in result.results] == ["Trip"]


def test_province_and_region_filters(intermediate):
    banff = make_trail("Banff One", park_name="Banff National Park", distance_km=8)
    bc = make_trail("BC One", province_code="BC", distance_km=8)
    by_province = recommend(intermediate, GuideRequest(on_date=SUMMER, province="BC"), [banff, bc])
    assert [r.trail.name for r in by_province.results] == ["BC One"]
    by_region = recommend(intermediate, GuideRequest(on_date=SUMMER, regions=("banff",)), [banff, bc])
    assert [r.trail.name for r in by_region.results] == ["Banff One"]


def test_at_most_two_per_park(intermediate):
    park = [make_trail(f"P{i}", park_name="Banff National Park", distance_km=8 + i * 0.1) for i in range(4)]
    other = make_trail("Elsewhere", distance_km=5)
    result = recommend(intermediate, GuideRequest(on_date=SUMMER), [*park, other])
    assert sum(r.trail.park_name == "Banff National Park" for r in result.results) == 2


def test_show_me_more_excludes_shown(intermediate):
    pool = [make_trail(f"T{i}", distance_km=7 + i) for i in range(5)]
    first = recommend(intermediate, GuideRequest(on_date=SUMMER), pool)
    shown = frozenset(r.trail.id for r in first.results)
    more = recommend(intermediate, GuideRequest(on_date=SUMMER, exclude_ids=shown), pool)
    assert not shown & {r.trail.id for r in more.results} and more.results


def test_like_reason_uses_real_numbers():
    # Their closest hike is Ha Ling (7.2 km, 762 m); this is 300 m less gain.
    p = profile_with(hike(HA_LING), hike(make_trail("Long", distance_km=20, elevation_gain_m=1200)))
    lighter = make_trail("Lighter", distance_km=7.4, elevation_gain_m=460)
    reason = recommend(p, GuideRequest(on_date=SUMMER), [lighter]).results[0].reasons[0]
    assert reason == "Like Ha Ling (which you did) but 300 m less gain."


def test_saved_and_favourite_reasons():
    p = build_profile([hike(BIG), hike(MID)], StatedPreferences(favourite_regions=("banff",)),
                      saved_trail_ids=[])
    trail = make_trail("Fav", park_name="Banff National Park", distance_km=9, elevation_gain_m=600)
    reasons = recommend(p, GuideRequest(on_date=SUMMER), [trail]).results[0].reasons
    assert reasons[1] == "In Banff National Park, one of your favourite places."


def test_no_history_reason_states_numbers():
    p = profile_with(experience_level="new")
    trail = make_trail("Starter", distance_km=5.6, elevation_gain_m=280)
    reason = recommend(p, GuideRequest(on_date=SUMMER), [trail]).results[0].reasons[0]
    assert reason == "5.6 km and 280 m of climbing: right around your usual hike."


def test_deterministic(intermediate, catalogue):
    request = GuideRequest(on_date=SUMMER, difficulty="push")
    first = [r.trail.id for r in recommend(intermediate, request, catalogue).results]
    assert first == [r.trail.id for r in recommend(intermediate, request, list(reversed(catalogue))).results]


# ---- readiness ------------------------------------------------------------

def test_ready_when_within_max(intermediate):
    result = readiness(intermediate, make_trail("Fine", distance_km=10, elevation_gain_m=700), SUMMER)
    assert result.verdict == READY and not result.build_up
    assert any(r.text.startswith("Within your range: 10 km here") for r in result.reasons)


def test_stretch_between_100_and_130(intermediate):
    trail = make_trail("Bit More", distance_km=14, elevation_gain_m=700)
    result = readiness(intermediate, trail, SUMMER, [make_trail("Builder", distance_km=12.5, elevation_gain_m=650)])
    assert result.verdict == STRETCH
    assert [t.name for t in result.build_up] == ["Builder"]


def test_not_yet_above_130(intermediate):
    result = readiness(intermediate, make_trail("Huge", distance_km=20, elevation_gain_m=700), SUMMER)
    assert result.verdict == NOT_YET
    assert any("67% more than your biggest day" in r.text for r in result.reasons)


@pytest.mark.parametrize("exposure", ["challenging", "complex"])
def test_not_yet_on_serious_avalanche_terrain(intermediate, exposure):
    trail = make_trail("Serious", winter_activities=("snowshoe",), avalanche_exposure=exposure, distance_km=8)
    result = readiness(intermediate, trail, WINTER)
    assert result.verdict == NOT_YET and result.avalanche_link == "https://avalanche.ca"


def test_unknown_avalanche_in_winter_is_at_least_stretch(intermediate):
    trail = make_trail("Unrated", winter_activities=("snowshoe",), avalanche_exposure="unknown", distance_km=8)
    winter_profile = profile_with(*intermediate.hikes, hike(make_trail("W", winter_activities=("snowshoe",)),
                                                            date(2026, 1, 5)))
    result = readiness(winter_profile, trail, WINTER)
    assert result.verdict == STRETCH
    assert any("avalanche.ca" in r.text for r in result.reasons if r.kind == "avalanche")


def test_summer_trail_in_winter_is_not_yet(intermediate):
    result = readiness(intermediate, make_trail("Summer", distance_km=8), WINTER)
    assert result.verdict == NOT_YET


def test_high_point_and_first_overnight_are_stretch(intermediate):
    high = readiness(intermediate, make_trail("High", distance_km=8, max_elevation_m=3100), SUMMER)
    assert high.verdict == STRETCH and any(r.kind == "high_point" for r in high.reasons)
    trip = readiness(intermediate, make_trail("Trip", distance_km=20, elevation_gain_m=900, nights=1), SUMMER)
    assert trip.verdict == STRETCH and any(r.kind == "overnight" for r in trip.reasons)


def test_gentle_answer_with_little_history():
    p = profile_with(hike(MID), experience_level="new")
    result = readiness(p, make_trail("Hard", terrain="difficult", distance_km=20, elevation_gain_m=1500), SUMMER)
    assert result.gentle and result.verdict == NOT_YET
    assert any("Log a few past hikes" in r.text for r in result.reasons)
    easy = readiness(p, make_trail("Easy", terrain="easy", distance_km=4), SUMMER)
    assert easy.verdict == READY


def test_estimate_uses_pace(intermediate):
    trail = make_trail("Timed", distance_km=10, elevation_gain_m=600)
    result = readiness(intermediate, trail, SUMMER)
    assert result.est_hours == pytest.approx(3.0 * intermediate.pace.factor, abs=0.01)
    assert any("at your pace" in r.text for r in result.reasons if r.kind == "duration")


def test_never_says_safe(intermediate, catalogue):
    for day in (SUMMER, WINTER, MAY):
        for trail in catalogue:
            for reason in readiness(intermediate, trail, day).reasons:
                assert "safe" not in reason.text.lower()
