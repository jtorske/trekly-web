"""One run of the availability-alert poller (scripts/poll_alerts.py runs it).

Safe to call from any cron or worker, as often as you like:

- A lease in job_locks means two runs never overlap; a crashed run's lease
  expires after LEASE so the next one can proceed.
- Runs are skipped if the last one started less than MIN_INTERVAL ago: a
  global cap on polling frequency, whatever the schedule says.
- Each run makes at most MAX_REQUESTS live requests, and every request also
  takes from the global per-minute budget shared with the API. When either
  runs out, the remaining alerts wait for the next run (least recently
  checked go first).
- Alerts are merged into one request per (provider map, party size, date
  window), and fresh cached responses from on-demand checks are reused.

An alert fires once, when every night of its stay is available; it's then
'notified' until the user re-arms it. Alerts whose first night has passed
expire.
"""

from __future__ import annotations

import os
import socket
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from urllib.parse import urlencode

from app.backcountry.availability import (
    RESULTS_URL,
    AvailabilityChecker,
    CheckResult,
    MapGroup,
    ProviderError,
    RateLimited,
    group_of,
    parse_statuses,
)
from app.models.availability import AvailabilityAlert, AvailabilityCache, JobLock
from app.models.backcountry import BackcountrySite
from app.notify import Email, EmailSender

JOB_NAME = "alert_poller"
MIN_INTERVAL = timedelta(minutes=int(os.getenv("ALERT_POLL_MIN_INTERVAL_MINUTES", "10")))
MAX_REQUESTS = int(os.getenv("ALERT_POLL_MAX_REQUESTS", "20"))
LEASE = timedelta(minutes=15)
# Longest date range merged into one request.
MAX_WINDOW_NIGHTS = 31
CACHE_RETENTION = timedelta(days=1)
APP_URL = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


@dataclass
class PollReport:
    status: str = "ran"  # ran | skipped
    reason: str | None = None
    checked: int = 0
    notified: int = 0
    expired: int = 0
    live_requests: int = 0
    deferred: int = 0  # alerts left for the next run (request cap or budget)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.status == "skipped":
            return f"skipped: {self.reason}"
        return (
            f"checked {self.checked}, notified {self.notified}, expired {self.expired}, "
            f"deferred {self.deferred}, {self.live_requests} live request(s)"
            + (f", {len(self.errors)} error(s)" if self.errors else "")
        )


