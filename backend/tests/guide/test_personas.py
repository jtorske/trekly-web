"""Run every persona in personas.py against the real catalogue.

The invariants (every persona, every answer):
- every recommended trail exists in the database and is live
- nothing above 130% of the persona's biggest day (per-day distance and gain)
- winter + avoid avalanche terrain: an official Simple or none rating only,
  and every winter result links avalanche.ca
- dog: never a banned trail; unknown rules carry "Check dog rules"
- already-hiked trails excluded unless include_hiked
- "Show me more" never repeats a trail
- never a trail its own "Am I ready?" calls Not yet
- readiness verdicts follow the rules (rule_check below, written from the
  spec, independent of app/guide/readiness.py)
Then each persona's own expected properties, and its readiness targets.

Set GUIDE_EVAL_REPORT=path to write a markdown table of the answers.
"""

import os
from datetime import date

import pytest

from app.guide.estimate import AVALANCHE_SEASON_MONTHS, WINTER_MONTHS, scenery_of
from app.guide.profile import MIN_HISTORY_HIKES, HikeRecord, StatedPreferences, build_profile
from app.guide.readiness import ORDER, readiness
from app.guide.recommend import CEILING, GuideRequest, recommend
from app.models.trail import Trail
from tests.guide.personas import PERSONAS, Persona

REPORT: list[str] = []


def profile_for(persona: Persona, by_slug):
    hikes = [HikeRecord(by_slug[slug], day, minutes) for slug, day, minutes in persona.hikes]
    return build_profile(
        hikes, StatedPreferences(**persona.prefs), home_province=persona.home_province,
        saved_trail_ids=[by_slug[s].id for s in persona.saved],
    )


def rule_check(profile, trail, day: date, verdict: str) -> None:
    """The readiness rules, straight from the spec."""
    exp = profile.experience
    winter = day.month in WINTER_MONTHS
    avalanche_season = day.month in AVALANCHE_SEASON_MONTHS
    gentle = exp.hike_count < MIN_HISTORY_HIKES or exp.basis != "history"
    not_yet, stretch = [], []
    if not gentle and not (winter and trail.winter_route_ends):
        for value, best in ((trail.per_day_km, exp.max_distance_km), (trail.per_day_gain, exp.max_gain_m)):
            if value is None:
                continue
            if value > best * CEILING:
                not_yet.append("over 130%")
            elif value > best:
                stretch.append("100-130%")
    if avalanche_season and trail.avalanche_exposure in ("challenging", "complex"):
        not_yet.append("ATES challenging/complex")
    if winter and not trail.winter_activities:
        not_yet.append("not a winter route")
    if winter and trail.avalanche_exposure == "unknown":
        stretch.append("unknown ATES in winter")

    if not_yet:
        assert verdict == "not_yet", (trail.name, day, not_yet)
    elif not gentle:
        assert verdict != "not_yet", (trail.name, day, verdict)
    if stretch:
        assert ORDER[verdict] >= ORDER["stretch"], (trail.name, day, stretch)


def check_expectations(persona, profile, request, result):
    expect = persona.expect
    names = [r.trail.name for r in result.results]
    assert len(result.results) >= expect.get("min_results", 0), (persona.name, names, result.notes)
    if "max_results" in expect:
        assert len(result.results) <= expect["max_results"], (persona.name, names)
    if "province" in expect:
        assert all(r.trail.province_code == expect["province"] for r in result.results)
    if "regions_park" in expect:
        assert all(r.trail.park_name == expect["regions_park"] for r in result.results)
    if "terrain_in" in expect:
        assert all(r.trail.terrain in expect["terrain_in"] for r in result.results)
    if "activity" in expect:
        assert all(expect["activity"] in r.trail.winter_activities for r in result.results)
    if "notes_contain" in expect:
        assert any(expect["notes_contain"] in note for note in result.notes), result.notes
    if "basis" in expect:
        assert profile.experience.basis == expect["basis"]
    if "pace_between" in expect:
        low, high = expect["pace_between"]
        assert low <= profile.pace.factor <= high, profile.pace
    if "ates_in" in expect:
        assert all(r.trail.avalanche_exposure in expect["ates_in"] for r in result.results)
    if "scenery" in expect:
        assert any(expect["scenery"] in scenery_of(r.trail) for r in result.results)


