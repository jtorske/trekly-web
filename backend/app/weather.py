"""Five-day trail forecasts from Open-Meteo (https://open-meteo.com, no key).

One request per trail covers both points we forecast: the trailhead and,
when we know it, the high point. Open-Meteo corrects temperatures for the
elevation it's given, so both points use the trail's coordinates with
different elevations. The trailhead elevation follows the catalogue's own
definition (elevation gain = high point - trailhead); without it, Open-Meteo
uses its terrain model at the coordinates, which is where trails start.

Responses are cached per trail for an hour in availability_cache (the same
keyed response cache the Parks Canada lookups use, under an "open-meteo:"
prefix), so a trail costs at most 24 requests a day. Data is CC BY 4.0:
the frontend credits Open-Meteo.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.availability import AvailabilityCache
from app.models.trail import Trail

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 5
CACHE_TTL = timedelta(minutes=int(os.getenv("FORECAST_CACHE_MINUTES", "60")))
TIMEOUT_S = float(os.getenv("FORECAST_TIMEOUT_SECONDS", "6"))
# A high point this close to the trailhead adds nothing a hiker could use.
MIN_SUMMIT_RISE_M = 150
DAILY = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
    "sunrise",
    "sunset",
)
USER_AGENT = "Trekly/1.0 (trail forecasts; https://trekly-web.vercel.app)"


class ForecastUnavailable(Exception):
    """Open-Meteo failed or sent something we can't read."""


class ForecastTimeout(ForecastUnavailable):
    pass


class NoForecast(Exception):
    """The trail has no coordinates, so there's nothing to forecast."""


@dataclass(frozen=True)
class ForecastPoints:
    latitude: float
    longitude: float
    # None = let Open-Meteo use its terrain model (the trailhead without data).
    trailhead_m: int | None
    summit_m: int | None


def forecast_points(trail: Trail) -> ForecastPoints:
    if trail.latitude is None or trail.longitude is None:
        raise NoForecast()
    high = trail.max_elevation_m
    trailhead = high - trail.elevation_gain_m if high is not None and trail.elevation_gain_m is not None else None
    summit = None
    if high is not None and (trailhead is None or high - trailhead >= MIN_SUMMIT_RISE_M):
        summit = high
    return ForecastPoints(float(trail.latitude), float(trail.longitude), trailhead, summit)


def forecast_url(points: ForecastPoints) -> str:
    params = {
        "daily": ",".join(DAILY),
        "timezone": "auto",
        "forecast_days": str(FORECAST_DAYS),
        "wind_speed_unit": "kmh",
    }
    if points.summit_m is None:
        params["latitude"] = f"{points.latitude:.4f}"
        params["longitude"] = f"{points.longitude:.4f}"
        if points.trailhead_m is not None:
            params["elevation"] = str(points.trailhead_m)
    else:
        # Two locations in one request. "nan" asks for the terrain model's
        # elevation at a point, so the trailhead keeps that fallback.
        params["latitude"] = f"{points.latitude:.4f},{points.latitude:.4f}"
        params["longitude"] = f"{points.longitude:.4f},{points.longitude:.4f}"
        trailhead = "nan" if points.trailhead_m is None else str(points.trailhead_m)
        params["elevation"] = f"{trailhead},{points.summit_m}"
    return f"{FORECAST_URL}?{urlencode(params)}"


def cache_key(trail: Trail, points: ForecastPoints) -> str:
    # The coordinates and elevations are part of the key, so a catalogue fix
    # takes effect without waiting out the cache.
    return (
        f"open-meteo:forecast:{trail.id}:{points.latitude:.4f}:{points.longitude:.4f}:"
        f"{points.trailhead_m}:{points.summit_m}"
    )


