"""Visit streaks: every rule in one place.

A streak counts consecutive *periods* with at least one signed-in visit.
The period is a calendar day in the visitor's own time zone. To switch to
a weekly streak, change `period()` (and the wording in the frontend's
lib/visitStreak.ts); the rules below only compare period numbers.

    same period as the last visit   → nothing changes
    the next period                 → current + 1
    a gap of one period or more     → current resets to 1
    an earlier period               → nothing changes (the time zone moved
                                      west; never reset or go backwards)

longest is raised whenever current passes it.

The browser sends its IANA time zone; "today" is the date there, clamped to
within a day of the server's UTC date, so a made-up or changed zone can
shift the date by one day at most. Unknown zones count as UTC. Zones come
from the pinned tzdata package, never the OS copy, which can be years old
(Alberta stopped changing its clocks in November 2026: tzdata 2026f). The counts
are only ever computed here: the client never sends one.

Only the last visit's date and the two counts are stored (table
visit_streaks), never a visit history or the time zone.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from zoneinfo import ZoneInfo

# Longest real IANA names are ~32 characters ("America/Argentina/ComodRivadavia").
MAX_TIME_ZONE_LENGTH = 64
_TIME_ZONE = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*$")
MAX_SHIFT = timedelta(days=1)


def period(day: date) -> int:
    """The streak's unit, as a number that goes up by one per unit.

    Daily: the date's ordinal. Weekly (Monday to Sunday) would be
    `(day.toordinal() - 1) // 7`.
    """
    return day.toordinal()


@dataclass(frozen=True)
class Streak:
    current: int
    longest: int
    last_visit: date | None


NO_STREAK = Streak(current=0, longest=0, last_visit=None)


def record_visit(streak: Streak, today: date) -> tuple[Streak, bool]:
    """The streak after a visit on `today`, and whether `current` grew."""
    if streak.last_visit is None:
        current = 1
    else:
        gap = period(today) - period(streak.last_visit)
        if gap <= 0:
            return streak, False
        current = streak.current + 1 if gap == 1 else 1
    grew = current > streak.current
    return Streak(current=current, longest=max(streak.longest, current), last_visit=today), grew


def is_alive(last_visit: date | None, today: date) -> bool:
    """Visiting `today` would still continue the streak."""
    return last_visit is not None and period(today) - period(last_visit) <= 1


def current_on(streak: Streak, today: date) -> int:
    """The current streak as of `today`: 0 once it has lapsed, even though
    the stored count only resets on the next visit."""
    return streak.current if is_alive(streak.last_visit, today) else 0


@lru_cache(maxsize=512)
def _load(name: str) -> ZoneInfo | None:
    try:
        with files("tzdata.zoneinfo").joinpath(*name.split("/")).open("rb") as source:
            return ZoneInfo.from_file(source, key=name)
    except Exception:  # not a zone (missing file, a directory, not TZif data)
        return None


def valid_time_zone(name: str | None) -> ZoneInfo | None:
    # The pattern allows no "." at all, so no path can leave the package.
    if not name or len(name) > MAX_TIME_ZONE_LENGTH or not _TIME_ZONE.match(name):
        return None
    return _load(name)


def local_today(time_zone: str | None, now: datetime) -> date:
    """Today's date in `time_zone`, within a day of `now`'s UTC date."""
    now = now.astimezone(timezone.utc)
    zone = valid_time_zone(time_zone)
    utc_today = now.date()
    if zone is None:
        return utc_today
    local = now.astimezone(zone).date()
    return min(max(local, utc_today - MAX_SHIFT), utc_today + MAX_SHIFT)


def earliest_today(now: datetime) -> date:
    """The earliest date it can be anywhere right now. Visitors don't know
    the owner's time zone, so a streak is shown as lapsed only once it has
    lapsed everywhere."""
    return now.astimezone(timezone.utc).date() - MAX_SHIFT
