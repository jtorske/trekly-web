"""Every Trail Journal milestone, in one place to add, retune or retire.

A milestone is a `Milestone(...)` entry below: an id (stored in
featured_badges.milestone, so never rename one that has been live), the
category it's filed under, a tier, an icon from MILESTONE_ICONS in
frontend/lib/badge.ts, and a `rule`: one of the rule kinds in
app/milestones.py with its `params`. Adding a milestone that uses an
existing rule kind needs no other change; nothing is stored, so everyone's
milestones (and points) update on their next request.

`detail` says how to earn it. "{goal}" is replaced by the goal, formatted in
the reader's units when the rule measures distance or elevation.

Secret milestones show "???" and their `hint` until earned; the API never
sends an unearned secret's id, title or detail.

`enabled=False` keeps a milestone out of the journal, points and badges
until the data it needs exists (the rule is still written and tested):
Old friend waits for a trail to be loggable more than once.
"""

from dataclasses import dataclass, field
from typing import Any

# Rank points per milestone earned, by tier (app/points.py). The tier also
# sets the badge ring colour.
TIER_POINTS = {
    "bronze": 10,
    "silver": 25,
    "gold": 50,
}

# (id, heading), in journal order.
CATEGORIES = (
    ("getting-out", "Getting out there"),
    ("nights", "Nights out"),
    ("distance", "Distance"),
    ("elevation", "Elevation"),
    ("exploration", "Exploration"),
    ("difficulty", "Difficulty"),
    ("seasons", "Seasons"),
    ("journal", "Journal"),
    ("planning", "Planning and gear"),
    ("secret", "Secret"),
)

# Seasons by hike date (meteorological): month numbers.
SEASONS = {
    "winter": (12, 1, 2),
    "spring": (3, 4, 5),
    "summer": (6, 7, 8),
    "autumn": (9, 10, 11),
}

# The seven core slots of a gear setup (CORE_SLOTS in frontend/app/gear/slots.ts),
# each as the catalogue subcategories that fill it.
CORE_SLOT_CATEGORIES = {
    "backpack": ("backpacks",),
    "tent": ("tents", "tarps", "bivy-sacks"),
    "sleeping-bag": ("sleeping-bags", "quilts", "sleep-liners"),
    "sleeping-pad": ("sleeping-pads",),
    "stove": ("stoves",),
    "footwear": ("hiking-boots", "trail-runners"),
    "rain-jacket": ("rainwear", "wind-layers"),
}

# Worn rather than packed unless the owner says otherwise, so left out of
# base weight (WORN_BY_DEFAULT_SLOTS in frontend/app/gear/weightConfig.ts).
WORN_BY_DEFAULT = CORE_SLOT_CATEGORIES["footwear"]

MOUNTAIN_PARKS = (
    "Banff National Park",
    "Jasper National Park",
    "Yoho National Park",
    "Kootenay National Park",
    "Waterton Lakes National Park",
)
TERRITORIES = ("YT", "NT", "NU")
ATLANTIC = ("NB", "NS", "PE", "NL")


@dataclass(frozen=True)
class Milestone:
    id: str
    category: str
    title: str
    detail: str
    tier: str
    icon: str
    rule: str
    params: dict[str, Any] = field(default_factory=dict)
    hint: str | None = None
    enabled: bool = True

    @property
    def secret(self) -> bool:
        return self.hint is not None


M = Milestone