@pytest.mark.parametrize("persona", PERSONAS, ids=[p.name for p in PERSONAS])
def test_persona(persona, catalogue, by_slug, catalogue_session):
    profile = profile_for(persona, by_slug)
    request = GuideRequest(**persona.request)
    result = recommend(profile, request, catalogue)
    exp = profile.experience
    live_ids = {t.id for t in catalogue_session.query(Trail.id).filter(Trail.retired_at.is_(None))}

    for r in result.results:
        trail = r.trail
        assert trail.id in live_ids, f"{trail.name} isn't in the database"
        if trail.per_day_km is not None:
            assert trail.per_day_km <= exp.max_distance_km * CEILING + 1e-9, trail.name
        if trail.per_day_gain is not None:
            assert trail.per_day_gain <= exp.max_gain_m * CEILING + 1e-9, trail.name
        if request.winter and request.avoids_avalanche:
            assert trail.avalanche_exposure in ("none", "simple"), trail.name
        if request.avoids_avalanche and trail.climate_zone == "alpine" and request.snow_season:
            assert trail.avalanche_exposure in ("none", "simple"), trail.name
        if request.winter:
            assert any("https://avalanche.ca" in reason for reason in r.reasons), trail.name
        if request.dog:
            assert trail.dog_policy != "not_allowed", trail.name
            assert r.dog_note and ("Check dog rules" in r.dog_note) == (trail.dog_policy == "unknown")
        else:
            assert r.dog_note is None
        if not request.include_hiked:
            assert trail.id not in profile.hiked_trail_ids, trail.name
        assert 1 <= len(r.reasons) <= 2 and all(r.reasons)
        verdict = readiness(profile, trail, request.on_date, catalogue).verdict
        rule_check(profile, trail, request.on_date, verdict)
        assert verdict != "not_yet", f"{persona.name}: recommended {trail.name}, which readiness calls Not yet"

    if not result.results:
        assert result.notes, f"{persona.name}: an empty answer must say what to loosen"

    shown = frozenset(r.trail.id for r in result.results)
    more = recommend(profile, GuideRequest(**{**persona.request, "exclude_ids": shown}), catalogue)
    assert not shown & {r.trail.id for r in more.results}

    check_expectations(persona, profile, request, result)

    for slug, day, expected in persona.readiness:
        trail = by_slug[slug]
        answer = readiness(profile, trail, day, catalogue)
        rule_check(profile, trail, day, answer.verdict)
        if expected is not None:
            assert answer.verdict == expected, (persona.name, slug, answer.verdict, [r.text for r in answer.reasons])
        for build in answer.build_up:
            assert build.id in live_ids and build.id not in profile.hiked_trail_ids
            if day.month in WINTER_MONTHS:
                assert build.avalanche_exposure in ("none", "simple")
        REPORT.append(f"| {persona.name} | readiness: {slug} ({day}) | {answer.label} | "
                      f"{'; '.join(r.text for r in answer.reasons if r.level != 'info')[:160]} |")

    picks = ", ".join(r.trail.name for r in result.results) or f"none ({result.notes[0] if result.notes else ''})"
    REPORT.append(f"| {persona.name} | {request.difficulty}, {request.length or 'any'}, {request.on_date} | "
                  f"{len(result.results)} | {picks} |")


def test_persona_count():
    assert len(PERSONAS) >= 30


@pytest.fixture(scope="session", autouse=True)
def _write_report():
    yield
    path = os.environ.get("GUIDE_EVAL_REPORT")
    if path and REPORT:
        with open(path, "w", encoding="utf-8") as f:
            f.write("| Persona | Request | Results | Picks / reasons |\n|---|---|---|---|\n")
            f.write("\n".join(REPORT) + "\n")
