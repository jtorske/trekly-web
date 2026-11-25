"""Summer or winter: the one place Trekly decides which season it is.

Winter runs from WINTER_STARTS (Nov 15) up to WINTER_ENDS (Apr 15). Near
either boundary (SHOULDER_DAYS each side) snow can tip it: a measured snow
depth of SNOW_ON_CM or more makes it winter, under SNOW_OFF_CM makes it
summer, and anything in between (or no measurement) keeps the date's answer.
Away from the boundaries the date alone decides, so a freak October storm
or a thin January doesn't flip the whole site.

Everything seasonal reads this module: Explore's default mode (through
GET /api/season), picks, recommendations, @trekly spotlights and the
landing page. The frontend never re-derives the dates; it asks the API.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

Season = Literal["summer", "winter"]

WINTER_STARTS = (11, 15)  # month, day: first day of winter
WINTER_ENDS = (4, 15)  # first day of summer
SHOULDER_DAYS = 21
SNOW_ON_CM = 10.0
SNOW_OFF_CM = 2.0
# Trekly's trails are Canadian; the calendar day is Canada's, not the server's.
TIMEZONE = ZoneInfo("America/Edmonton")


def today() -> date:
    return datetime.now(TIMEZONE).date()


def _boundary(year: int, month_day: tuple[int, int]) -> date:
    return date(year, *month_day)


def by_date(day: date) -> Season:
    """The season from the calendar alone."""
    md = (day.month, day.day)
    return "winter" if md >= WINTER_STARTS or md < WINTER_ENDS else "summer"


def near_boundary(day: date) -> bool:
    """Within SHOULDER_DAYS of a season change, where snow data may decide."""
    window = timedelta(days=SHOULDER_DAYS)
    for year in (day.year - 1, day.year, day.year + 1):
        for md in (WINTER_STARTS, WINTER_ENDS):
            if abs(day - _boundary(year, md)) <= window:
                return True
    return False


def season_for(day: date, snow_depth_cm: float | None = None) -> Season:
    """The season on `day`, adjusted by a snow depth (cm) when one is known."""
    season = by_date(day)
    if snow_depth_cm is None or not near_boundary(day):
        return season
    if snow_depth_cm >= SNOW_ON_CM:
        return "winter"
    if snow_depth_cm < SNOW_OFF_CM:
        return "summer"
    return season


def next_change(day: date) -> date:
    """The first day of the other season (by date)."""
    current = by_date(day)
    for year in (day.year, day.year + 1):
        md = WINTER_STARTS if current == "summer" else WINTER_ENDS
        candidate = _boundary(year, md)
        if candidate > day:
            return candidate
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class SeasonInfo:
    season: Season
    by_date: Season
    adjusted_by_snow: bool
    next_change: date


def info(day: date, snow_depth_cm: float | None = None) -> SeasonInfo:
    season = season_for(day, snow_depth_cm)
    base = by_date(day)
    return SeasonInfo(season=season, by_date=base, adjusted_by_snow=season != base, next_change=next_change(day))


# --- Picks: the finer calendar season for summer-mode suggestions -------------

def pick_season(day: date) -> Literal["spring", "summer", "fall", "winter"] | None:
    """Which seasonal pick fits `day`. Winter whenever season_for says so;
    in summer mode spring (to May 31), summer (Jun-Aug) or fall (Sep-Oct).
    None in early November: no fall picks once the snow comes."""
    if by_date(day) == "winter":
        return "winter"
    if day.month in (4, 5):
        return "spring"
    if day.month in (6, 7, 8):
        return "summer"
    if day.month in (9, 10):
        return "fall"
    return None