MILESTONES = (
    # Getting out there
    M("first-hike", "getting-out", "First steps", "Log your first hike", "bronze", "first-hike", "hikes", {"goal": 1}),
    M("trail-regular", "getting-out", "Trail regular", "Log {goal} hikes", "bronze", "boot", "hikes", {"goal": 10}),
    M("trail-devotee", "getting-out", "Trail devotee", "Log {goal} hikes", "silver", "boots", "hikes", {"goal": 25}),
    M("trailblazer", "getting-out", "Trailblazer", "Log {goal} hikes", "gold", "blaze", "hikes", {"goal": 50}),
    # Off until a trail can be logged more than once (hike_logs is one row per user and trail).
    M("old-friend", "getting-out", "Old friend", "Hike the same trail twice", "bronze", "repeat", "repeat_trail",
      enabled=False),
    # Nights out (a trip's nights are its trail's typical nights)
    M("first-overnight", "nights", "Under the stars", "Log an overnight trip", "bronze", "first-overnight",
      "trip_nights", {"nights": 1}),
    M("long-weekend", "nights", "Long weekend", "Log a trip of 3 or more nights", "silver", "tent-moon",
      "trip_nights", {"nights": 3}),
    M("week-in-the-wild", "nights", "Week in the wild", "Log a trip of 6 or more nights", "gold", "campfire",
      "trip_nights", {"nights": 6}),
    M("backcountry-regular", "nights", "Backcountry regular", "Spend {goal} nights out in total", "silver", "moon",
      "total_nights", {"goal": 10}),
    # Distance (trails with a known length only)
    M("hundred-km", "distance", "Century", "Hike {goal} in total", "bronze", "hundred-km", "distance", {"goal": 100}),
    M("long-hauler", "distance", "Long hauler", "Hike {goal} in total", "silver", "path", "distance", {"goal": 250}),
    M("thousand-km", "distance", "Thousand-kilometre club", "Hike {goal} in total", "gold", "compass",
      "distance", {"goal": 1000}),
    # Elevation (trails with known elevation only)
    M("vertical-km", "elevation", "Vertical kilometre", "Climb {goal} in one hike", "silver", "switchbacks",
      "climb_one", {"goal": 1000}),
    M("sky-high", "elevation", "Sky high", "Hike a trail that tops out at {goal} or higher", "silver", "summit",
      "high_point", {"goal": 2500}),
    M("everest-club", "elevation", "Everest club", "Climb {goal} in total", "gold", "flag", "total_gain",
      {"goal": 8849}),
    # Exploration
    M("five-parks", "exploration", "Park hopper", "Hike in {goal} parks or regions", "bronze", "five-parks",
      "regions", {"goal": 5}),
    M("grand-slam", "exploration", "Mountain parks grand slam",
      "Hike in Banff, Jasper, Yoho, Kootenay and Waterton Lakes", "gold", "peaks", "parks_all",
      {"parks": MOUNTAIN_PARKS}),
    M("provincial-passport", "exploration", "Provincial passport", "Hike in {goal} provinces or territories", "gold",
      "passport", "provinces", {"goal": 5}),
    M("true-north", "exploration", "True north", "Hike in a territory", "silver", "north-star", "any_province",
      {"codes": TERRITORIES}),
    M("coast-to-coast", "exploration", "Coast to coast", "Hike in British Columbia and an Atlantic province",
      "silver", "waves", "every_group", {"groups": (("BC",), ATLANTIC)}),
    M("park-completionist", "exploration", "Park completionist",
      "Hike every trail in a park ({goal}+ trails)", "silver", "check-map", "park_complete",
      {"min": 3}),
    # Difficulty
    M("full-spectrum", "difficulty", "Full spectrum", "Hike an easy, moderate, difficult and extreme trail",
      "silver", "spectrum", "difficulties", {"levels": ("easy", "moderate", "difficult", "extreme")}),
    M("grinder", "difficulty", "Grinder", "Hike {goal} difficult trails", "silver", "pickaxe", "difficulty",
      {"level": "difficult", "goal": 5}),
    M("extreme", "difficulty", "Extreme", "Hike an extreme trail", "silver", "starburst", "difficulty",
      {"level": "extreme", "goal": 1}),
    # Seasons (by the days of each trip: its hike date plus its nights)
    M("larch-madness", "seasons", "Larch madness", "Hike a larch trail between September 15 and October 10",
      "silver", "larch", "tagged_in_window", {"tag": "larch", "start": (9, 15), "end": (10, 10)}),
    M("winter-warrior", "seasons", "Winter warrior", "Hike between December and February", "silver", "snowflake",
      "in_months", {"months": SEASONS["winter"]}),
    M("four-seasons", "seasons", "Four seasons", "Hike in all four seasons", "gold", "seasons", "seasons",
      {"seasons": SEASONS}),
    M("monthly-regular", "seasons", "Monthly regular", "Hike in {goal} months in a row", "bronze", "calendar",
      "consecutive_months", {"goal": 3}),
    # Journal
    M("storyteller", "journal", "Storyteller", "Write notes on {goal} hikes", "bronze", "quill", "notes",
      {"goal": 5}),
    M("shutterbug", "journal", "Shutterbug", "Add photos to {goal} hikes", "bronze", "camera", "photos",
      {"goal": 5}),
    # Planning and gear
    M("planner", "planning", "Planner", "Make your first trip plan", "bronze", "map", "plans", {"goal": 1}),
    M("permit-hunter", "planning", "Permit hunter", "Set your first availability alert", "bronze", "bell",
      "alerts", {"goal": 1}),
    M("lucky-break", "planning", "Lucky break", "Get a “site available” notice from an alert", "silver",
      "clover", "alert_notified"),
    M("packed-and-ready", "planning", "Packed and ready", "Fill all 7 main slots in a gear setup", "silver",
      "backpack", "setup_core", {"slots": CORE_SLOT_CATEGORIES}),
    # A complete setup (all 7 main slots), so an empty one can't weigh 0 kg.
    M("ultralight", "planning", "Ultralight", "Get a full setup's base weight under {goal}", "gold", "feather",
      "base_weight", {"goal_kg": 9}),
    # Secret
    M("stairmaster", "secret", "Stairmaster", "Hike the Grouse Grind", "bronze", "stairs", "trail",
      {"name": "Grouse Grind", "province": "BC"}, hint="A famously steep climb above Vancouver"),
    M("coastal-legend", "secret", "Coastal legend", "Hike the West Coast Trail", "gold", "lighthouse", "trail",
      {"name": "West Coast Trail", "province": "BC"}, hint="Ladders, beaches and surge channels"),
    M("skyline", "secret", "Skyline", "Hike Jasper's Skyline Trail", "silver", "ridge", "trail",
      {"name": "Skyline Trail", "province": "AB"}, hint="Three days above the treeline"),
)

ACTIVE = tuple(milestone for milestone in MILESTONES if milestone.enabled)
BY_ID = {milestone.id: milestone for milestone in ACTIVE}
