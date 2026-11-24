"""Shared measures for Trekly Guide: trail times, seasons and scenery.

Trail time is Naismith's rule: 1 hour per 5 km on the flat plus 1 hour per
600 m of climbing. It's a moving-time estimate for a fit hiker without long
breaks; a hiker's pace_factor (app/guide/profile.py) scales it to them.

Seasons are by calendar month, the same for every trail, so the rules are easy
to explain and test:
- WINTER_MONTHS (Dec-Mar): only trails with official winter_activities are in
  play, and avalanche exposure decides a lot.
- SHOULDER_MONTHS (Apr, May, Nov): snow lingers up high, so alpine trails are
  marked down (not removed).
- AVALANCHE_SEASON_MONTHS (Nov-May): when a trail's ATES rating matters for
  "Am I ready?" (Avalanche Canada's forecasts run through these months).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

FLAT_KMH = 5.0
CLIMB_M_PER_HOUR = 600.0

WINTER_MONTHS = frozenset({12, 1, 2, 3})
SHOULDER_MONTHS = frozenset({4, 5, 11})
AVALANCHE_SEASON_MONTHS = frozenset({11, 12, 1, 2, 3, 4, 5})

AVALANCHE_CANADA_URL = "https://avalanche.ca"


def naismith_hours(distance_km: float | None, gain_m: float | None) -> float | None:
    """Moving time in hours, or None without a distance. Unknown gain counts as 0."""
    if distance_km is None or distance_km <= 0:
        return None
    return distance_km / FLAT_KMH + (gain_m or 0) / CLIMB_M_PER_HOUR


def is_winter(day: date) -> bool:
    return day.month in WINTER_MONTHS


def is_shoulder(day: date) -> bool:
    return day.month in SHOULDER_MONTHS


def in_avalanche_season(day: date) -> bool:
    return day.month in AVALANCHE_SEASON_MONTHS


def this_weekend(today: date) -> date:
    """The Saturday of this weekend: today on a Saturday, yesterday's on a Sunday."""
    weekday = today.weekday()  # Monday 0 ... Sunday 6
    if weekday == 6:
        return today - timedelta(days=1)
    return today + timedelta(days=5 - weekday)


def format_hours(hours: float) -> str:
    """'45 min', '3 h', '4.5 h' (to the nearest half hour above an hour)."""
    if hours < 1:
        return f"{max(5, round(hours * 60 / 5) * 5)} min"
    half = round(hours * 2) / 2
    return f"{half:g} h"


@dataclass(frozen=True)
class TrailFacts:
    """The trail measures the Guide works with, as plain values.

    Built from a Trail row (from_trail) or directly in tests. distance_km and
    elevation_gain_m cover the whole trip (round trip, loop or one way);
    per_day_* split an overnight evenly over its days on trail.
    """

    id: object
    slug: str
    name: str
    province_code: str | None
    park_name: str | None
    terrain: str
    distance_km: float | None
    elevation_gain_m: int | None
    max_elevation_m: int | None
    nights: int
    climate_zone: str | None
    tags: tuple[str, ...]
    description: str | None
    winter_activities: tuple[str, ...]
    avalanche_exposure: str
    winter_route_ends: str | None
    dog_policy: str
    popularity_rank: int | None
    has_photo: bool

    @property
    def days(self) -> int:
        return self.nights + 1

    @property
    def per_day_km(self) -> float | None:
        return None if self.distance_km is None else self.distance_km / self.days

    @property
    def per_day_gain(self) -> float | None:
        return None if self.elevation_gain_m is None else self.elevation_gain_m / self.days

    def winter_measures_known(self) -> bool:
        """False when only part of the trail is a winter route, so the summer
        distance and gain don't describe the winter outing."""
        return not self.winter_route_ends

    @classmethod
    def from_trail(cls, trail) -> "TrailFacts":
        return cls(
            id=trail.id,
            slug=trail.slug,
            name=trail.name,
            province_code=trail.province_code,
            park_name=trail.park_name,
            terrain=trail.terrain_difficulty,
            distance_km=float(trail.distance_km) if trail.distance_km is not None else None,
            elevation_gain_m=trail.elevation_gain_m,
            max_elevation_m=trail.max_elevation_m,
            nights=trail.typical_duration_nights or 0,
            climate_zone=trail.climate_zone,
            tags=tuple(trail.tags or ()),
            description=trail.description,
            winter_activities=tuple(trail.winter_activities or ()),
            avalanche_exposure=trail.avalanche_exposure or "unknown",
            winter_route_ends=trail.winter_route_ends,
            dog_policy=getattr(trail, "dog_policy", None) or "unknown",
            popularity_rank=trail.popularity_rank,
            has_photo=trail.photo is not None,
        )


# Scenery labels, read from the trail's name, description and tags. They only
# nudge the ranking toward what someone likes, never filter, so a keyword
# match is enough. Keys are mirrored in frontend/lib/guide.ts.
SCENERY = {
    "lakes": ("lake", "lakes", "pond", "tarn", "lac "),
    "waterfalls": ("falls", "waterfall", "cascade", "chute"),
    "summits": ("summit", "peak", "mount ", "mountain", "lookout", "ridge", "viewpoint"),
    "glaciers": ("glacier", "icefield", "icefall"),
    "coast": ("coast", "ocean", "beach", "sea ", "shore", "cove", "fjord", "headland", "cape "),
    "forest": ("forest", "old-growth", "old growth", "rainforest", "cedar", "woods"),
    "larches": ("larch",),
    "canyons": ("canyon", "gorge"),
}
SCENERY_KEYS = tuple(SCENERY)


def scenery_of(trail: TrailFacts) -> frozenset[str]:
    text = f" {trail.name} {trail.description or ''} {' '.join(trail.tags)} ".lower()
    return frozenset(key for key, words in SCENERY.items() if any(word in text for word in words))
