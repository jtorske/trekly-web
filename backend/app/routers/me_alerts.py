"""The signed-in user's "alert me when this opens up" alerts.

An alert watches one campground for one stay (start date + nights + party
size). The poller (scripts/poll_alerts.py) emails once when every night of the
stay is available, then marks the alert 'notified'; the user can re-arm it.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, get_current_user, get_current_user_id
from app.backcountry.availability import group_of, summarize
from app.database import get_db
from app.models.availability import (
    MAX_ACTIVE_ALERTS_PER_USER,
    MAX_ALERT_NIGHTS,
    MAX_PARTY_SIZE,
    AvailabilityAlert,
)
from app.models.backcountry import BackcountrySite
from app.models.trail_campground import TrailCampground
from app.routers.availability import get_today, validate_stay

router = APIRouter(prefix="/api/me/alerts", tags=["my alerts"])


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    trail_id: UUID | None = None
    start_date: date
    nights: int = Field(ge=1, le=MAX_ALERT_NIGHTS)
    party_size: int = Field(default=2, ge=1, le=MAX_PARTY_SIZE)


class AlertTrailOut(BaseModel):
    id: UUID
    name: str


class AlertOut(BaseModel):
    id: UUID
    site_id: UUID
    campground: str
    site_code: str | None
    park: str | None
    trail: AlertTrailOut | None
    start_date: date
    end_date: date  # morning you leave
    nights: int
    party_size: int
    status: Literal["active", "notified", "cancelled", "expired"]
    # Summary of the last check: available / partial / full / closed / not_released / unknown.
    last_summary: str | None
    last_checked_at: datetime | None
    notified_at: datetime | None
    created_at: datetime


def _out(alert: AvailabilityAlert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        site_id=alert.site_id,
        campground=alert.site.name,
        site_code=alert.site.site_code,
        park=alert.site.park.name if alert.site.park else None,
        trail=AlertTrailOut(id=alert.trail.id, name=alert.trail.name) if alert.trail else None,
        start_date=alert.start_date,
        end_date=alert.start_date + timedelta(days=alert.nights),
        nights=alert.nights,
        party_size=alert.party_size,
        status=alert.status,
        last_summary=summarize(alert.last_result) if alert.last_result else None,
        last_checked_at=alert.last_checked_at,
        notified_at=alert.notified_at,
        created_at=alert.created_at,
    )


def _query(user_id: UUID):
    return (
        select(AvailabilityAlert)
        .where(AvailabilityAlert.user_id == user_id)
        .options(
            selectinload(AvailabilityAlert.site).selectinload(BackcountrySite.park),
            selectinload(AvailabilityAlert.trail),
        )
    )


DUPLICATE_ALERT = "You already have an alert for this campground and these dates."


def _lock_user_alerts(db: Session, user_id: UUID) -> None:
    """Serialize alert writes per user until the transaction ends.

    Without it, simultaneous requests all pass the duplicate check and the
    active-alert cap before any of them commits. The partial unique index
    still backs up the duplicate rule; this is what keeps the cap honest.
    SQLite (tests) runs one request at a time, so it needs no lock.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"availability_alerts:{user_id}"},
        )


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_ALERT) from error


def _get(db: Session, user_id: UUID, alert_id: UUID) -> AvailabilityAlert:
    # Someone else's alert is indistinguishable from a missing one.
    alert = db.scalar(_query(user_id).where(AvailabilityAlert.id == alert_id))
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


STATUS_ORDER = {"active": 0, "notified": 1, "expired": 2, "cancelled": 3}


@router.get("", response_model=list[AlertOut])
def list_alerts(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    alerts = db.scalars(_query(user_id)).all()
    alerts.sort(key=lambda a: (STATUS_ORDER.get(a.status, 9), a.start_date))
    return [_out(alert) for alert in alerts]


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    if not user.email:
        raise HTTPException(status_code=422, detail="Your account needs an email address to get alerts.")
    validate_stay(payload.start_date, payload.nights, today)

    site = db.get(BackcountrySite, payload.site_id)
    if site is None or not site.is_publicly_listed or site.retired_at is not None:
        raise HTTPException(status_code=422, detail="That campground isn't available for alerts.")
    if group_of(site) is None:
        raise HTTPException(status_code=422, detail="Parks Canada doesn't show availability for that campground online.")
    if payload.trail_id is not None and db.get(TrailCampground, (payload.trail_id, payload.site_id)) is None:
        raise HTTPException(status_code=422, detail="That campground isn't on this trail.")

    _lock_user_alerts(db, user.id)
    active = AvailabilityAlert.status == "active"
    duplicate = db.scalar(
        select(AvailabilityAlert.id).where(
            AvailabilityAlert.user_id == user.id, active,
            AvailabilityAlert.site_id == payload.site_id,
            AvailabilityAlert.start_date == payload.start_date,
            AvailabilityAlert.nights == payload.nights,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=DUPLICATE_ALERT)
    count = db.scalar(
        select(func.count()).select_from(AvailabilityAlert).where(AvailabilityAlert.user_id == user.id, active)
    )
    if (count or 0) >= MAX_ACTIVE_ALERTS_PER_USER:
        raise HTTPException(
            status_code=422,
            detail=f"You can have up to {MAX_ACTIVE_ALERTS_PER_USER} active alerts. Cancel one to add another.",
        )

    alert = AvailabilityAlert(
        user_id=user.id,
        email=user.email,
        site_id=payload.site_id,
        trail_id=payload.trail_id,
        start_date=payload.start_date,
        nights=payload.nights,
        party_size=payload.party_size,
        status="active",
    )
    db.add(alert)
    _commit_or_conflict(db)
    return _out(_get(db, user.id, alert.id))


@router.post("/{alert_id}/cancel", response_model=AlertOut)
def cancel_alert(alert_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    alert = _get(db, user_id, alert_id)
    if alert.status in ("active", "notified"):
        alert.status = "cancelled"
        alert.cancelled_at = datetime.now(timezone.utc)
        db.commit()
    return _out(_get(db, user_id, alert_id))


@router.post("/{alert_id}/rearm", response_model=AlertOut)
def rearm_alert(
    alert_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Watch again after a notification (e.g. someone else booked it first)."""
    alert = _get(db, user_id, alert_id)
    if alert.status != "notified":
        raise HTTPException(status_code=409, detail="Only alerts that have already notified you can be turned back on.")
    validate_stay(alert.start_date, alert.nights, today)
    _lock_user_alerts(db, user_id)
    count = db.scalar(
        select(func.count()).select_from(AvailabilityAlert)
        .where(AvailabilityAlert.user_id == user_id, AvailabilityAlert.status == "active")
    )
    if (count or 0) >= MAX_ACTIVE_ALERTS_PER_USER:
        raise HTTPException(status_code=422, detail=f"You can have up to {MAX_ACTIVE_ALERTS_PER_USER} active alerts.")
    alert.status = "active"
    alert.notified_at = None
    # An identical alert may have been set again after this one notified.
    _commit_or_conflict(db)
    return _out(_get(db, user_id, alert_id))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Removes the alert from the list entirely."""
    db.delete(_get(db, user_id, alert_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
