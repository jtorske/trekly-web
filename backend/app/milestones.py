"""Trail Journal milestones: which are earned, and how far along the rest are.

The definitions are in app/milestones_config.py; this module holds the rule
kinds they name. Everything is worked out from existing data on each
request (nothing is stored), so the browser can never claim a milestone, and
deleting a hike or a plan takes away what it earned.

The facts come from gather(); tests build Facts directly.

Data rules:
- A trip's nights are its trail's typical nights. Its days run from the hike
  date through the nights after it, so a trip that crosses into a new month
  or season counts for both.
- Distance and elevation count only trails where they're known.
- The catalogue's retired trails still count as hikes, but a park's "every
  trail" is its active trails only.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.catalog.presenters import effective_weight
from app.milestones_config import ACTIVE, CATEGORIES, CORE_SLOT_CATEGORIES, TIER_POINTS, WORN_BY_DEFAULT, Milestone
from app.models.availability import AvailabilityAlert
from app.models.hike_log import HikeLog
from app.models.setup import GearSetup, GearSetupItem
from app.models.trail import Trail
from app.models.trip_plan import TripPlan
from app.models.user_gear import UserGearItem


@dataclass(frozen=True)
class Hike:
    trail: Trail
    hiked_on: date | None = None
    note: bool = False
    photo: bool = False

    @property
    def nights(self) -> int:
        return self.trail.typical_duration_nights or 0

    def days(self) -> list[date]:
        """Every day of the trip, from the hike date through its last night."""
        if self.hiked_on is None:
            return []
        return [self.hiked_on + timedelta(days=n) for n in range(self.nights + 1)]


@dataclass
class Facts:
    hikes: list[Hike] = field(default_factory=list)
    plans: int = 0
    alerts: int = 0
    alert_notified: bool = False
    # Per setup, the catalogue subcategory slugs of its items.
    setups: list[set[str]] = field(default_factory=list)
    # Base weight in kg of each complete setup (all core slots filled, every
    # packed item weighed); see setup_base_weight_kg.
    base_weights_kg: list[float] = field(default_factory=list)
    # Active catalogue trails by region, for "every trail in a park".
    region_trails: dict[str, set[UUID]] = field(default_factory=dict)

    @property
    def trails(self) -> list[Trail]:
        return [hike.trail for hike in self.hikes]


@dataclass(frozen=True)
class Result:
    earned: bool
    # Progress towards the goal, where a count makes sense (else None).
    current: float | None = None
    goal: float | None = None
    # "km" or "m" when the numbers are a distance or an elevation.
    unit: str | None = None
    # Which park the progress is for (Park completionist).
    near: str | None = None


def _count(current: float, goal: float, unit: str | None = None) -> Result:
    return Result(earned=current >= goal, current=current, goal=goal, unit=unit)


# ------------------------------------------------------------ rule kinds
# Each takes the facts and the milestone's params and returns a Result.


def hikes(facts: Facts, goal: int) -> Result:
    return _count(len(facts.hikes), goal)


def repeat_trail(facts: Facts) -> Result:
    counts = Counter(hike.trail.id for hike in facts.hikes)
    return Result(earned=any(n >= 2 for n in counts.values()))


def trip_nights(facts: Facts, nights: int) -> Result:
    return Result(earned=any(hike.nights >= nights for hike in facts.hikes))


def total_nights(facts: Facts, goal: int) -> Result:
    return _count(sum(hike.nights for hike in facts.hikes), goal)


def distance(facts: Facts, goal: float) -> Result:
    km = sum(float(trail.distance_km) for trail in facts.trails if trail.distance_km is not None)
    return _count(round(km, 1), goal, "km")


def climb_one(facts: Facts, goal: int) -> Result:
    return Result(earned=any((trail.elevation_gain_m or 0) >= goal for trail in facts.trails))


def high_point(facts: Facts, goal: int) -> Result:
    return Result(earned=any((trail.max_elevation_m or 0) >= goal for trail in facts.trails))


def total_gain(facts: Facts, goal: int) -> Result:
    return _count(sum(trail.elevation_gain_m or 0 for trail in facts.trails), goal, "m")


def regions(facts: Facts, goal: int) -> Result:
    return _count(len({trail.region for trail in facts.trails}), goal)


def parks_all(facts: Facts, parks: Iterable[str]) -> Result:
    parks = set(parks)
    return _count(len(parks & {trail.park_name for trail in facts.trails}), len(parks))


def _provinces(facts: Facts) -> set[str]:
    return {trail.province_code for trail in facts.trails if trail.country_code == "CA" and trail.province_code}


def provinces(facts: Facts, goal: int) -> Result:
    return _count(len(_provinces(facts)), goal)


def any_province(facts: Facts, codes: Iterable[str]) -> Result:
    return Result(earned=bool(_provinces(facts) & set(codes)))


def every_group(facts: Facts, groups: Iterable[Iterable[str]]) -> Result:
    """A province from each group (e.g. BC, and any Atlantic province)."""
    groups = [set(group) for group in groups]
    hiked = _provinces(facts)
    return _count(sum(1 for group in groups if group & hiked), len(groups))


def park_complete(facts: Facts, min: int) -> Result:  # noqa: A002  (named for the config)
    hiked = {trail.id for trail in facts.trails}
    best: tuple[float, int, int, str] | None = None
    for region, ids in facts.region_trails.items():
        if len(ids) < min:
            continue
        done = len(ids & hiked)
        if done and (best is None or (done / len(ids), done) > (best[0], best[1])):
            best = (done / len(ids), done, len(ids), region)
    if best is None:
        return Result(earned=False)
    _, done, total, region = best
    return Result(earned=done == total, current=done, goal=total, near=region)


def difficulties(facts: Facts, levels: Iterable[str]) -> Result:
    levels = set(levels)
    return _count(len(levels & {trail.terrain_difficulty for trail in facts.trails}), len(levels))


def difficulty(facts: Facts, level: str, goal: int) -> Result:
    return _count(sum(1 for trail in facts.trails if trail.terrain_difficulty == level), goal)


def tagged_in_window(facts: Facts, tag: str, start: tuple[int, int], end: tuple[int, int]) -> Result:
    """A trail with `tag` hiked on a day between start and end (month, day), any year."""
    return Result(
        earned=any(
            tag in (hike.trail.tags or ()) and any(start <= (day.month, day.day) <= end for day in hike.days())
            for hike in facts.hikes
        )
    )


def _months(facts: Facts) -> set[tuple[int, int]]:
    return {(day.year, day.month) for hike in facts.hikes for day in hike.days()}


def in_months(facts: Facts, months: Iterable[int]) -> Result:
    months = set(months)
    return Result(earned=any(month in months for _, month in _months(facts)))


def seasons(facts: Facts, seasons: dict[str, Iterable[int]]) -> Result:
    hiked = {month for _, month in _months(facts)}
    return _count(sum(1 for months in seasons.values() if hiked & set(months)), len(seasons))


def consecutive_months(facts: Facts, goal: int) -> Result:
    """The longest run of calendar months in a row with a hike (across years)."""
    indexes = sorted(year * 12 + month - 1 for year, month in _months(facts))
    best = run = 0
    for i, index in enumerate(indexes):
        run = run + 1 if i and index == indexes[i - 1] + 1 else 1
        best = max(best, run)
    return _count(best, goal)


def notes(facts: Facts, goal: int) -> Result:
    return _count(sum(1 for hike in facts.hikes if hike.note), goal)


def photos(facts: Facts, goal: int) -> Result:
    return _count(sum(1 for hike in facts.hikes if hike.photo), goal)


def plans(facts: Facts, goal: int) -> Result:
    return _count(facts.plans, goal)


def alerts(facts: Facts, goal: int) -> Result:
    return _count(facts.alerts, goal)


def alert_notified(facts: Facts) -> Result:
    return Result(earned=facts.alert_notified)


def setup_core(facts: Facts, slots: dict[str, Iterable[str]]) -> Result:
    """The fullest setup: how many of the core slots its items fill."""
    best = max(
        (sum(1 for categories in slots.values() if setup & set(categories)) for setup in facts.setups), default=0
    )
    return _count(best, len(slots))


def base_weight(facts: Facts, goal_kg: float) -> Result:
    return Result(earned=any(weight < goal_kg for weight in facts.base_weights_kg))


def trail(facts: Facts, name: str, province: str) -> Result:
    return Result(earned=any(t.name == name and t.province_code == province for t in facts.trails))


RULES: dict[str, Callable[..., Result]] = {
    rule.__name__: rule
    for rule in (
        hikes, repeat_trail, trip_nights, total_nights, distance, climb_one, high_point, total_gain, regions,
        parks_all, provinces, any_province, every_group, park_complete, difficulties, difficulty,
        tagged_in_window, in_months, seasons, consecutive_months, notes, photos, plans, alerts, alert_notified,
        setup_core, base_weight, trail,
    )
}


# ------------------------------------------------------------ evaluation


def check(milestone: Milestone, facts: Facts) -> Result:
    return RULES[milestone.rule](facts, **milestone.params)


def evaluate(facts: Facts, milestones: Iterable[Milestone] = ACTIVE) -> list[tuple[Milestone, Result]]:
    return [(milestone, check(milestone, facts)) for milestone in milestones]


def earned_ids(facts: Facts) -> set[str]:
    return {milestone.id for milestone, result in evaluate(facts) if result.earned}


def milestone_points(facts: Facts) -> int:
    return sum(TIER_POINTS[milestone.tier] for milestone, result in evaluate(facts) if result.earned)


def goal_of(milestone: Milestone) -> float | int | None:
    """The number "{goal}" stands for in the detail."""
    params = milestone.params
    return params.get("goal", params.get("min", params.get("goal_kg")))


CATEGORY_TITLES = dict(CATEGORIES)


# ------------------------------------------------------------ what the API sends


class MilestoneBadgeOut(BaseModel):
    """An earned milestone as a badge: enough to draw and name it."""

    id: str
    category: str
    title: str
    tier: str
    icon: str


class ProgressOut(BaseModel):
    current: float
    goal: float
    unit: str | None = None
    near: str | None = None


class MilestoneOut(BaseModel):
    # An unearned secret has no id, title, detail or tier: only "???" and its hint.
    id: str | None
    category: str
    title: str
    detail: str
    # The number "{goal}" in detail stands for, and its unit ("km", "m", "kg").
    goal: float | None = None
    unit: str | None = None
    tier: str | None
    icon: str
    secret: bool
    earned: bool
    progress: ProgressOut | None = None


class CategoryOut(BaseModel):
    id: str
    title: str


def badge_out(milestone: Milestone) -> MilestoneBadgeOut:
    return MilestoneBadgeOut(
        id=milestone.id, category=milestone.category, title=milestone.title, tier=milestone.tier, icon=milestone.icon
    )


GOAL_UNITS = {"distance": "km", "climb_one": "m", "high_point": "m", "total_gain": "m", "base_weight": "kg"}


def milestone_out(milestone: Milestone, result: Result) -> MilestoneOut:
    if milestone.secret and not result.earned:
        return MilestoneOut(
            id=None, category=milestone.category, title="???", detail=milestone.hint or "", tier=None,
            icon="secret", secret=True, earned=False,
        )
    progress = None
    # Progress only means something partway: not at zero, and not once earned.
    if not result.earned and result.goal and result.current:
        progress = ProgressOut(current=result.current, goal=result.goal, unit=result.unit, near=result.near)
    return MilestoneOut(
        id=milestone.id, category=milestone.category, title=milestone.title, detail=milestone.detail,
        goal=goal_of(milestone), unit=GOAL_UNITS.get(milestone.rule), tier=milestone.tier, icon=milestone.icon,
        secret=milestone.secret, earned=result.earned, progress=progress,
    )


# ------------------------------------------------------------ facts


def setup_base_weight_kg(items: Iterable[UserGearItem]) -> float | None:
    """A setup's base weight, as the gear page counts it (frontend app/gear/baseWeight.ts):
    packed items only (worn and consumable ones are left out; footwear is worn
    unless the owner says otherwise), each weight times its quantity. None
    while a packed item has no weight."""
    grams = 0.0
    for item in items:
        slug = item.category.slug if item.category is not None else None
        carry = item.carry or ("worn" if slug in WORN_BY_DEFAULT else "packed")
        if carry != "packed":
            continue
        weight, _ = effective_weight(item)
        if weight is None:
            return None
        grams += float(weight) * item.quantity
    return grams / 1000


def gather(db: Session, user_id: UUID) -> Facts:
    """Everything the rules read, for one user."""
    logs = db.scalars(select(HikeLog).where(HikeLog.user_id == user_id).options(joinedload(HikeLog.trail))).all()
    facts = Facts(
        hikes=[Hike(log.trail, log.hiked_on, bool(log.note), bool(log.photo_path)) for log in logs],
        plans=db.scalar(select(func.count()).select_from(TripPlan).where(TripPlan.user_id == user_id)) or 0,
        alerts=db.scalar(
            select(func.count()).select_from(AvailabilityAlert).where(AvailabilityAlert.user_id == user_id)
        ) or 0,
        alert_notified=db.scalar(
            select(func.count()).select_from(AvailabilityAlert).where(
                AvailabilityAlert.user_id == user_id,
                or_(AvailabilityAlert.notified_at.is_not(None), AvailabilityAlert.status == "notified"),
            )
        ) > 0,
    )
    setups = db.scalars(
        select(GearSetup)
        .where(GearSetup.user_id == user_id)
        .options(
            joinedload(GearSetup.entries).joinedload(GearSetupItem.gear_item).options(
                joinedload(UserGearItem.category),
                joinedload(UserGearItem.product),
                joinedload(UserGearItem.variant),
            )
        )
    ).unique().all()
    for setup in setups:
        items = [entry.gear_item for entry in setup.entries]
        categories = {item.category.slug for item in items if item.category is not None}
        facts.setups.append(categories)
        weight = setup_base_weight_kg(items)
        if weight is not None and setup_core(facts=Facts(setups=[categories]), slots=CORE_SLOT_CATEGORIES).earned:
            facts.base_weights_kg.append(weight)
    if logs:
        for trail_id, region in db.execute(select(Trail.id, Trail.region).where(Trail.retired_at.is_(None))):
            facts.region_trails.setdefault(region, set()).add(trail_id)
    return facts
