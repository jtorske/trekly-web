"""What Trekly Guide knows about a hiker: get_hiker_profile(db, user_id).

build_profile() does the work over plain values (unit-tested and used by the
persona evals); get_hiker_profile() loads those values for one user.

Experience comes from the Trail Journal: the biggest day they've done
(distance, gain, high point) and their typical hike (the median of the last 10
dated hikes). An overnight counts per day on trail, so a 3-day 45 km trip is a
15 km day.

With fewer than MIN_HISTORY_HIKES hikes, or with "Use my history to
personalize Trekly Guide" turned off, the numbers come instead from the
experience level they chose (STATED_BASELINES), marked basis "stated".

pace_factor compares their logged "Time on trail" with Naismith's estimate
for the same trail (app/guide/estimate.py): 1.2 means they take 20% longer.
It needs MIN_TIMED_HIKES timed day hikes; until then it stays 1.0 with low
confidence.

Privacy: the profile is the owner's alone. It's returned only to them
(GET /api/guide/profile) and is never stored; it's worked out on each request.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from app.guide.estimate import SCENERY_KEYS, TrailFacts, is_winter, naismith_hours

MIN_HISTORY_HIKES = 2
TYPICAL_WINDOW = 10

PACE_MIN, PACE_MAX = 0.6, 1.6
MIN_TIMED_HIKES = 3
# Timed hikes needed for each confidence level.
PACE_CONFIDENCE = ((6, "high"), (MIN_TIMED_HIKES, "medium"))

# What someone at each experience level can be taken to have done when the
# journal doesn't say: (biggest day km, biggest day gain m). The typical hike
# is STATED_TYPICAL_SHARE of that.
STATED_BASELINES = {
    "new": (8.0, 400),
    "few_seasons": (15.0, 900),
    "seasoned": (22.0, 1400),
    None: (10.0, 500),
}
STATED_TYPICAL_SHARE = 0.7


@dataclass(frozen=True)
class HikeRecord:
    trail: TrailFacts
    hiked_on: date | None = None
    duration_minutes: int | None = None


@dataclass(frozen=True)
class StatedPreferences:
    """What they told Trekly in /welcome and Settings."""

    hiking_style: str | None = None
    experience_level: str | None = None
    favourite_regions: tuple[str, ...] = ()
    scenery: tuple[str, ...] = ()
    hikes_with_dog: bool = False
    use_history: bool = True


@dataclass(frozen=True)
class Experience:
    hike_count: int
    max_distance_km: float
    max_gain_m: float
    max_high_point_m: int | None
    typical_distance_km: float
    typical_gain_m: float
    overnight_count: int
    max_nights: int
    # "history" (from the journal) or "stated" (from their experience level).
    basis: str
    # The trails behind the maxima, for reasons like "more than Ha Ling".
    max_distance_trail: str | None = None
    max_gain_trail: str | None = None
    max_high_point_trail: str | None = None


@dataclass(frozen=True)
class Pace:
    factor: float
    confidence: str
    timed_hikes: int


@dataclass(frozen=True)
class WinterExperience:
    # Dated hikes in Dec-Mar, and how many of those were on official winter routes.
    # (Hike logs have no activity type yet, so the date is the signal.)
    winter_hikes: int
    winter_route_hikes: int


@dataclass(frozen=True)
class HikerProfile:
    experience: Experience
    pace: Pace
    preferences: StatedPreferences
    home_province: str | None = None
    saved_trail_ids: frozenset = frozenset()
    hiked_trail_ids: frozenset = frozenset()
    gear_categories: frozenset[str] = frozenset()
    winter: WinterExperience = WinterExperience(0, 0)
    # The hikes themselves (history on only), for "Like X but..." reasons.
    hikes: tuple[HikeRecord, ...] = field(default=(), repr=False)

    @property
    def has_history(self) -> bool:
        return self.experience.basis == "history"


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _top(hikes: list[HikeRecord], key) -> tuple[float | None, str | None]:
    best = max((h for h in hikes if key(h) is not None), key=key, default=None)
    return (key(best), best.trail.name) if best else (None, None)


def _per_day_km(hike: HikeRecord) -> float | None:
    return hike.trail.per_day_km


def _per_day_gain(hike: HikeRecord) -> float | None:
    return hike.trail.per_day_gain


def pace_from(hikes: list[HikeRecord]) -> Pace:
    """Their median ratio of logged time to Naismith time, over timed day hikes."""
    ratios = []
    for hike in hikes:
        trail = hike.trail
        if not hike.duration_minutes or trail.nights:
            continue
        estimate = naismith_hours(trail.distance_km, trail.elevation_gain_m)
        if not estimate:
            continue
        ratios.append((hike.duration_minutes / 60) / estimate)
    if len(ratios) < MIN_TIMED_HIKES:
        return Pace(factor=1.0, confidence="low", timed_hikes=len(ratios))
    factor = min(PACE_MAX, max(PACE_MIN, statistics.median(ratios)))
    confidence = next(level for needed, level in PACE_CONFIDENCE if len(ratios) >= needed)
    return Pace(factor=round(factor, 2), confidence=confidence, timed_hikes=len(ratios))


def stated_experience(level: str | None, hike_count: int = 0) -> Experience:
    max_km, max_gain = STATED_BASELINES.get(level, STATED_BASELINES[None])
    return Experience(
        hike_count=hike_count,
        max_distance_km=max_km,
        max_gain_m=max_gain,
        max_high_point_m=None,
        typical_distance_km=round(max_km * STATED_TYPICAL_SHARE, 1),
        typical_gain_m=round(max_gain * STATED_TYPICAL_SHARE),
        overnight_count=0,
        max_nights=0,
        basis="stated",
    )


def experience_from(hikes: list[HikeRecord], level: str | None) -> Experience:
    if len(hikes) < MIN_HISTORY_HIKES:
        return stated_experience(level, len(hikes))
    stated = stated_experience(level)
    max_km, km_trail = _top(hikes, _per_day_km)
    max_gain, gain_trail = _top(hikes, _per_day_gain)
    max_high, high_trail = _top(hikes, lambda h: h.trail.max_elevation_m)

    dated = sorted((h for h in hikes if h.hiked_on), key=lambda h: h.hiked_on, reverse=True)
    # The typical hike: the last 10 dated hikes, or every hike if none is dated.
    recent = dated[:TYPICAL_WINDOW] or hikes
    typical_km = _median([v for h in recent if (v := _per_day_km(h)) is not None])
    typical_gain = _median([v for h in recent if (v := _per_day_gain(h)) is not None])

    max_km = max_km if max_km is not None else stated.max_distance_km
    max_gain = max_gain if max_gain is not None else stated.max_gain_m
    overnights = [h for h in hikes if h.trail.nights]
    return Experience(
        hike_count=len(hikes),
        max_distance_km=round(max_km, 1),
        max_gain_m=round(max_gain),
        max_high_point_m=int(max_high) if max_high is not None else None,
        typical_distance_km=round(min(typical_km if typical_km is not None else max_km * STATED_TYPICAL_SHARE, max_km), 1),
        typical_gain_m=round(min(typical_gain if typical_gain is not None else max_gain * STATED_TYPICAL_SHARE, max_gain)),
        overnight_count=len(overnights),
        max_nights=max((h.trail.nights for h in overnights), default=0),
        basis="history",
        max_distance_trail=km_trail,
        max_gain_trail=gain_trail,
        max_high_point_trail=high_trail,
    )


def build_profile(
    hikes: list[HikeRecord],
    prefs: StatedPreferences,
    *,
    home_province: str | None = None,
    saved_trail_ids=(),
    gear_categories=(),
) -> HikerProfile:
    """The profile from plain values. With use_history off, hikes, saved trails
    and gear are left out and only the stated answers count."""
    prefs = StatedPreferences(
        hiking_style=prefs.hiking_style,
        experience_level=prefs.experience_level,
        favourite_regions=tuple(prefs.favourite_regions),
        scenery=tuple(s for s in prefs.scenery if s in SCENERY_KEYS),
        hikes_with_dog=prefs.hikes_with_dog,
        use_history=prefs.use_history,
    )
    if not prefs.use_history:
        return HikerProfile(
            experience=stated_experience(prefs.experience_level),
            pace=Pace(factor=1.0, confidence="low", timed_hikes=0),
            preferences=prefs,
            home_province=home_province,
        )
    winter = [h for h in hikes if h.hiked_on and is_winter(h.hiked_on)]
    return HikerProfile(
        experience=experience_from(hikes, prefs.experience_level),
        pace=pace_from(hikes),
        preferences=prefs,
        home_province=home_province,
        saved_trail_ids=frozenset(saved_trail_ids),
        hiked_trail_ids=frozenset(h.trail.id for h in hikes),
        gear_categories=frozenset(gear_categories),
        winter=WinterExperience(
            winter_hikes=len(winter),
            winter_route_hikes=sum(1 for h in winter if h.trail.winter_activities),
        ),
        hikes=tuple(hikes),
    )


def get_hiker_profile(db, user_id: UUID, *, use_history: bool | None = None) -> HikerProfile:
    """The profile for one user, honouring their "Use my history" setting
    (use_history overrides it, e.g. for a one-off "ignore my history")."""
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.models.account import Profile, SavedTrail
    from app.models.catalog import CatalogCategory
    from app.models.hike_log import HikeLog
    from app.models.preferences import ProfilePreferences
    from app.models.user_gear import UserGearItem

    row = db.get(ProfilePreferences, user_id)
    prefs = StatedPreferences(
        hiking_style=row.hiking_style if row else None,
        experience_level=row.experience if row else None,
        favourite_regions=tuple(row.favourite_regions or ()) if row else (),
        scenery=tuple(row.scenery or ()) if row else (),
        hikes_with_dog=bool(row.hikes_with_dog) if row else False,
        use_history=(row.guide_use_history if row else True) if use_history is None else use_history,
    )
    profile_row = db.get(Profile, user_id)
    home = profile_row.home_province if profile_row else None
    if not prefs.use_history:
        return build_profile([], prefs, home_province=home)

    logs = db.scalars(
        select(HikeLog).where(HikeLog.user_id == user_id).options(joinedload(HikeLog.trail))
    ).all()
    hikes = [HikeRecord(TrailFacts.from_trail(log.trail), log.hiked_on, log.duration_minutes) for log in logs]
    saved = db.scalars(select(SavedTrail.trail_id).where(SavedTrail.user_id == user_id)).all()
    categories = set()
    for slug, parent in db.execute(
        select(CatalogCategory.slug, CatalogCategory.parent_id)
        .join(UserGearItem, UserGearItem.category_id == CatalogCategory.id)
        .where(UserGearItem.user_id == user_id)
    ).all():
        categories.add(slug)
        if parent is not None:
            parent_row = db.get(CatalogCategory, parent)
            if parent_row is not None:
                categories.add(parent_row.slug)
    return build_profile(hikes, prefs, home_province=home, saved_trail_ids=saved, gear_categories=categories)
