"""The signed-in user's "alert me when this opens up" alerts.

An alert watches one campground for one stay (start date + nights + party
size). Setting one sends a "we're watching" email. The poller
(scripts/poll_alerts.py), or the user's own "check now", emails once when
every night of the stay is available, then marks the alert 'notified'; the
user can re-arm it or move it to new dates.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.alert_emails import booking_url_for, watching_email
from app.alert_poller import send_opened
from app.auth import CurrentUser, get_current_user, get_current_user_id
from app.backcountry.alertable import alert_block, party_problem
from app.backcountry.availability import AvailabilityChecker, ProviderError, RateLimited, group_of, summarize
from app.database import get_db
from app.models.availability import (
    MAX_ACTIVE_ALERTS_PER_USER,
    MAX_ALERT_NIGHTS,
    MAX_PARTY_SIZE,
    AvailabilityAlert,
)
from app.models.backcountry import BackcountrySite
from app.models.trail_campground import TrailCampground
from app.notify import Email, EmailSender, get_email_sender
from app.routers.availability import availability_error, get_availability_fetch, get_today, validate_stay

router = APIRouter(prefix="/api/me/alerts", tags=["my alerts"])
log = logging.getLogger(__name__)


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    trail_id: UUID | None = None
    start_date: date
    nights: int = Field(ge=1, le=MAX_ALERT_NIGHTS)
    party_size: int = Field(default=2, ge=1, le=MAX_PARTY_SIZE)


class AlertStayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    nights: int = Field(ge=1, le=MAX_ALERT_NIGHTS)
    party_size: int = Field(ge=1, le=MAX_PARTY_SIZE)


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
    # Parks Canada's booking form on these dates; null if it can't be booked online.
    booking_url: str | None


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
        booking_url=booking_url_for(alert),
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


def _send_quietly(sender: EmailSender, email: Email) -> None:
    """For emails nothing depends on: a failure is logged, not raised."""
    try:
        sender.send(email)
    except Exception:  # noqa: BLE001
        log.exception("couldn't send %r", email.subject)


def _check_active_cap(db: Session, user_id: UUID) -> None:
    count = db.scalar(
        select(func.count()).select_from(AvailabilityAlert)
        .where(AvailabilityAlert.user_id == user_id, AvailabilityAlert.status == "active")
    )
    if (count or 0) >= MAX_ACTIVE_ALERTS_PER_USER:
        raise HTTPException(
            status_code=422,
            detail=f"You can have up to {MAX_ACTIVE_ALERTS_PER_USER} active alerts. Cancel one to add another.",
        )


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
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    sender: EmailSender = Depends(get_email_sender),
):
    if not user.email:
        raise HTTPException(status_code=422, detail="Your account needs an email address to get alerts.")
    validate_stay(payload.start_date, payload.nights, today)

    site = db.get(BackcountrySite, payload.site_id)
    if site is None or not site.is_publicly_listed or site.retired_at is not None:
        raise HTTPException(status_code=422, detail="That campground isn't available for alerts.")
    if group_of(site) is None:
        raise HTTPException(status_code=422, detail="Parks Canada doesn't show availability for that campground online.")
    if blocked := alert_block(site):
        raise HTTPException(status_code=422, detail=blocked)
    if too_many := party_problem(site, payload.party_size):
        raise HTTPException(status_code=422, detail=too_many)
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
    _check_active_cap(db, user.id)

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
    created = _get(db, user.id, alert.id)
    # After the response: the alert is set whether or not this email goes.
    background.add_task(_send_quietly, sender, watching_email(created))
    return _out(created)


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
    _check_active_cap(db, user_id)
    alert.status = "active"
    alert.notified_at = None
    # An identical alert may have been set again after this one notified.
    _commit_or_conflict(db)
    return _out(_get(db, user_id, alert_id))


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert_stay(
    alert_id: UUID,
    payload: AlertStayIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """New dates or party size. The alert watches again from scratch: active,
    unchecked, and able to email once more, whatever state it was in."""
    alert = _get(db, user_id, alert_id)
    validate_stay(payload.start_date, payload.nights, today)
    site = db.get(BackcountrySite, alert.site_id)
    if site is not None and (too_many := party_problem(site, payload.party_size)):
        raise HTTPException(status_code=422, detail=too_many)
    _lock_user_alerts(db, user_id)
    duplicate = db.scalar(
        select(AvailabilityAlert.id).where(
            AvailabilityAlert.user_id == user_id, AvailabilityAlert.status == "active",
            AvailabilityAlert.id != alert.id,
            AvailabilityAlert.site_id == alert.site_id,
            AvailabilityAlert.start_date == payload.start_date,
            AvailabilityAlert.nights == payload.nights,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=DUPLICATE_ALERT)
    if alert.status != "active":
        _check_active_cap(db, user_id)
    alert.start_date = payload.start_date
    alert.nights = payload.nights
    alert.party_size = payload.party_size
    alert.status = "active"
    alert.last_result = None
    alert.last_checked_at = None
    alert.notified_at = None
    alert.cancelled_at = None
    _commit_or_conflict(db)
    return _out(_get(db, user_id, alert_id))


@router.post("/{alert_id}/check", response_model=AlertOut)
def check_alert(
    alert_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    fetch=Depends(get_availability_fetch),
    today: date = Depends(get_today),
    sender: EmailSender = Depends(get_email_sender),
):
    """Check an active alert now, through the same cache and request budget as
    every other check. If the whole stay is open it notifies just as the
    poller would: the email goes first, and the alert only counts as notified
    once it has."""
    alert = _get(db, user_id, alert_id)
    if alert.status != "active":
        raise HTTPException(status_code=409, detail="Only active alerts can be checked.")
    if alert.start_date < today:
        raise HTTPException(status_code=422, detail="These dates have passed, so there's nothing left to check.")
    try:
        result = AvailabilityChecker(db, fetch).check([alert.site], alert.start_date, alert.nights, alert.party_size)
    except (RateLimited, ProviderError) as error:
        raise availability_error(error) from error
    found = result.sites[alert.site_id]
    alert.last_result = found.statuses
    alert.last_checked_at = datetime.now(timezone.utc)
    if found.summary == "available":
        problem = send_opened(alert, sender, alert.last_checked_at)
        if problem:
            log.error("opened-up email for alert %s failed: %s", alert.id, problem)
    db.commit()
    return _out(_get(db, user_id, alert_id))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Removes the alert from the list entirely."""
    db.delete(_get(db, user_id, alert_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
