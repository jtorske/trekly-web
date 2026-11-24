"""Rules shared by recommend.py and readiness.py, so the two never disagree.

The main one: Trekly Guide never recommends a trail its own "Am I ready?"
would call Not yet (blocker() below). Readiness turns the same rules into
worded reasons.
"""

from __future__ import annotations

from datetime import date

from app.guide.estimate import TrailFacts, in_avalanche_season, is_winter
from app.guide.profile import MIN_HISTORY_HIKES, HikerProfile

READY, STRETCH, NOT_YET = "ready", "stretch", "not_yet"

# Never more than this share of the biggest day they've done (distance or gain).
CEILING = 1.3

# Trail alone (little or no history): terrain grade -> verdict, per stated level.
GENTLE = {
    "new": {"easy": READY, "moderate": STRETCH, "difficult": NOT_YET, "extreme": NOT_YET},
    "few_seasons": {"easy": READY, "moderate": READY, "difficult": STRETCH, "extreme": NOT_YET},
    "seasoned": {"easy": READY, "moderate": READY, "difficult": READY, "extreme": STRETCH},
    None: {"easy": READY, "moderate": STRETCH, "difficult": STRETCH, "extreme": NOT_YET},
}

SERIOUS_AVALANCHE = ("challenging", "complex")

# Overnights: nights more than their longest trip that's still a sensible next step.
OVERNIGHT_JUMP = 2
# Longest trip to suggest without overnight history, per stated level.
STATED_MAX_NIGHTS = {"new": 1, "few_seasons": 2, "seasoned": 4, None: 2}


def is_gentle(profile: HikerProfile) -> bool:
    """Too little history to compare against: judge the trail alone."""
    return profile.experience.hike_count < MIN_HISTORY_HIKES or not profile.has_history


def gentle_verdict(profile: HikerProfile, trail: TrailFacts) -> str:
    return GENTLE.get(profile.preferences.experience_level, GENTLE[None])[trail.terrain]


def above_ceiling(profile: HikerProfile, trail: TrailFacts) -> bool:
    """Per-day distance or gain above CEILING x their biggest day."""
    exp = profile.experience
    km, gain = trail.per_day_km, trail.per_day_gain
    return (km is not None and km > exp.max_distance_km * CEILING) or (
        gain is not None and gain > exp.max_gain_m * CEILING
    )


def max_nights(profile: HikerProfile) -> int:
    exp = profile.experience
    if exp.overnight_count:
        return exp.max_nights + OVERNIGHT_JUMP
    return STATED_MAX_NIGHTS.get(profile.preferences.experience_level, STATED_MAX_NIGHTS[None])


def blocker(profile: HikerProfile, trail: TrailFacts, on_date: date) -> str | None:
    """Why "Am I ready?" would say Not yet, or None."""
    winter = is_winter(on_date)
    if winter and not trail.winter_activities:
        return "season"
    if in_avalanche_season(on_date) and trail.avalanche_exposure in SERIOUS_AVALANCHE:
        return "avalanche"
    if is_gentle(profile):
        if gentle_verdict(profile, trail) == NOT_YET:
            return "terrain"
    elif not (winter and trail.winter_route_ends) and above_ceiling(profile, trail):
        return "ceiling"
    return None
