"""When each earned milestone was first earned.

Nothing about earning is stored (app/milestones.py works it all out on each
request), so the date is found by replaying the user's history: every dated
fact (a hike, a trip plan, an alert, a setup) as it stood at the end of each
day, in order, until the milestone holds.

The dates come from:
- a hike: its hike date, or the day it was logged when it has none;
- a trip plan or an alert: the day it was made; an alert's notice: the day it
  was sent;
- a gear setup: its last change, or the last change to one of its items. No
  setup history is kept, so that's the earliest day it's known to have
  looked as it does now.

Days are calendar days: hike dates as the hiker picked them, timestamps in UTC.

A milestone that needed undated hikes ("before Trekly") added on the day it
was earned is marked as earned from past hikes (past_hike_milestones): the
journal shows "Earned when you joined" for those from onboarding.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.milestones import Facts, Result, check, evaluate, gather
from app.milestones_config import ACTIVE, Milestone
from app.models.availability import AvailabilityAlert
from app.models.trip_plan import TripPlan


def earned_dates(
    facts: Facts,
    results: list[tuple[Milestone, Result]],
    *,
    plan_dates: list[date],
    alert_dates: list[date],
    notified_dates: list[date],
) -> dict[str, date]:
    """The first day each earned milestone held, by id. One whose day can't be
    found (it shouldn't happen) is left out."""
    pending = [milestone for milestone, result in results if result.earned]
    if not pending:
        return {}
    hike_dates = [hike.hiked_on or hike.logged_on for hike in facts.hikes]
    days = sorted(
        {d for d in [*hike_dates, *plan_dates, *alert_dates, *notified_dates, *facts.setup_dates, *facts.base_weight_dates] if d}
    )
    found: dict[str, date] = {}
    for day in days:
        upto = facts_on(facts, day, plan_dates=plan_dates, alert_dates=alert_dates, notified_dates=notified_dates)
        for milestone in [m for m in pending if check(m, upto).earned]:
            found[milestone.id] = day
            pending.remove(milestone)
        if not pending:
            break
    return found


def facts_on(
    facts: Facts,
    day: date,
    *,
    plan_dates: list[date],
    alert_dates: list[date],
    notified_dates: list[date],
    without_past_hikes_from: date | None = None,
) -> Facts:
    """The facts as they stood at the end of `day`. With
    `without_past_hikes_from`, undated hikes logged on or after that day are
    left out."""

    def keep(hike) -> bool:
        on = hike.hiked_on or hike.logged_on
        if not on or on > day:
            return False
        return not (
            without_past_hikes_from and hike.hiked_on is None and hike.logged_on and hike.logged_on >= without_past_hikes_from
        )

    return replace(
        facts,
        hikes=[hike for hike in facts.hikes if keep(hike)],
        plans=sum(1 for d in plan_dates if d <= day),
        alerts=sum(1 for d in alert_dates if d <= day),
        alert_notified=any(d <= day for d in notified_dates),
        setups=[s for s, d in zip(facts.setups, facts.setup_dates) if d <= day],
        base_weights_kg=[w for w, d in zip(facts.base_weights_kg, facts.base_weight_dates) if d <= day],
    )


def past_hike_milestones(
    facts: Facts,
    dates: dict[str, date],
    *,
    plan_dates: list[date],
    alert_dates: list[date],
    notified_dates: list[date],
) -> set[str]:
    """The earned milestones that only held on their day thanks to undated
    hikes added that day."""
    by_id = {milestone.id: milestone for milestone in ACTIVE}
    found = set()
    for milestone_id, day in dates.items():
        milestone = by_id.get(milestone_id)
        if milestone is None:
            continue
        without = facts_on(
            facts, day, plan_dates=plan_dates, alert_dates=alert_dates, notified_dates=notified_dates,
            without_past_hikes_from=day,
        )
        if not check(milestone, without).earned:
            found.add(milestone_id)
    return found


@dataclass(frozen=True)
class EarnedDates:
    dates: dict[str, date]
    # Earned on the strength of undated hikes added that day.
    from_past_hikes: set[str]


def gather_earned_dates(db: Session, user_id: UUID, facts: Facts, results: list[tuple[Milestone, Result]]) -> EarnedDates:
    """earned_dates (and past_hike_milestones) with the plan and alert dates read for one user."""
    if not any(result.earned for _, result in results):
        return EarnedDates({}, set())
    plan_dates = [d.date() for d in db.scalars(select(TripPlan.created_at).where(TripPlan.user_id == user_id))]
    alerts = db.execute(
        select(AvailabilityAlert.created_at, AvailabilityAlert.notified_at, AvailabilityAlert.status, AvailabilityAlert.updated_at)
        .where(AvailabilityAlert.user_id == user_id)
    ).all()
    notified = [
        (notified_at or updated_at).date()
        for _, notified_at, status, updated_at in alerts
        if notified_at is not None or status == "notified"
    ]
    others = {
        "plan_dates": plan_dates,
        "alert_dates": [created_at.date() for created_at, *_ in alerts],
        "notified_dates": notified,
    }
    dates = earned_dates(facts, results, **others)
    return EarnedDates(dates, past_hike_milestones(facts, dates, **others))


class BadgeDates:
    """When owners earned their badges, for the badges' cards on someone
    else's screen (Activity posts, featured badges): the same days their own
    journal shows. Worked out once per owner, since a feed page shows a few
    people. A badge earned from undated past hikes has no day."""

    def __init__(self, db: Session):
        self.db = db
        self._by_user: dict[UUID, EarnedDates] = {}

    def __call__(self, user_id: UUID, milestone_id: str) -> tuple[date | None, Literal["past_hikes"] | None]:
        if user_id not in self._by_user:
            facts = gather(self.db, user_id)
            self._by_user[user_id] = gather_earned_dates(self.db, user_id, facts, evaluate(facts))
        dates = self._by_user[user_id]
        if milestone_id in dates.from_past_hikes:
            return None, "past_hikes"
        return dates.dates.get(milestone_id), None
