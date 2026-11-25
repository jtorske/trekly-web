"""GET /api/season: summer or winter, from app/season.py (the only source)."""

from datetime import date

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app import season as season_rules

router = APIRouter(prefix="/api/season", tags=["season"])


class SeasonOut(BaseModel):
    season: season_rules.Season
    # The calendar's answer before any snow adjustment.
    by_date: season_rules.Season
    adjusted_by_snow: bool
    # First day of the other season by date.
    next_change: date
    today: date


@router.get("", response_model=SeasonOut)
def get_season(
    response: Response,
    snow_depth_cm: float | None = Query(None, ge=0, le=2000),
    on: date | None = None,
):
    """The season today in Canada (or `on` a given day). A trail page can pass
    its trailhead's measured snow depth, which may tip the answer within a few
    weeks of a season change."""
    day = on or season_rules.today()
    result = season_rules.info(day, snow_depth_cm)
    # The same for everyone, and it changes at most daily.
    response.headers["Cache-Control"] = "public, max-age=600"
    return SeasonOut(season=result.season, by_date=result.by_date, adjusted_by_snow=result.adjusted_by_snow,
                     next_change=result.next_change, today=day)
