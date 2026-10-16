"""The signed-in user's trip plans: a night-by-night itinerary on one trail,
an optional gear setup, and a booking status per night.

Dates are plain calendar dates throughout (night N = start_date + N), so a
night never moves for users in other time zones.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user_id
from app.backcountry.availability import AvailabilityChecker, ProviderError, RateLimited, group_of
from app.database import get_db
from app.models.availability import MAX_PARTY_SIZE, AvailabilityAlert
from app.models.backcountry import BackcountrySite
from app.models.setup import GearSetup
from app.models.trail import Trail
from app.models.trail_campground import TrailCampground
from app.models.trip_plan import MAX_PLAN_NIGHTS, MAX_PLANS_PER_USER, TripPlan, TripPlanNight
from app.routers.availability import (
    MAX_DAYS_AHEAD,
    availability_error,
    get_availability_fetch,
    get_today,
)
from app.routers.me_setups import SetupOut
from app.routers.me_setups import _load as load_setups
from app.routers.me_setups import _out as setup_out
from app.routers.trails import booking_links

router = APIRouter(prefix="/api/me/plans", tags=["my trip plans"])

# A user west of the server can still be on "yesterday" when they save, so a
# new plan may start one day before the server's today.
START_SLACK = timedelta(days=1)

Choice = Literal["campground", "undecided", "outside"]
NightStatus = Literal[
    "booked", "alert", "available", "full", "closed", "not_released", "unknown", "not_checked"
]


class NightIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: Choice = "undecided"
    site_id: UUID | None = None

    @model_validator(mode="after")
    def _site_matches_choice(self):
        if (self.choice == "campground") != (self.site_id is not None):
            raise ValueError("Pick a campground, or choose 'Not decided' or 'Outside Parks Canada'.")
        return self


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=80)
    start_date: date
    nights: int = Field(ge=1, le=MAX_PLAN_NIGHTS)
    party_size: int = Field(default=2, ge=1, le=MAX_PARTY_SIZE)
    setup_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)
    itinerary: list[NightIn] = Field(max_length=MAX_PLAN_NIGHTS)
    # An edit that would clear a "booked by me" night (dropped, moved to
    # another date or campground) is refused unless this is set.
    confirm_drop_booked: bool = False

    @field_validator("title", "notes", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _one_entry_per_night(self):
        if len(self.itinerary) != self.nights:
            raise ValueError("The itinerary needs one entry per night.")
        return self


class PlanCreate(PlanIn):
    trail_id: UUID


class NightBookedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booked_by_me: bool


class PlanTrailOut(BaseModel):
    id: UUID
    name: str
    region: str
    typical_duration_nights: int | None


class PlanSiteOut(BaseModel):
    id: UUID
    name: str
    site_code: str | None
    stop_name: str | None
    park: str | None
    kind: str
    max_group_size: int | None
    retired: bool
    # Parks Canada shows this campground's availability online.
    checkable: bool
    book_url: str | None


class PlanNightOut(BaseModel):
    night_index: int
    date: date
    choice: Choice
    site: PlanSiteOut | None
    booked_by_me: bool
    # Worked out on read: booked > alert > last check > not checked. Null
    # for nights without a campground that aren't marked booked.
    status: NightStatus | None
    alert_id: UUID | None
    last_status: str | None
    last_checked_at: datetime | None


class PlanPermitOut(BaseModel):
    name: str
    book_url: str | None


class PlanSummaryOut(BaseModel):
    id: UUID
    title: str | None
    trail: PlanTrailOut
    start_date: date
    end_date: date  # the morning you walk out
    last_night: date
    nights: int
    party_size: int
    booked_nights: int
    updated_at: datetime


class PlanOut(PlanSummaryOut):
    notes: str | None
    setup_id: UUID | None
    setup: SetupOut | None
    itinerary: list[PlanNightOut]
    permits: list[PlanPermitOut]
    created_at: datetime


def _query(user_id: UUID):
    return (
        select(TripPlan)
        .where(TripPlan.user_id == user_id)
        .options(
            selectinload(TripPlan.trail),
            selectinload(TripPlan.plan_nights)
            .selectinload(TripPlanNight.site)
            .selectinload(BackcountrySite.park),
        )
    )


def _get(db: Session, user_id: UUID, plan_id: UUID) -> TripPlan:
    # Someone else's plan is indistinguishable from a missing one.
    plan = db.scalar(_query(user_id).where(TripPlan.id == plan_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="Trip plan not found")
    return plan


def _trail_out(trail: Trail) -> PlanTrailOut:
    return PlanTrailOut(
        id=trail.id, name=trail.name, region=trail.region,
        typical_duration_nights=trail.typical_duration_nights,
    )


def _summary(plan: TripPlan) -> PlanSummaryOut:
    return PlanSummaryOut(
        id=plan.id,
        title=plan.title,
        trail=_trail_out(plan.trail),
        start_date=plan.start_date,
        end_date=plan.start_date + timedelta(days=plan.nights),
        last_night=plan.start_date + timedelta(days=plan.nights - 1),
        nights=plan.nights,
        party_size=plan.party_size,
        booked_nights=sum(1 for night in plan.plan_nights if night.booked_by_me),
        updated_at=plan.updated_at,
    )


def _book_url(site: BackcountrySite) -> str | None:
    links = booking_links([SimpleNamespace(site=site)])
    return links[0].url if links else None


def _trail_links(db: Session, trail_id: UUID) -> list[TrailCampground]:
    return db.scalars(
        select(TrailCampground)
        .join(BackcountrySite, TrailCampground.site_id == BackcountrySite.id)
        .where(TrailCampground.trail_id == trail_id, BackcountrySite.is_publicly_listed.is_(True))
        .options(selectinload(TrailCampground.site).selectinload(BackcountrySite.park))
    ).all()


def _out(db: Session, user_id: UUID, plan: TripPlan) -> PlanOut:
    links = {link.site_id: link for link in _trail_links(db, plan.trail_id)}

    site_ids = {night.site_id for night in plan.plan_nights if night.site_id}
    alerts = (
        db.scalars(
            select(AvailabilityAlert).where(
                AvailabilityAlert.user_id == user_id,
                AvailabilityAlert.status == "active",
                AvailabilityAlert.site_id.in_(site_ids),
            )
        ).all()
        if site_ids
        else []
    )

    def covering_alert(site_id, night_date):
        for alert in alerts:
            if alert.site_id == site_id and alert.start_date <= night_date < alert.start_date + timedelta(days=alert.nights):
                return alert.id
        return None

    itinerary = []
    for night in plan.plan_nights:
        night_date = plan.start_date + timedelta(days=night.night_index)
        site_out = None
        alert_id = None
        if night.site is not None:
            site = night.site
            link = links.get(site.id)
            site_out = PlanSiteOut(
                id=site.id,
                name=site.name,
                site_code=site.site_code,
                stop_name=link.stop_name if link else None,
                park=site.park.name if site.park else None,
                kind=site.kind,
                max_group_size=site.max_group_size,
                retired=site.retired_at is not None,
                checkable=site.retired_at is None and group_of(site) is not None,
                book_url=_book_url(site),
            )
            alert_id = covering_alert(site.id, night_date)

        if night.booked_by_me:
            night_status = "booked"
        elif site_out is None:
            night_status = None
        elif alert_id is not None:
            night_status = "alert"
        elif night.last_status:
            night_status = night.last_status
        else:
            night_status = "not_checked"

        itinerary.append(
            PlanNightOut(
                night_index=night.night_index,
                date=night_date,
                choice=night.choice,
                site=site_out,
                booked_by_me=night.booked_by_me,
                status=night_status,
                alert_id=alert_id,
                last_status=night.last_status,
                last_checked_at=night.last_checked_at,
            )
        )

    permits = [
        PlanPermitOut(name=link.site.name, book_url=_book_url(link.site))
        for link in sorted(links.values(), key=lambda l: l.route_order)
        if link.site.kind == "trail_permit" and link.site.retired_at is None
    ]

    setup = None
    if plan.setup_id is not None:
        found = load_setups(db, user_id, plan.setup_id)
        setup = setup_out(db, user_id, found[0]) if found else None

    return PlanOut(
        **_summary(plan).model_dump(),
        notes=plan.notes,
        setup_id=plan.setup_id,
        setup=setup,
        itinerary=itinerary,
        permits=permits,
        created_at=plan.created_at,
    )


def _validate(
    db: Session, user_id: UUID, trail_id: UUID, payload: PlanIn, existing: TripPlan | None, today: date
) -> None:
    if payload.start_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=422, detail="That's too far ahead to plan.")

    if payload.setup_id is not None and db.scalar(
        select(GearSetup.id).where(GearSetup.id == payload.setup_id, GearSetup.user_id == user_id)
    ) is None:
        raise HTTPException(status_code=422, detail="That gear setup isn't one of yours.")

    links = {link.site_id: link for link in _trail_links(db, trail_id)}
    kept = {
        (night.night_index, night.site_id) for night in (existing.plan_nights if existing else []) if night.site_id
    }
    for index, night in enumerate(payload.itinerary):
        if night.site_id is None:
            continue
        link = links.get(night.site_id)
        if link is None or link.site.kind == "trail_permit":
            raise HTTPException(status_code=422, detail=f"Night {index + 1}: that campground isn't on this trail.")
        # A campground that has since been retired can stay where it was,
        # but can't be newly picked.
        if link.site.retired_at is not None and (index, night.site_id) not in kept:
            raise HTTPException(
                status_code=422, detail=f"Night {index + 1}: Parks Canada no longer lists that campground."
            )


def _apply(plan: TripPlan, payload: PlanIn) -> None:
    """Write the payload onto the plan. A night keeps its "booked by me" flag
    only if its date and campground are unchanged, and its last check only if
    the party size is unchanged too."""
    old_start = plan.start_date
    old_party = plan.party_size
    old_nights = {night.night_index: night for night in plan.plan_nights}

    plan.title = payload.title
    plan.start_date = payload.start_date
    plan.nights = payload.nights
    plan.party_size = payload.party_size
    plan.setup_id = payload.setup_id
    plan.notes = payload.notes

    same_dates = old_start == payload.start_date
    kept_nights = []
    for index, wanted in enumerate(payload.itinerary):
        night = old_nights.pop(index, None)
        unchanged = (
            night is not None and same_dates and night.choice == wanted.choice and night.site_id == wanted.site_id
        )
        if night is None:
            night = TripPlanNight(night_index=index)
        if not unchanged:
            night.booked_by_me = False
        if not unchanged or old_party != payload.party_size:
            night.last_status = None
            night.last_checked_at = None
        night.choice = wanted.choice
        night.site_id = wanted.site_id
        kept_nights.append(night)
    plan.plan_nights = kept_nights


def _refuse_lost_bookings(plan: TripPlan, payload: PlanIn) -> None:
    """Dry-run check before anything is written."""
    if payload.confirm_drop_booked:
        return
    same_dates = plan.start_date == payload.start_date
    lost = []
    for night in plan.plan_nights:
        if not night.booked_by_me:
            continue
        wanted = payload.itinerary[night.night_index] if night.night_index < len(payload.itinerary) else None
        if wanted is None or not same_dates or wanted.choice != night.choice or wanted.site_id != night.site_id:
            lost.append(night)
    if lost:
        names = ", ".join(
            f"night {n.night_index + 1} ({(plan.start_date + timedelta(days=n.night_index)).isoformat()})" for n in lost
        )
        raise HTTPException(
            status_code=409,
            detail=f"This change would unmark {names} as booked. Confirm to continue.",
        )


@router.get("", response_model=list[PlanSummaryOut])
def list_plans(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Soonest first. The client splits upcoming from past using its own
    calendar date, so a trip turns "past" at the user's midnight."""
    plans = db.scalars(_query(user_id).order_by(TripPlan.start_date, TripPlan.created_at)).all()
    return [_summary(plan) for plan in plans]


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    if db.get(Trail, payload.trail_id) is None:
        raise HTTPException(status_code=422, detail="That trail doesn't exist.")
    if payload.start_date < today - START_SLACK:
        raise HTTPException(status_code=422, detail="Pick a first night from today onwards.")
    count = db.scalar(select(func.count()).select_from(TripPlan).where(TripPlan.user_id == user_id))
    if (count or 0) >= MAX_PLANS_PER_USER:
        raise HTTPException(
            status_code=422, detail=f"You can have up to {MAX_PLANS_PER_USER} trip plans. Delete one to add another."
        )
    _validate(db, user_id, payload.trail_id, payload, None, today)

    plan = TripPlan(user_id=user_id, trail_id=payload.trail_id, start_date=payload.start_date,
                    nights=payload.nights, party_size=payload.party_size)
    plan.plan_nights = []
    _apply(plan, payload)
    db.add(plan)
    db.commit()
    return _out(db, user_id, _get(db, user_id, plan.id))


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return _out(db, user_id, _get(db, user_id, plan_id))