def fetch_json(url: str, timeout_s: float = TIMEOUT_S) -> Any:
    """GET `url` once (no retries: a slow forecast must never hold up a page)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.load(response)
    except (TimeoutError, socket.timeout) as error:
        raise ForecastTimeout(f"Open-Meteo didn't answer within {timeout_s:g}s") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise ForecastTimeout(f"Open-Meteo didn't answer within {timeout_s:g}s") from error
        raise ForecastUnavailable(str(error)) from error
    except (ValueError, OSError) as error:
        raise ForecastUnavailable(str(error)) from error


def _days(location: dict) -> list[dict]:
    daily = location.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise ForecastUnavailable("Open-Meteo response has no daily forecast")
    count = len(daily["time"])
    columns = {}
    for name in DAILY:
        values = daily.get(name)
        if not isinstance(values, list) or len(values) != count:
            raise ForecastUnavailable(f"Open-Meteo response is missing {name}")
        columns[name] = values
    return [
        {
            "date": daily["time"][i],
            "weather_code": columns["weather_code"][i],
            "temp_max_c": columns["temperature_2m_max"][i],
            "temp_min_c": columns["temperature_2m_min"][i],
            "precip_probability_pct": columns["precipitation_probability_max"][i],
            "precip_mm": columns["precipitation_sum"][i],
            "snowfall_cm": columns["snowfall_sum"][i],
            "wind_max_kmh": columns["wind_speed_10m_max"][i],
            "sunrise": columns["sunrise"][i],
            "sunset": columns["sunset"][i],
        }
        for i in range(count)
    ]


def parse_forecast(body: Any, points: ForecastPoints) -> dict:
    """Open-Meteo's body (one location object, or a list of two) as
    {timezone, trailhead: {elevation_m, days}, summit: {...} | None}."""
    locations = body if isinstance(body, list) else [body]
    if not all(isinstance(location, dict) for location in locations):
        raise ForecastUnavailable("unexpected Open-Meteo response")
    expected = 1 if points.summit_m is None else 2
    if len(locations) != expected:
        raise ForecastUnavailable(f"expected {expected} forecast locations, got {len(locations)}")

    def point(location: dict) -> dict:
        elevation = location.get("elevation")
        return {
            "elevation_m": round(elevation) if isinstance(elevation, (int, float)) else None,
            "days": _days(location),
        }

    trailhead = point(locations[0])
    summit = point(locations[1]) if expected == 2 else None
    # Without our own trailhead elevation, Open-Meteo's terrain model decides
    # it; drop a "summit" that turns out to be barely higher.
    if (
        summit is not None
        and trailhead["elevation_m"] is not None
        and summit["elevation_m"] is not None
        and summit["elevation_m"] - trailhead["elevation_m"] < MIN_SUMMIT_RISE_M
    ):
        summit = None
    return {"timezone": locations[0].get("timezone"), "trailhead": trailhead, "summit": summit}


def _aware(value: datetime) -> datetime:
    # SQLite (tests) hands back naive datetimes.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def trail_forecast(
    db: Session,
    trail: Trail,
    fetch: Callable[[str], Any],
    *,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ttl: timedelta = CACHE_TTL,
) -> tuple[dict, datetime]:
    """The parsed forecast and when it was fetched, from the cache when it's
    under `ttl` old and from Open-Meteo otherwise."""
    points = forecast_points(trail)
    key = cache_key(trail, points)
    current = now()
    cached = db.get(AvailabilityCache, key)
    if cached is not None and current - _aware(cached.fetched_at) < ttl:
        return parse_forecast(cached.response, points), _aware(cached.fetched_at)

    try:
        body = fetch(forecast_url(points))
    except ForecastUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - any client failure is "unavailable"
        raise ForecastUnavailable(str(error)) from error
    # Parse before caching, so a malformed response is never served for an hour.
    forecast = parse_forecast(body, points)

    cached = db.get(AvailabilityCache, key)
    if cached is None:
        db.add(AvailabilityCache(cache_key=key, response=body, fetched_at=current))
    else:
        cached.response = body
        cached.fetched_at = current
    try:
        db.commit()
    except IntegrityError:  # a concurrent request cached the same key
        db.rollback()
    return forecast, current
