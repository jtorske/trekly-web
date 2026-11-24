"""Trekly Guide recommendations: recommend(profile, request, trails).

Deterministic: the same profile, request and catalogue always give the same
ranking. Every number in a reason comes from the trail and profile data.

1. Hard filters, in this order (a trail failing any is never shown):
   - "Show me more" exclusions, and trails they've hiked (unless include_hiked)
   - province / favourite-park regions they picked
   - dog: never a trail whose official rule bans dogs. Trails with an official
     on-leash rule come first; trails without a rule on file stay in with a
     "Check dog rules" note (dog_note), never marked dog-friendly
   - season and activity: Dec-Mar only official winter routes for the chosen
     winter activity; the rest of the year only hiking, and no winter-only trails
   - avoid avalanche terrain (default on Dec-Mar and in the shoulder months):
     an official ATES rating of Simple or none (AVOID_KEEPS); 'unknown' is
     out. Dec-Mar it covers every trail; in Apr, May and Nov only alpine
     trails, where snow lingers. Every winter result links avalanche.ca
   - length: nights, and the estimated hours for THEIR pace (LENGTH_HOURS).
     No length picked means day hikes, unless their hiking style includes
     overnights. Never more nights than rules.max_nights (their longest trip
     + 2, or a stated-level cap without overnight history)
   - the ceiling: per-day distance and gain never above CEILING (130%) of
     the biggest day they've done, whatever the difficulty asked
   - never a trail "Am I ready?" would call Not yet (rules.blocker): serious
     avalanche terrain (Challenging/Complex) in Nov-May even with "avoid" off,
     or, with little history, a grade that's too much for their stated level
   - "easier": nothing above their typical hike
2. A score out of 100, the sum of WEIGHTS x component (each component 0-1):
   - fit: how well the per-day distance and gain match the difficulty band
     (FIT_BANDS); gain counts as much as distance when it's known
   - season: 1, or SHOULDER_ALPINE for alpine trails in Apr/May/Nov
   - preferences: scenery they like and terrain for their experience level
   - region: a favourite park 1, their home province HOME_PROVINCE_SHARE
   - saved: on their saved list
   - popularity and photo: tiebreakers
3. At most MAX_PER_PARK picks from one park.

Overnights are compared per day on trail (distance / days), the same way the
profile measures their biggest day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from app.guide.estimate import (
    AVALANCHE_CANADA_URL,
    TrailFacts,
    format_hours,
    is_shoulder,
    is_winter,
    naismith_hours,
    scenery_of,
)
from app.guide.profile import HikerProfile
from app.guide.rules import CEILING, above_ceiling, blocker, max_nights
from app.preferences import _DIFFICULTY_FIT, PARK_BY_REGION

WEIGHTS = {
    "fit": 45.0,
    "season": 15.0,
    "preferences": 15.0,
    "region": 10.0,
    "saved": 5.0,
    "popularity": 6.0,
    "photo": 4.0,
}
assert sum(WEIGHTS.values()) == 100.0

# Per band: (reference measure, full-marks range of ratio to it).
FIT_BANDS = {
    "easier": ("typical", (0.0, 0.7)),
    "similar": ("typical", (0.7, 1.1)),
    "push": ("max", (1.1, CEILING)),
}
# How far outside the full-marks range a ratio can drift before scoring 0.
FIT_FALLOFF = {"easier": 0.6, "similar": 0.4, "push": 0.4}
# An "easier" trail this small is more of a stroll than a hike.
EASIER_FLOOR = (0.25, 0.6)  # below 25% of typical scores 0.6
# Fit when the winter route is only part of the trail and its length isn't known.
UNKNOWN_WINTER_FIT = 0.5
# Gain unknown: fit from distance alone, a little discounted.
UNKNOWN_GAIN_DISCOUNT = 0.85

SHOULDER_ALPINE = 0.3
HOME_PROVINCE_SHARE = 0.6
POPULARITY_SCALE = 25  # rank 1 scores 1, rank 26 scores 0.5
MAX_PER_PARK = 2

# Estimated hours on trail (per day, at their pace) for each length.
LENGTH_HOURS = {
    "short": (0.0, 3.0),
    "half_day": (2.5, 5.5),
    "full_day": (5.0, 11.0),
}

# What "avoid avalanche terrain" keeps: an official rating of none or Simple.
# 'unknown' never; Challenging and Complex never in any case (rules.blocker).
AVOID_KEEPS = ("none", "simple")

DOG_NOTES = {
    "on_leash": "Dogs allowed on a leash (official park rule).",
    "unknown": "Check dog rules: Trekly doesn't have this park's rule yet.",
}

ACTIVITY_LABELS = {
    "hike": "hike",
    "winter_hike": "winter hike",
    "snowshoe": "snowshoe",
    "xc_ski": "cross-country ski",
}
AVALANCHE_LABELS = {
    "none": "no avalanche terrain",
    "simple": "Simple",
    "challenging": "Challenging",
    "complex": "Complex",
    "unknown": "not rated",
}


@dataclass(frozen=True)
class GuideRequest:
    on_date: date
    difficulty: str = "similar"  # easier | similar | push
    length: str | None = None  # short | half_day | full_day | overnight
    province: str | None = None
    regions: tuple[str, ...] = ()  # app/preferences.py REGION_SLUGS
    dog: bool = False
    activity: str = "hike"  # hike | winter_hike | snowshoe | xc_ski
    # None: on in winter and the shoulder months, off in summer and fall.
    avoid_avalanche: bool | None = None
    include_hiked: bool = False
    exclude_ids: frozenset = frozenset()
    limit: int = 3

    @property
    def winter(self) -> bool:
        return is_winter(self.on_date)

    @property
    def snow_season(self) -> bool:
        return self.winter or is_shoulder(self.on_date)

    @property
    def avoids_avalanche(self) -> bool:
        return self.snow_season if self.avoid_avalanche is None else self.avoid_avalanche

    def avalanche_filter_applies(self, trail: TrailFacts) -> bool:
        """Dec-Mar every trail; in Apr, May and Nov only alpine ones."""
        return self.avoids_avalanche and (self.winter or trail.climate_zone == "alpine")

    @property
    def wanted_activity(self) -> str:
        """In winter a plain "hike" means a winter hike."""
        return "winter_hike" if self.winter and self.activity == "hike" else self.activity


@dataclass(frozen=True)
class Recommendation:
    trail: TrailFacts
    score: float
    components: dict[str, float]
    reasons: tuple[str, ...]
    est_hours: float | None
    # Set when they're bringing a dog (DOG_NOTES).
    dog_note: str | None
    # Per-day ratios to the band's reference (None when unknown).
    distance_ratio: float | None
    gain_ratio: float | None


@dataclass(frozen=True)
class RecommendResult:
    results: list[Recommendation]
    # Trails that passed every filter (before the limit).
    matching: int
    # Why nothing (or little) fit and what to loosen; plain sentences.
    notes: list[str] = field(default_factory=list)


def est_hours(profile: HikerProfile, trail: TrailFacts) -> float | None:
    """Hours per day on trail at their pace."""
    base = naismith_hours(trail.per_day_km, trail.per_day_gain)
    return None if base is None else round(base * profile.pace.factor, 2)


def _band_score(ratio: float, band: str) -> float:
    low, high = FIT_BANDS[band][1]
    falloff = FIT_FALLOFF[band]
    if band == "easier":
        if ratio < EASIER_FLOOR[0]:
            return EASIER_FLOOR[1]
        if ratio <= high:
            return 1.0
        # Hard-filtered above 1.0, so this runs 0.7 -> 1.0.
        return max(0.0, 1.0 - (ratio - high) / falloff)
    if low <= ratio <= high:
        return 1.0
    if ratio < low:
        return max(0.0, 1.0 - (low - ratio) / falloff)
    return max(0.0, 1.0 - (ratio - high) / falloff)


def ratios(profile: HikerProfile, trail: TrailFacts, band: str) -> tuple[float | None, float | None]:
    exp = profile.experience
    ref_km, ref_gain = (
        (exp.typical_distance_km, exp.typical_gain_m) if FIT_BANDS[band][0] == "typical"
        else (exp.max_distance_km, exp.max_gain_m)
    )
    km, gain = trail.per_day_km, trail.per_day_gain
    distance_ratio = km / ref_km if km is not None and ref_km else None
    gain_ratio = gain / ref_gain if gain is not None and ref_gain else None
    return distance_ratio, gain_ratio


def fit_score(profile: HikerProfile, trail: TrailFacts, band: str, winter: bool) -> float:
    if winter and not trail.winter_measures_known():
        return UNKNOWN_WINTER_FIT
    distance_ratio, gain_ratio = ratios(profile, trail, band)
    if distance_ratio is None:
        return 0.0
    if gain_ratio is None:
        return _band_score(distance_ratio, band) * UNKNOWN_GAIN_DISCOUNT
    return (_band_score(distance_ratio, band) + _band_score(gain_ratio, band)) / 2


def _favourite_parks(profile: HikerProfile) -> set[str]:
    return {PARK_BY_REGION[s] for s in profile.preferences.favourite_regions if s in PARK_BY_REGION}


def components(profile: HikerProfile, trail: TrailFacts, request: GuideRequest) -> dict[str, float]:
    prefs = profile.preferences
    season = 1.0
    if is_shoulder(request.on_date) and trail.climate_zone == "alpine":
        season = SHOULDER_ALPINE

    liked = set(prefs.scenery)
    scenery = 1.0 if liked & scenery_of(trail) else (0.5 if not liked else 0.0)
    terrain_table = _DIFFICULTY_FIT.get(prefs.experience_level)
    # _DIFFICULTY_FIT runs -6..3; map to 0..1.
    terrain = (terrain_table.get(trail.terrain, 0.0) + 6) / 9 if terrain_table else 0.5
    preferences = (scenery + terrain) / 2

    if trail.park_name and trail.park_name in _favourite_parks(profile):
        region = 1.0
    elif profile.home_province and trail.province_code == profile.home_province:
        region = HOME_PROVINCE_SHARE
    else:
        region = 0.0

    rank = trail.popularity_rank or 1000
    return {
        "fit": fit_score(profile, trail, request.difficulty, request.winter),
        "season": season,
        "preferences": preferences,
        "region": region,
        "saved": 1.0 if trail.id in profile.saved_trail_ids else 0.0,
        "popularity": 1.0 / (1.0 + (rank - 1) / POPULARITY_SCALE),
        "photo": 1.0 if trail.has_photo else 0.0,
    }


def total(parts: dict[str, float]) -> float:
    return round(sum(WEIGHTS[name] * value for name, value in parts.items()), 2)


# ---- filters --------------------------------------------------------------

def _in_place(request: GuideRequest, trail: TrailFacts) -> bool:
    if request.province and trail.province_code != request.province:
        return False
    if request.regions:
        parks = {PARK_BY_REGION[s] for s in request.regions if s in PARK_BY_REGION}
        if trail.park_name not in parks:
            return False
    return True


def _season_ok(request: GuideRequest, trail: TrailFacts) -> bool:
    if request.winter:
        return request.wanted_activity in trail.winter_activities
    return request.activity == "hike" and "winter_only" not in trail.tags


def _length_ok(profile: HikerProfile, request: GuideRequest, trail: TrailFacts) -> bool:
    if trail.nights > max_nights(profile):
        return False
    if request.length is None:
        return trail.nights == 0 or profile.preferences.hiking_style in ("overnight", "both")
    if request.length == "overnight":
        return trail.nights >= 1
    if trail.nights:
        return False
    if request.winter and not trail.winter_measures_known():
        return request.length != "full_day"
    hours = est_hours(profile, trail)
    if hours is None:
        return False
    low, high = LENGTH_HOURS[request.length]
    return low <= hours <= high


def _difficulty_ok(profile: HikerProfile, request: GuideRequest, trail: TrailFacts) -> bool:
    if request.difficulty == "push" and request.winter and not trail.winter_measures_known():
        return False  # can't show it's a step up
    if request.difficulty != "easier":
        return True
    distance_ratio, gain_ratio = ratios(profile, trail, "easier")
    return (distance_ratio is None or distance_ratio <= 1.0) and (gain_ratio is None or gain_ratio <= 1.0)


def _filters(profile: HikerProfile, request: GuideRequest):
    """(name, predicate, what to suggest when it removes everything)."""
    activity = ACTIVITY_LABELS.get(request.wanted_activity, request.wanted_activity)
    return [
        ("shown", lambda t: t.id not in request.exclude_ids, "That's every match so far."),
        ("hiked", lambda t: request.include_hiked or t.id not in profile.hiked_trail_ids,
         "You've hiked every trail that fits. Include trails you've done?"),
        ("place", lambda t: _in_place(request, t), "Try a wider area or another province."),
        ("measured", lambda t: t.distance_km is not None or (request.winter and not t.winter_measures_known()),
         "Trekly doesn't have distances for the trails here yet."),
        ("dog", lambda t: not request.dog or t.dog_policy != "not_allowed",
         "Dogs aren't allowed on the trails that fit here. Try another area."),
        ("season", lambda t: _season_ok(request, t),
         f"No official {activity} routes fit here. Try another activity or area."
         if request.winter else
         "Winter activities only run Dec-Mar. Pick hiking, or a winter date."),
        ("avalanche", lambda t: not request.avalanche_filter_applies(t) or t.avalanche_exposure in AVOID_KEEPS,
         "No trails here have an official Simple or no-avalanche-terrain rating. Turning off "
         "\"avoid avalanche terrain\" adds trails that aren't rated yet; check avalanche.ca before you go."),
        ("length", lambda t: _length_ok(profile, request, t), "Try a different trip length."),
        ("ceiling", lambda t: not above_ceiling(profile, t),
         "Everything that fits is a big jump from what you've done. Log a longer hike, or try a different length."),
        ("ready", lambda t: blocker(profile, t, request.on_date) is None,
         "What fits is a big step for now (serious avalanche terrain, or a hard grade for your experience). "
         "Try \"easier\" or another area."),
        ("difficulty", lambda t: _difficulty_ok(profile, request, t), "Try \"similar\" instead of \"easier\"."),
    ]


# ---- reasons --------------------------------------------------------------

def _km(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + " km"


def _closest_hike(profile: HikerProfile, trail: TrailFacts):
    """Their hike most like this trail, by per-day distance and gain."""
    exp = profile.experience
    best, best_gap = None, None
    for hike in profile.hikes:
        other = hike.trail
        if other.id == trail.id or other.per_day_km is None or trail.per_day_km is None:
            continue
        gap = abs(other.per_day_km - trail.per_day_km) / max(exp.max_distance_km, 1)
        if other.per_day_gain is not None and trail.per_day_gain is not None:
            gap += abs(other.per_day_gain - trail.per_day_gain) / max(exp.max_gain_m, 1)
        if best_gap is None or gap < best_gap:
            best, best_gap = other, gap
    return best


def _comparison(profile: HikerProfile, trail: TrailFacts, request: GuideRequest) -> str | None:
    if request.winter and not trail.winter_measures_known():
        return f"The winter route is shorter than the summer trail: it ends at {trail.winter_route_ends.rstrip('.')}."
    km, gain = trail.per_day_km, trail.per_day_gain
    if km is None:
        return None
    per = " a day" if trail.nights else ""
    exp = profile.experience
    if request.difficulty == "push":
        steps = []
        if km > exp.max_distance_km:
            steps.append(f"{round((km / exp.max_distance_km - 1) * 100)}% farther")
        if gain is not None and gain > exp.max_gain_m:
            steps.append(f"{round((gain / exp.max_gain_m - 1) * 100)}% more climbing")
        if steps:
            base = exp.max_gain_trail if gain is not None and gain > exp.max_gain_m else exp.max_distance_trail
            against = f"than {base}, your biggest day" if base and profile.has_history else "than your biggest day so far"
            return f"A step up: {' and '.join(steps)}{per} {against}."
    closest = _closest_hike(profile, trail) if profile.has_history else None
    if closest is not None:
        d_km = km - closest.per_day_km
        d_gain = (gain - closest.per_day_gain) if gain is not None and closest.per_day_gain is not None else None
        # Lead with whichever difference is bigger relative to their max day.
        km_weight = abs(d_km) / max(exp.max_distance_km, 1)
        gain_weight = abs(d_gain) / max(exp.max_gain_m, 1) if d_gain is not None else 0
        if km_weight < 0.05 and gain_weight < 0.05:
            return f"About the same distance and climb as {closest.name}, which you've done."
        if d_gain is not None and gain_weight >= km_weight:
            diff = f"{abs(round(d_gain / 10) * 10)} m {'less' if d_gain < 0 else 'more'} gain"
        else:
            diff = f"{_km(abs(d_km))} {'shorter' if d_km < 0 else 'longer'}"
        return f"Like {closest.name} (which you did) but {diff}{per}."
    climb = f" and {round(gain)} m of climbing" if gain is not None else ""
    phrase = {
        "easier": "an easy day out for you",
        "similar": "right around your usual hike",
        "push": "a solid step up for you",
    }[request.difficulty]
    return f"{_km(km)}{climb}{per}: {phrase}."


def _second_reason(profile: HikerProfile, trail: TrailFacts, request: GuideRequest, parts) -> str | None:
    if request.winter:
        activities = " and ".join(ACTIVITY_LABELS[a] for a in trail.winter_activities)
        return (f"An official {activities} route; avalanche terrain: "
                f"{AVALANCHE_LABELS[trail.avalanche_exposure]}. Check {AVALANCHE_CANADA_URL} before you go.")
    if parts["season"] < 1.0:
        return f"It's alpine: snow can linger up high in {request.on_date:%B}."
    if parts["saved"]:
        return "It's on your saved list."
    if parts["region"] == 1.0:
        return f"In {trail.park_name}, one of your favourite places."
    liked = set(profile.preferences.scenery) & scenery_of(trail)
    if liked:
        return f"Scenery you like: {', '.join(sorted(liked))}."
    return None


# ---- main -----------------------------------------------------------------

def recommend(profile: HikerProfile, request: GuideRequest, trails: Iterable[TrailFacts]) -> RecommendResult:
    pool = list(trails)
    notes: list[str] = []
    for name, keep, suggestion in _filters(profile, request):
        kept = [t for t in pool if keep(t)]
        if pool and not kept:
            notes.append(suggestion)
            return RecommendResult(results=[], matching=0, notes=notes)
        pool = kept
    if not pool:
        return RecommendResult(results=[], matching=0, notes=["No trails in the catalogue fit yet."])

    scored = []
    for trail in pool:
        parts = components(profile, trail, request)
        scored.append((total(parts), parts, trail))
    # Bringing a dog: trails with an official on-leash rule before ones without a rule on file.
    dog_first = (lambda t: 0 if t.dog_policy == "on_leash" else 1) if request.dog else (lambda t: 0)
    scored.sort(key=lambda item: (dog_first(item[2]), -item[0], item[2].popularity_rank or 1000, item[2].name))

    results: list[Recommendation] = []
    per_park: dict[str, int] = {}
    for score, parts, trail in scored:
        park = trail.park_name or f"none:{trail.id}"
        if per_park.get(park, 0) >= MAX_PER_PARK:
            continue
        per_park[park] = per_park.get(park, 0) + 1
        reasons = tuple(r for r in (_comparison(profile, trail, request), _second_reason(profile, trail, request, parts)) if r)
        distance_ratio, gain_ratio = ratios(profile, trail, request.difficulty)
        results.append(Recommendation(
            trail=trail,
            score=score,
            components=parts,
            reasons=reasons[:2],
            est_hours=None if request.winter and not trail.winter_measures_known() else est_hours(profile, trail),
            dog_note=DOG_NOTES.get(trail.dog_policy) if request.dog else None,
            distance_ratio=distance_ratio,
            gain_ratio=gain_ratio,
        ))
        if len(results) == request.limit:
            break
    if len(results) < request.limit and len(pool) <= request.limit:
        notes.append("That's everything that fits. Loosen a filter for more.")
    return RecommendResult(results=results, matching=len(pool), notes=notes)


def describe_hours(hours: float | None) -> str | None:
    return format_hours(hours) if hours is not None else None