@router.put("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: UUID,
    payload: PlanIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Replace the plan's details and itinerary. Past dates are allowed here,
    so a finished trip can still be tidied up."""
    plan = _get(db, user_id, plan_id)
    _validate(db, user_id, plan.trail_id, payload, plan, today)
    _refuse_lost_bookings(plan, payload)
    _apply(plan, payload)
    plan.updated_at = func.now()
    db.commit()
    db.expire_all()
    return _out(db, user_id, _get(db, user_id, plan_id))


@router.put("/{plan_id}/nights/{night_index}", response_model=PlanOut)
def set_night_booked(
    plan_id: UUID,
    night_index: int,
    payload: NightBookedIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Mark one night as booked (or not). Trekly never books: this is the
    user's own record."""
    plan = _get(db, user_id, plan_id)
    night = next((n for n in plan.plan_nights if n.night_index == night_index), None)
    if night is None:
        raise HTTPException(status_code=404, detail="That night isn't in this plan.")
    if payload.booked_by_me and night.choice == "undecided":
        raise HTTPException(status_code=422, detail="Choose where you're staying before marking the night booked.")
    night.booked_by_me = payload.booked_by_me
    db.commit()
    db.expire_all()
    return _out(db, user_id, _get(db, user_id, plan_id))


@router.post("/{plan_id}/check", response_model=PlanOut)
def check_plan(
    plan_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    fetch=Depends(get_availability_fetch),
    today: date = Depends(get_today),
):
    """Check each upcoming night's campground on Parks Canada (through the
    shared cache and request budget) and remember the answer per night."""
    plan = _get(db, user_id, plan_id)
    first = max(plan.start_date, today)
    last = plan.start_date + timedelta(days=plan.nights - 1)
    if first > last:
        raise HTTPException(status_code=422, detail="This trip is over, so there's nothing left to check.")
    if first > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=422, detail="That's too far ahead to check.")

    to_check = [
        night for night in plan.plan_nights
        if night.site is not None and night.site.retired_at is None and group_of(night.site) is not None
        and plan.start_date + timedelta(days=night.night_index) >= first
    ]
    if to_check:
        sites = {night.site.id: night.site for night in to_check}
        span = (last - first).days + 1
        try:
            result = AvailabilityChecker(db, fetch).check(sites.values(), first, span, plan.party_size)
        except (RateLimited, ProviderError) as error:
            raise availability_error(error) from error
        for night in to_check:
            found = result.sites.get(night.site_id)
            offset = (plan.start_date + timedelta(days=night.night_index) - first).days
            if found is None or offset >= len(found.statuses):
                continue
            night.last_status = found.statuses[offset]
            night.last_checked_at = result.fetched_at
        db.commit()
        db.expire_all()
    return _out(db, user_id, _get(db, user_id, plan_id))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    db.delete(_get(db, user_id, plan_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
