"""Every Trail Journal milestone, in one place to add, retune or retire.

A milestone is a `Milestone(...)` entry below: an id (stored in
featured_badges.milestone, so never rename one that has been live), the
category it's filed under, a tier, an icon from MILESTONE_ICONS in
frontend/lib/badge.ts, and a `rule`: one of the rule kinds in
app/milestones.py with its `params`. Adding a milestone that uses an
existing rule kind needs no other change; nothing is stored, so everyone's
milestones (and points) update on their next request.

`detail` says how to earn it. "{goal}" is replaced by the goal, formatted in
the reader's units when the rule measures distance or elevation. `note` is a
short aside shown under it (e.g. which trails count).

Secret milestones show "???" and their `hint` until earned; the API never
sends an unearned secret's id, title or detail.

None is earned by one specific trail (trail stamps do that), and none needs
the same trail hiked twice: a journal has one entry per trail.

Rules that read trail data (distance, elevation, route type) are also
checked against the whole active catalogue: one that can't be earned even
by hiking every trail is marked "needs more trail data" until the
catalogue's measurements fill in (TRAIL_DATA_RULES in app/milestones.py).
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

# (id, heading), in journal order. The ids name the journal sections
# (?section=milestones-<id>); "seasons" is also what public profiles leave
# out while "Hide dates on my hikes" is on.
CATEGORIES = (
    ("getting-out", "Getting out there"),
    ("nights", "Nights out"),
    ("distance", "Distance"),
    ("elevation", "Elevation"),
    ("exploration", "Exploration"),
    ("difficulty", "Difficulty"),
    ("routes", "Route types"),
    ("seasons", "Seasons and calendar"),
    ("journal", "Journal"),
    ("planning", "Planning"),
    ("gear", "Gear"),
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

# The Big Three as the gear page counts it (BIG_THREE_PIECES in
# frontend/app/gear/weightConfig.ts): pack, shelter, and a sleep system of
# both a bag and a pad.
BIG_THREE_SLOTS = ("backpack", "tent", "sleeping-bag", "sleeping-pad")

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

KNOWN_LENGTH = "Counts trails with a known length."
KNOWN_ELEVATION = "Counts trails with known elevation."
KNOWN_ROUTE = "Counts trails with a known route type."


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
    note: str | None = None

    @property
    def secret(self) -> bool:
        return self.hint is not None


M = Milestone

MILESTONES = (
    # Getting out there
    M("first-hike", "getting-out", "First steps", "Hike your first trail", "bronze", "first-hike", "hikes",
      {"goal": 1}),
    M("trail-regular", "getting-out", "Trail regular", "Hike {goal} trails", "bronze", "boot", "hikes", {"goal": 10}),
    M("trail-devotee", "getting-out", "Devotee", "Hike {goal} trails", "silver", "boots", "hikes", {"goal": 25}),
    M("trailblazer", "getting-out", "Trailblazer", "Hike {goal} trails", "gold", "blaze", "hikes", {"goal": 50}),
    M("every-last-trail", "getting-out", "Every last trail", "Hike every active trail in the catalogue", "gold",
      "all-trails", "every_trail", hint="Leave no trail unhiked"),
    # Nights out (a trip's nights are its trail's typical nights)
    M("first-overnight", "nights", "Under the stars", "Go on your first overnight trip", "bronze",
      "first-overnight", "trip_nights", {"nights": 1}),
    M("long-weekend", "nights", "Long weekend", "Go on a single trip of 3 or more nights", "silver", "tent-moon",
      "trip_nights", {"nights": 3}),
    M("week-in-the-wild", "nights", "Week in the wild", "Go on a single trip of 6 or more nights", "gold",
      "campfire", "trip_nights", {"nights": 6}),
    M("backcountry-regular", "nights", "Backcountry regular", "Spend {goal} nights out in total", "silver", "moon",
      "total_nights", {"goal": 10}),
    M("moonlighter", "nights", "Moonlighter", "Spend {goal} nights out in total", "gold", "stars",
      "total_nights", {"goal": 30}),
    # Distance (canonical km; trails with a known length only)
    M("hundred-km", "distance", "Century", "Hike {goal} in total", "bronze", "hundred-km", "distance",
      {"goal": 100}, note=KNOWN_LENGTH),
    M("long-hauler", "distance", "Long hauler", "Hike {goal} in total", "silver", "path", "distance",
      {"goal": 250}, note=KNOWN_LENGTH),
    M("thousand-km", "distance", "Thousand-kilometre club", "Hike {goal} in total", "gold", "compass",
      "distance", {"goal": 1000}, note=KNOWN_LENGTH),
    M("marathon-day", "distance", "Marathon day", "Hike a single trail of {goal} or more", "silver", "stopwatch",
      "longest", {"goal": 42.2}, note=KNOWN_LENGTH),
    # Elevation (trails with known elevation only)
    M("vertical-km", "elevation", "Vertical kilometre", "Climb {goal} on a single trail", "silver", "switchbacks",
      "climb_one", {"goal": 1000}, note=KNOWN_ELEVATION),
    M("sky-high", "elevation", "Sky high", "Hike a trail that tops out at {goal} or higher", "silver", "summit",
      "high_point", {"goal": 2500}, note=KNOWN_ELEVATION),
    M("everest-club", "elevation", "Everest club", "Climb {goal} in total", "gold", "flag", "total_gain",
      {"goal": 8849}, note=KNOWN_ELEVATION),
    # Exploration
    M("five-parks", "exploration", "Park hopper", "Hike in {goal} parks or regions", "bronze", "five-parks",
      "regions", {"goal": 5}),
    M("park-collector", "exploration", "Park collector", "Hike in {goal} parks or regions", "gold", "stamps",
      "regions", {"goal": 15}),
    M("grand-slam", "exploration", "Mountain parks grand slam",
      "Hike in Banff, Jasper, Yoho, Kootenay and Waterton Lakes", "gold", "peaks", "parks_all",
      {"parks": MOUNTAIN_PARKS}),
    M("divide-crosser", "exploration", "Divide crosser", "Hike in both Alberta and British Columbia", "bronze",
      "divide", "every_group", {"groups": (("AB",), ("BC",))}),
    M("provincial-passport", "exploration", "Provincial passport", "Hike in {goal} provinces or territories",
      "silver", "passport", "provinces", {"goal": 5}),
    M("coast-to-coast", "exploration", "Coast to coast", "Hike in British Columbia and an Atlantic province",
      "gold", "waves", "every_group", {"groups": (("BC",), ATLANTIC)}),
    M("true-north", "exploration", "True north", "Hike in a territory", "silver", "north-star", "any_province",
      {"codes": TERRITORIES}),
    # Parks with fewer trails don't count, or one hike would finish one.
    M("park-completionist", "exploration", "Park completionist",
      "Hike every trail in a park or region with {goal} or more", "gold", "check-map", "park_complete",
      {"min": 3}),
    M("off-the-beaten-path", "exploration", "Off the beaten path",
      "Hike {goal} trails outside the 50 most popular", "silver", "trail-fork", "less_popular",
      {"outside": 50, "goal": 5}),
    M("crowd-pleaser", "exploration", "Crowd pleaser", "Hike all of the 10 most popular trails", "silver",
      "crowd", "most_popular", {"top": 10}),
    # Difficulty
    M("full-spectrum", "difficulty", "Full spectrum", "Hike an easy, moderate, difficult and extreme trail",
      "silver", "spectrum", "difficulties", {"levels": ("easy", "moderate", "difficult", "extreme")}),
    M("grinder", "difficulty", "Grinder", "Hike {goal} difficult trails", "silver", "pickaxe", "difficulty",
      {"level": "difficult", "goal": 5}),
    M("extreme", "difficulty", "Into the extreme", "Hike an extreme trail", "silver", "starburst", "difficulty",
      {"level": "extreme", "goal": 1}),
    M("glutton-for-punishment", "difficulty", "Glutton for punishment", "Hike {goal} extreme trails", "gold",
      "flame", "difficulty", {"level": "extreme", "goal": 3}),
    # Route types (trails with a known route type only)
    M("loop-de-loop", "routes", "Loop de loop", "Hike {goal} loop trails", "bronze", "repeat", "route_type",
      {"route": "loop", "goal": 5}, note=KNOWN_ROUTE),
    M("one-way-ticket", "routes", "One-way ticket", "Hike a point-to-point trail", "bronze", "arrow",
      "route_type", {"route": "point_to_point", "goal": 1}, note=KNOWN_ROUTE),
    # Seasons and calendar (by the days of each trip: its hike date plus its nights)
    M("larch-madness", "seasons", "Larch madness", "Hike a larch trail between September 15 and October 10",
      "silver", "larch", "tagged_in_window", {"tag": "larch", "start": (9, 15), "end": (10, 10)}),
    M("winter-warrior", "seasons", "Winter warrior", "Hike in December, January or February", "silver",
      "snowflake", "in_months", {"months": SEASONS["winter"]}),
    M("four-seasons", "seasons", "Four seasons", "Hike in all four seasons", "gold", "seasons", "seasons",
      {"seasons": SEASONS}),
    M("monthly-regular", "seasons", "Monthly regular", "Hike in {goal} months in a row", "silver", "calendar",
      "consecutive_months", {"goal": 3}),
    M("year-rounder", "seasons", "Year-rounder", "Hike in all 12 months, across any years", "gold",
      "calendar-full", "calendar_months", {"goal": 12}),
    M("back-to-back", "seasons", "Back-to-back", "Hike on two days in a row", "bronze", "two-days",
      "consecutive_days", note="Two different hikes in your journal."),
    M("double-header", "seasons", "Double header", "Hike two different trails on the same day", "bronze",
      "two-flags", "same_day"),
    M("canada-day", "seasons", "Canada Day", "Hike on July 1", "bronze", "maple", "on_date",
      {"month": 7, "day": 1}, hint="Celebrate the true north"),
    M("first-day-hike", "seasons", "First day hike", "Hike on January 1", "bronze", "sunrise", "on_date",
      {"month": 1, "day": 1}, hint="Start the year right"),
    # Journal
    M("storyteller", "journal", "Storyteller", "Write notes on {goal} hikes", "bronze", "quill", "notes",
      {"goal": 5}),
    M("field-notes", "journal", "Field notes", "Write notes on {goal} hikes", "silver", "notebook", "notes",
      {"goal": 25}),
    M("shutterbug", "journal", "Shutterbug", "Add photos to {goal} hikes", "bronze", "camera", "photos",
      {"goal": 5}),
    # Planning
    M("planner", "planning", "Planner", "Create your first trip plan", "bronze", "map", "plans", {"goal": 1}),
    M("permit-hunter", "planning", "Permit hunter", "Set your first campsite alert", "bronze", "bell",
      "alerts", {"goal": 1}),
    M("lucky-break", "planning", "Lucky break", "Have an alert find an open campsite", "silver", "clover",
      "alert_notified", hint="Patience pays off"),
    # Gear
    M("packed-and-ready", "gear", "Packed and ready", "Fill all 7 main slots in one gear setup", "silver",
      "backpack", "setup_core", {"slots": CORE_SLOT_CATEGORIES}),
    M("ultralight", "gear", "Ultralight", "Complete the Big Three in a setup with a base weight under {goal}",
      "gold", "feather", "base_weight", {"goal_kg": 9}, note="Every packed item needs a weight."),
)

# Every milestone is live (kept as a name for the callers).
ACTIVE = MILESTONES
BY_ID = {milestone.id: milestone for milestone in MILESTONES}
