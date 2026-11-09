"""Trail preferences from the /welcome setup flow, and the picks they drive.

Hiking style, experience and favourite regions are private: only
the owner reads them (GET /api/me/preferences), they never appear on a public
profile, and row-level security keeps other clients off the table (migration
6d1a8f3b2c57). Their only use is ordering trail recommendations.

The option lists are mirrored in frontend/lib/onboarding.ts; a frontend test
checks the two agree.

The interests step ("What gets you out there?") was removed (migration
c7e3a9f1d5b2): profile_preferences.interests is still stored but nothing
reads it, and picks rely on home province, style, experience and regions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

HIKING_STYLES = ("day", "overnight", "both")
EXPERIENCE_LEVELS = ("new", "few_seasons", "seasoned")

# The setup flow's screens, in order. onboarding_step is where to resume.
ONBOARDING_STEPS = (
    "name",
    "photo",
    "home",
    "style",
    "experience",
    "regions",
    # Which trails they've hiked before, and what's in their pack (b4e7a2c9d1f3).
    "hiked",
    "pack",
    "units",
    "privacy",
    "done",
)
ONBOARDING_OUTCOMES = ("completed", "skipped")


@dataclass(frozen=True)
class Region:
    slug: str
    label: str
    park_name: str
    province: str


# Parks people plan trips around, matched to trails.park_name exactly. Explore's
# quick chips use the same park names.
REGIONS = (
    Region("banff", "Banff", "Banff National Park", "AB"),
    Region("jasper", "Jasper", "Jasper National Park", "AB"),
    Region("kananaskis", "Kananaskis", "Kananaskis Country", "AB"),
    Region("waterton", "Waterton Lakes", "Waterton Lakes National Park", "AB"),
    Region("yoho", "Yoho", "Yoho National Park", "BC"),
    Region("kootenay", "Kootenay", "Kootenay National Park", "BC"),
    Region("assiniboine", "Mount Assiniboine", "Mount Assiniboine Provincial Park", "BC"),
    Region("robson", "Mount Robson", "Mount Robson Provincial Park", "BC"),
    Region("garibaldi", "Garibaldi", "Garibaldi Provincial Park", "BC"),
    Region("joffre", "Joffre Lakes", "Joffre Lakes Provincial Park", "BC"),
    Region("kokanee", "Kokanee Glacier", "Kokanee Glacier Provincial Park", "BC"),
    Region("cape-scott", "Cape Scott", "Cape Scott Provincial Park", "BC"),
    Region("tombstone", "Tombstone", "Tombstone Territorial Park", "YT"),
    Region("kluane", "Kluane", "Kluane National Park and Reserve", "YT"),
    Region("prince-albert", "Prince Albert", "Prince Albert National Park", "SK"),
    Region("whiteshell", "Whiteshell", "Whiteshell Provincial Park", "MB"),
    Region("algonquin", "Algonquin", "Algonquin Provincial Park", "ON"),
    Region("killarney", "Killarney", "Killarney Provincial Park", "ON"),
    Region("bruce", "Bruce Peninsula", "Bruce Peninsula National Park", "ON"),
    Region("lake-superior", "Lake Superior", "Lake Superior Provincial Park", "ON"),
    Region("pukaskwa", "Pukaskwa", "Pukaskwa National Park", "ON"),
    Region("gaspesie", "Gaspésie", "Parc national de la Gaspésie", "QC"),
    Region("forillon", "Forillon", "Forillon National Park", "QC"),
    Region("cape-breton", "Cape Breton Highlands", "Cape Breton Highlands National Park", "NS"),
    Region("gros-morne", "Gros Morne", "Gros Morne National Park", "NL"),
)
REGION_SLUGS = tuple(region.slug for region in REGIONS)
PARK_BY_REGION = {region.slug: region.park_name for region in REGIONS}

# How well each terrain suits each experience level.
_DIFFICULTY_FIT = {
    "new": {"easy": 3.0, "moderate": 1.0, "difficult": -3.0, "extreme": -6.0},
    "few_seasons": {"easy": 0.5, "moderate": 3.0, "difficult": 1.5, "extreme": -3.0},
    "seasoned": {"easy": -1.0, "moderate": 1.0, "difficult": 3.0, "extreme": 2.0},
}

MAX_PER_PARK = 2


@dataclass(frozen=True)
class Preferences:
    hiking_style: str | None = None
    experience: str | None = None
    favourite_regions: tuple[str, ...] = ()
    home_province: str | None = None


def score(trail, prefs: Preferences) -> float:
    """How well a trail fits someone's answers; higher is better."""
    total = 0.0
    nights = trail.typical_duration_nights or 0
    if prefs.hiking_style == "day":
        total += 3.0 if nights == 0 else -3.0
    elif prefs.hiking_style == "overnight":
        total += 3.0 if nights >= 1 else -2.0
    if prefs.experience in _DIFFICULTY_FIT:
        total += _DIFFICULTY_FIT[prefs.experience].get(trail.terrain_difficulty, 0.0)
    favourite_parks = {PARK_BY_REGION[slug] for slug in prefs.favourite_regions if slug in PARK_BY_REGION}
    if trail.park_name and trail.park_name in favourite_parks:
        total += 4.0
    if prefs.home_province and trail.province_code == prefs.home_province:
        total += 1.5
    return total


def recommend(trails: Iterable, prefs: Preferences, limit: int = 5) -> list:
    """The best-fitting trails, at most MAX_PER_PARK from any one park.

    Ties keep the catalogue's popularity order, so someone who skipped every
    question still gets the most popular trails.
    """

    def popularity(trail) -> int:
        return trail.popularity_rank if trail.popularity_rank is not None else 1_000_000

    ranked = sorted(trails, key=lambda trail: (-score(trail, prefs), popularity(trail), trail.name))
    picks: list = []
    per_park: dict[str, int] = {}
    for trail in ranked:
        park = trail.park_name or f"none:{trail.id}"
        if per_park.get(park, 0) >= MAX_PER_PARK:
            continue
        per_park[park] = per_park.get(park, 0) + 1
        picks.append(trail)
        if len(picks) == limit:
            break
    return picks
