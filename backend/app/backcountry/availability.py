"""Per-night campground availability from Parks Canada (availability/map).

Only the campgrounds a user is looking at are queried, on demand, and the
alert poller only queries campgrounds with active alerts. One request covers
every site on one provider map for a date range, so a trail usually costs one
or two requests. Responses are cached in availability_cache for a few minutes
and every live request takes from a global per-minute budget
(provider_request_budget), shared by the API and the poller.

Request shape (established live 2026-10-15; see
tests/fixtures/parks_canada_availability.json and docs/backcountry-catalog.md):
startDate..endDate is inclusive and returns one value per night, but endDate
must be after startDate (start == end is rejected with HTTP 400, seen live), so
a one-night question asks for two nights and reads the first. The cart and
booking UIDs aren't validated, so fresh random ones are sent each time. The
Referer must be the matching results page.

Status values: 0 available (confirmed on Parks Canada's own map), 1
unavailable/full (GoingToCamp enum; not yet seen live), 2 not operating
(seen: West Coast Trail and Pukaskwa out of season), 3 not bookable online
yet (seen: dates before release). Anything else is "unknown" and never counts
as available.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backcountry.parks_canada import PROVIDER
from app.models.availability import AvailabilityCache, ProviderRequestBudget
from app.models.backcountry import BackcountrySite

RESULTS_URL = "https://reservation.pc.gc.ca/create-booking/results"

STATUS_BY_CODE = {0: "available", 1: "full", 2: "closed", 3: "not_released"}
STATUSES = ("available", "full", "closed", "not_released", "unknown")

CACHE_TTL = timedelta(minutes=int(os.getenv("AVAILABILITY_CACHE_MINUTES", "5")))
# Global cap on live availability requests per minute, across the API and
# the poller (one budget row in the database).
REQUESTS_PER_MINUTE = int(os.getenv("AVAILABILITY_REQUESTS_PER_MINUTE", "20"))
BUDGET_WINDOW = timedelta(minutes=1)
# Parks Canada: "a maximum Party Size of 4 per Tent Pad".
PEOPLE_PER_TENT_PAD = 4
# Parks Canada's "standard" capacity category.
STANDARD_CAPACITY_CATEGORY = -32767


class RateLimited(Exception):
    def __init__(self, retry_after_s: int):
        super().__init__(f"availability budget used up; retry in {retry_after_s}s")
        self.retry_after_s = retry_after_s


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class MapGroup:
    """Sites that one availability request covers."""

    location_id: str
    map_id: str
    booking_category_id: str


@dataclass
class SiteAvailability:
    site_id: Any
    dates: list[date]
    statuses: list[str]

    @property
    def summary(self) -> str:
        return summarize(self.statuses)


@dataclass
class CheckResult:
    sites: dict[Any, SiteAvailability] = field(default_factory=dict)
    # Oldest provider response used: how fresh the answer is.
    fetched_at: datetime | None = None
    live_requests: int = 0


def summarize(statuses: list[str]) -> str:
    """One word for a stay: available only if every night is."""
    if statuses and all(s == "available" for s in statuses):
        return "available"
    if any(s == "available" for s in statuses):
        return "partial"
    if len(set(statuses)) == 1:
        return statuses[0]
    if "full" in statuses:
        return "full"
    return "unknown"


def group_of(site: BackcountrySite) -> MapGroup | None:
    if site.provider != PROVIDER or not site.provider_map_id or not site.provider_booking_category_id:
        return None
    return MapGroup(site.provider_location_id, site.provider_map_id, site.provider_booking_category_id)


def tent_pads(party_size: int) -> int:
    return max(1, math.ceil(party_size / PEOPLE_PER_TENT_PAD))


def night_dates(start: date, nights: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(nights)]


def cache_key(group: MapGroup, start: date, end: date, party_size: int) -> str:
    return ":".join(
        [PROVIDER, group.location_id, group.map_id, group.booking_category_id,
         start.isoformat(), end.isoformat(), str(party_size)]
    )


def availability_request(group: MapGroup, start: date, end: date, party_size: int) -> tuple[str, dict[str, str]]:
    """(API path, extra headers) for one availability/map request."""
    params = {
        "mapId": group.map_id,
        "bookingCategoryId": group.booking_category_id,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "getDailyAvailability": "true",
        "isReserving": "true",
        "filterData": "[]",
        "peopleCapacityCategoryCounts": json.dumps(
            [{"capacityCategoryId": STANDARD_CAPACITY_CATEGORY, "subCapacityCategoryId": None, "count": party_size}]
        ),
        "numEquipment": str(tent_pads(party_size)),
        "seed": datetime.now(timezone.utc).isoformat(),
        "cartUid": str(uuid.uuid4()),
        "cartTransactionUid": str(uuid.uuid4()),
        "bookingUid": str(uuid.uuid4()),
        "groupHoldUid": "",
    }
    referer = RESULTS_URL + "?" + urlencode({
        "resourceLocationId": group.location_id,
        "mapId": group.map_id,
        "bookingCategoryId": group.booking_category_id,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    })
    return "availability/map?" + urlencode(params), {"Referer": referer}


def parse_statuses(response: dict, resource_id: str, nights: int, offset: int = 0) -> list[str]:
    """Statuses for `nights` nights starting `offset` nights into the response."""
    entries = ((response or {}).get("resourceAvailabilities") or {}).get(str(resource_id)) or []
    out = []
    for i in range(offset, offset + nights):
        if i < len(entries) and isinstance(entries[i], dict):
            out.append(STATUS_BY_CODE.get(entries[i].get("availability"), "unknown"))
        else:
            out.append("unknown")
    return out


def take_budget(db: Session, now: datetime, limit: int | None = None, provider: str = PROVIDER) -> None:
    """Count one live request against the global per-minute budget, or raise
    RateLimited. Commits straight away so the row lock isn't held while the
    request is in flight."""
    limit = REQUESTS_PER_MINUTE if limit is None else limit
    row = db.scalar(
        select(ProviderRequestBudget).where(ProviderRequestBudget.provider == provider).with_for_update()
    )
    if row is None:
        row = ProviderRequestBudget(provider=provider, window_started_at=now, window_count=0, total_requests=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # another process created it first
            db.rollback()
            return take_budget(db, now, limit, provider)
    started = _aware(row.window_started_at)
    if now - started >= BUDGET_WINDOW:
        row.window_started_at = now
        row.window_count = 0
        started = now
    if row.window_count >= limit:
        db.rollback()
        raise RateLimited(max(1, math.ceil((started + BUDGET_WINDOW - now).total_seconds())))
    row.window_count += 1
    row.total_requests = (row.total_requests or 0) + 1
    db.commit()


def _aware(value: datetime) -> datetime:
    # SQLite (tests) hands back naive datetimes.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AvailabilityChecker:
    """Answers "which nights are free" for a set of sites, using the shared
    cache first and the provider (within budget) otherwise."""

    def __init__(
        self,
        db: Session,
        fetch: Callable[[str, dict[str, str]], Any],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        ttl: timedelta = CACHE_TTL,
        requests_per_minute: int | None = None,
    ):
        self.db = db
        self.fetch = fetch
        self.now = now
        self.ttl = ttl
        self.requests_per_minute = requests_per_minute

    def check(self, sites: Iterable[BackcountrySite], start: date, nights: int, party_size: int) -> CheckResult:
        """Nights start..start+nights-1 for each site. Sites that can't be
        checked online (no map) come back as all 'unknown'."""
        result = CheckResult()
        groups: dict[MapGroup, list[BackcountrySite]] = defaultdict(list)
        dates = night_dates(start, nights)
        for site in sites:
            group = group_of(site)
            if group is None:
                result.sites[site.id] = SiteAvailability(site.id, dates, ["unknown"] * nights)
            else:
                groups[group].append(site)
        for group, members in groups.items():
            response, fetched_at = self.response(group, start, dates[-1], party_size, result)
            result.fetched_at = fetched_at if result.fetched_at is None else min(result.fetched_at, fetched_at)
            for site in members:
                result.sites[site.id] = SiteAvailability(
                    site.id, dates, parse_statuses(response, site.provider_resource_id, nights)
                )
        return result

    def response(self, group: MapGroup, start: date, end: date, party_size: int, result: CheckResult | None = None):
        """The provider response covering nights start..end (inclusive). It may
        cover one extra night: see the module docstring."""
        end = max(end, start + timedelta(days=1))
        key = cache_key(group, start, end, party_size)
        now = self.now()
        cached = self.db.get(AvailabilityCache, key)
        if cached is not None and now - _aware(cached.fetched_at) < self.ttl:
            return cached.response, _aware(cached.fetched_at)

        take_budget(self.db, now, self.requests_per_minute)
        path, headers = availability_request(group, start, end, party_size)
        try:
            body = self.fetch(path, headers)
        except Exception as error:  # noqa: BLE001 - surfaced as one provider error
            raise ProviderError(str(error)) from error
        if not isinstance(body, dict) or "resourceAvailabilities" not in body:
            raise ProviderError("unexpected availability response")
        if result is not None:
            result.live_requests += 1

        cached = self.db.get(AvailabilityCache, key)
        if cached is None:
            self.db.add(AvailabilityCache(cache_key=key, response=body, fetched_at=now))
        else:
            cached.response = body
            cached.fetched_at = now
        try:
            self.db.commit()
        except IntegrityError:  # a concurrent check cached the same key
            self.db.rollback()
        return body, now
