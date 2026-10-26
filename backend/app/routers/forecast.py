"""GET /api/trails/{id}/forecast: a five-day forecast at the trailhead and,
when known, the high point. See app/weather.py."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trail import Trail
from app.weather import ForecastTimeout, ForecastUnavailable, NoForecast, fetch_json, trail_forecast

router = APIRouter(prefix="/api/trails", tags=["trails"])


class ForecastDayOut(BaseModel):
    date: str
    # WMO weather interpretation code (Open-Meteo's weather_code).
    weather_code: int | None
    temp_max_c: float | None
    temp_min_c: float | None
    precip_probability_pct: int | None
    precip_mm: float | None
    snowfall_cm: float | None
    wind_max_kmh: float | None
    # Local times at the trail, e.g. "2026-10-26T08:01".
    sunrise: str | None
    sunset: str | None


class ForecastPointOut(BaseModel):
    elevation_m: int | None
    days: list[ForecastDayOut]


class TrailForecastOut(BaseModel):
    trail_id: UUID
    timezone: str | None
    fetched_at: datetime
    trailhead: ForecastPointOut
    summit: ForecastPointOut | None
    source: Literal["Open-Meteo"] = "Open-Meteo"


def get_forecast_fetch():
    """The live Open-Meteo call; overridden in tests."""
    return fetch_json


@router.get("/{trail_id}/forecast", response_model=TrailForecastOut)
def get_trail_forecast(trail_id: UUID, db: Session = Depends(get_db), fetch=Depends(get_forecast_fetch)):
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    try:
        forecast, fetched_at = trail_forecast(db, trail, fetch)
    except NoForecast as error:
        raise HTTPException(status_code=404, detail="There's no forecast for this trail.") from error
    except ForecastTimeout as error:
        raise HTTPException(status_code=504, detail="The weather service is taking too long. Try again shortly.") from error
    except ForecastUnavailable as error:
        raise HTTPException(status_code=502, detail="The weather forecast isn't available right now.") from error
    return TrailForecastOut(trail_id=trail.id, fetched_at=fetched_at, **forecast)