@dataclass
class Window:
    group: MapGroup
    party_size: int
    start: date
    end: date  # last night, inclusive
    alerts: list[AvailabilityAlert]

    @property
    def oldest_check(self) -> datetime:
        times = [_aware(a.last_checked_at) for a in self.alerts if a.last_checked_at]
        return min(times) if len(times) == len(self.alerts) else datetime.min.replace(tzinfo=timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def acquire_lock(db: Session, now: datetime, holder: str, min_interval: timedelta = MIN_INTERVAL) -> str | None:
    """None if acquired, otherwise why the run must be skipped."""
    if db.get(JobLock, JOB_NAME) is None:
        db.add(JobLock(name=JOB_NAME))
        try:
            db.commit()
        except IntegrityError:  # another run created it at the same moment
            db.rollback()
    lock = db.scalar(select(JobLock).where(JobLock.name == JOB_NAME).with_for_update())
    if lock.locked_until and _aware(lock.locked_until) > now:
        db.rollback()
        return f"another run ({lock.locked_by}) holds the lock until {lock.locked_until:%H:%M:%S}"
    if lock.last_started_at and now - _aware(lock.last_started_at) < min_interval:
        ago = int((now - _aware(lock.last_started_at)).total_seconds() // 60)
        db.rollback()
        return f"last run started {ago} min ago (minimum interval {int(min_interval.total_seconds() // 60)} min)"
    lock.locked_by = holder
    lock.locked_until = now + LEASE
    lock.last_started_at = now
    db.commit()
    return None


def release_lock(db: Session, now: datetime, result: str) -> None:
    db.rollback()
    lock = db.get(JobLock, JOB_NAME)
    if lock is not None:
        lock.locked_by = None
        lock.locked_until = None
        lock.last_finished_at = now
        lock.last_result = result[:500]
        db.commit()


def build_windows(alerts: list[AvailabilityAlert]) -> list[Window]:
    """Merge alerts on the same map and party size into date windows of at
    most MAX_WINDOW_NIGHTS nights."""
    by_key: dict[tuple[MapGroup, int], list[AvailabilityAlert]] = defaultdict(list)
    for alert in alerts:
        group = group_of(alert.site)
        if group is not None:
            by_key[(group, alert.party_size)].append(alert)
    windows: list[Window] = []
    for (group, party), members in by_key.items():
        members.sort(key=lambda a: a.start_date)
        current: Window | None = None
        for alert in members:
            last = alert.start_date + timedelta(days=alert.nights - 1)
            if current and (max(current.end, last) - current.start).days + 1 <= MAX_WINDOW_NIGHTS:
                current.end = max(current.end, last)
                current.alerts.append(alert)
            else:
                current = Window(group, party, alert.start_date, last, [alert])
                windows.append(current)
    return windows


def alert_email(alert: AvailabilityAlert, booking_url: str | None) -> Email:
    site = alert.site
    leave = alert.start_date + timedelta(days=alert.nights)
    dates = f"{alert.start_date:%a %b} {alert.start_date.day}"
    leave_s = f"{leave:%a %b} {leave.day}"
    name = site.name + (f" ({site.site_code})" if site.site_code and site.site_code != site.name else "")
    nights = f"{alert.nights} night{'s' if alert.nights != 1 else ''}"
    trail_link = (
        f"{APP_URL}/trails?" + urlencode({
            "id": str(alert.trail_id), "start": alert.start_date.isoformat(),
            "nights": alert.nights, "party": alert.party_size,
        })
        if alert.trail_id else None
    )
    lines = [
        f"Good news: {name} is showing as available for your whole stay.",
        "",
        f"  {dates} to {leave_s} ({nights}), party of {alert.party_size}",
        "",
        "Spots go quickly and Trekly doesn't book for you, so book on Parks Canada soon:",
        f"  {booking_url}" if booking_url else "  https://reservation.pc.gc.ca",
    ]
    if trail_link:
        lines += ["", f"Trail page: {trail_link}"]
    lines += [
        "",
        "This alert won't email you again. If the spot is gone by the time you look, "
        f"turn the alert back on from your alerts: {APP_URL}/alerts",
    ]
    return Email(to=alert.email, subject=f"{site.name} has opened up for {dates}", text="\n".join(lines))


def booking_url_for(alert: AvailabilityAlert) -> str | None:
    """Parks Canada's booking form for the campground's park and booking type."""
    group = group_of(alert.site)
    if group is None:
        return None
    return RESULTS_URL + "?" + urlencode({
        "resourceLocationId": group.location_id,
        "mapId": group.map_id,
        "bookingCategoryId": group.booking_category_id,
    })


def run_alert_poll(
    db: Session,
    checker: AvailabilityChecker,
    sender: EmailSender,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    max_requests: int = MAX_REQUESTS,
    min_interval: timedelta = MIN_INTERVAL,
    holder: str | None = None,
) -> PollReport:
    report = PollReport()
    started = now()
    holder = holder or f"{socket.gethostname()}:{os.getpid()}"
    reason = acquire_lock(db, started, holder, min_interval)
    if reason:
        report.status, report.reason = "skipped", reason
        return report
    try:
        _poll(db, checker, sender, now, max_requests, report)
    finally:
        release_lock(db, now(), report.summary())
    return report


def _poll(db, checker, sender, now, max_requests, report: PollReport) -> None:
    today = now().date()
    for alert in db.scalars(
        select(AvailabilityAlert).where(AvailabilityAlert.status == "active", AvailabilityAlert.start_date < today)
    ):
        alert.status = "expired"
        report.expired += 1
    db.execute(delete(AvailabilityCache).where(AvailabilityCache.fetched_at < now() - CACHE_RETENTION))
    db.commit()

    alerts = db.scalars(
        select(AvailabilityAlert)
        .where(AvailabilityAlert.status == "active")
        .options(selectinload(AvailabilityAlert.site).selectinload(BackcountrySite.park))
    ).all()
    windows = sorted(build_windows(list(alerts)), key=lambda w: w.oldest_check)

    for index, window in enumerate(windows):
        if report.live_requests >= max_requests:
            report.deferred += sum(len(w.alerts) for w in windows[index:])
            break
        before = report.live_requests
        try:
            result = CheckResult()
            response, _ = checker.response(window.group, window.start, window.end, window.party_size, result)
            report.live_requests += result.live_requests
        except RateLimited:
            report.deferred += sum(len(w.alerts) for w in windows[index:])
            break
        except ProviderError as error:
            report.errors.append(f"{window.group.map_id} {window.start}..{window.end}: {error}")
            report.live_requests = before + 1
            continue

        for alert in window.alerts:
            offset = (alert.start_date - window.start).days
            statuses = parse_statuses(response, alert.site.provider_resource_id, alert.nights, offset)
            alert.last_result = statuses
            alert.last_checked_at = now()
            report.checked += 1
            if all(s == "available" for s in statuses):
                try:
                    sender.send(alert_email(alert, booking_url_for(alert)))
                except Exception as error:  # noqa: BLE001 - try again next run
                    report.errors.append(f"email for alert {alert.id}: {error}")
                    db.commit()
                    continue
                alert.status = "notified"
                alert.notified_at = now()
                report.notified += 1
            db.commit()
