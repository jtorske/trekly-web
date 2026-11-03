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
"""

from dataclasses import replace
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.milestones import Facts, Result, check
from app.milestones_config import Milestone
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
        upto = replace(
            facts,
            hikes=[hike for hike, on in zip(facts.hikes, hike_dates) if on and on <= day],
            plans=sum(1 for d in plan_dates if d <= day),
            alerts=sum(1 for d in alert_dates if d <= day),
            alert_notified=any(d <= day for d in notified_dates),
            setups=[s for s, d in zip(facts.setups, facts.setup_dates) if d <= day],
            base_weights_kg=[w for w, d in zip(facts.base_weights_kg, facts.base_weight_dates) if d <= day],
        )
        for milestone in [m for m in pending if check(m, upto).earned]:
            found[milestone.id] = day
            pending.remove(milestone)
        if not pending:
            break
    return found


def gather_earned_dates(db: Session, user_id: UUID, facts: Facts, results: list[tuple[Milestone, Result]]) -> dict[str, date]:
    """earned_dates with the plan and alert dates read for one user."""
    if not any(result.earned for _, result in results):
        return {}
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
    return earned_dates(
        facts,
        results,
        plan_dates=plan_dates,
        alert_dates=[created_at.date() for created_at, *_ in alerts],
        notified_dates=notified,
    )
