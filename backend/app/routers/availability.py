"""On-demand availability for a trail's campgrounds (guests welcome)."""

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backcountry.availability import AvailabilityChecker, ProviderError, RateLimited
from app.backcountry.parks_canada import ParksCanadaClient
from app.database import get_db
from app.models.availability import MAX_ALERT_NIGHTS, MAX_PARTY_SIZE
from app.models.backcountry import BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailCampground

router = APIRouter(prefix="/api/trails", tags=["availability"])

# How far ahead a check may look. Parks Canada releases about a season ahead;
# later dates come back as "not_released".
MAX_DAYS_AHEAD = 550

Status = Literal["available", "full", "closed", "not_released", "unknown"]
Summary = Literal["available", "partial", "full", "closed", "not_released", "unknown"]


class NightOut(BaseModel):
    date: date
    status: Status


class CampgroundAvailabilityOut(BaseModel):
    site_id: UUID
    summary: Summary
    nights: list[NightOut]


class TrailAvailabilityOut(BaseModel):
    trail_id: UUID
    start: date
    nights: int
    party_size: int
    checked_at: datetime | None
    campgrounds: list[CampgroundAvailabilityOut]


@lru_cache
def _client() -> ParksCanadaClient:
    # Short retries: a person is waiting on this request.
    return ParksCanadaClient(None, delay_s=1.0, max_retries=2, timeout_s=15.0)


def get_availability_fetch():
    """The live provider call; overridden with saved fixtures in tests."""
    return lambda path, headers: _client().get_live(path, headers)


def get_today() -> date:
    """Today's date; overridden in tests."""
    return date.today()


def validate_stay(start: date, nights: int, today: date) -> None:
    if start < today:
        raise HTTPException(status_code=422, detail="Pick a start date from today onwards.")
    if start > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=422, detail="That's too far ahead to check.")
    if not 1 <= nights <= MAX_ALERT_NIGHTS:
        raise HTTPException(status_code=422, detail=f"Check between 1 and {MAX_ALERT_NIGHTS} nights.")


def availability_error(error: Exception) -> HTTPException:
    if isinstance(error, RateLimited):
        return HTTPException(
            status_code=429,
            detail="Lots of people are checking availability right now. Try again in a minute.",
            headers={"Retry-After": str(error.retry_after_s)},
        )
    return HTTPException(status_code=502, detail="Parks Canada isn't responding right now. Try again shortly.")


@router.get("/{trail_id}/availability", response_model=TrailAvailabilityOut)
def trail_availability(
    trail_id: UUID,
    start: date,
    nights: int = Query(..., ge=1, le=MAX_ALERT_NIGHTS),
    party: int = Query(2, ge=1, le=MAX_PARTY_SIZE),
    db: Session = Depends(get_db),
    fetch=Depends(get_availability_fetch),
    today: date = Depends(get_today),
):
    """Per-night availability at this trail's listed, unretired campgrounds."""
    if db.get(Trail, trail_id) is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    validate_stay(start, nights, today)

    sites = db.scalars(
        select(BackcountrySite)
        .join(TrailCampground, TrailCampground.site_id == BackcountrySite.id)
        .where(
            TrailCampground.trail_id == trail_id,
            BackcountrySite.is_publicly_listed.is_(True),
            BackcountrySite.retired_at.is_(None),
        )
    ).all()
    try:
        result = AvailabilityChecker(db, fetch).check(sites, start, nights, party)
    except (RateLimited, ProviderError) as error:
        raise availability_error(error) from error

    return TrailAvailabilityOut(
        trail_id=trail_id,
        start=start,
        nights=nights,
        party_size=party,
        checked_at=result.fetched_at,
        campgrounds=[
            CampgroundAvailabilityOut(
                site_id=site_id,
                summary=found.summary,
                nights=[NightOut(date=d, status=s) for d, s in zip(found.dates, found.statuses)],
            )
            for site_id, found in result.sites.items()
        ],
    )
