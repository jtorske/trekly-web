"""POST /api/me/visit: record that the signed-in user visited today.

The browser calls it once per app load, and at most once a day (it caches
the reply in sessionStorage). It sends only its IANA time zone; the server
works out the date and the counts (app/streaks.py), so a client can't set
its own streak. Repeat calls on the same day change nothing.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.models.visit_streak import VisitStreak
from app.streaks import MAX_TIME_ZONE_LENGTH, NO_STREAK, Streak, local_today, record_visit

router = APIRouter(prefix="/api/me", tags=["account"])


def now() -> datetime:
    """The server clock; tests replace it."""
    return datetime.now(timezone.utc)


class VisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # e.g. "America/Edmonton". Missing or unknown counts as UTC.
    time_zone: str | None = Field(default=None, max_length=MAX_TIME_ZONE_LENGTH)


class VisitOut(BaseModel):
    current_streak: int
    longest_streak: int
    # The date this visit counted for, in the user's time zone.
    today: date
    # True when this visit made the current streak longer (the icon animates once).
    grew: bool


def _record(db: Session, user_id, today: date) -> tuple[Streak, bool]:
    row = db.scalars(
        select(VisitStreak).where(VisitStreak.user_id == user_id).with_for_update()
    ).one_or_none()
    before = NO_STREAK if row is None else Streak(row.current_streak, row.longest_streak, row.last_visit_date)
    after, grew = record_visit(before, today)
    if after != before:
        if row is None:
            row = VisitStreak(user_id=user_id)
            db.add(row)
        row.current_streak = after.current
        row.longest_streak = after.longest
        row.last_visit_date = after.last_visit
    db.commit()
    return after, grew


@router.post("/visit", response_model=VisitOut)
def record_my_visit(
    payload: VisitIn,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    today = local_today(payload.time_zone, now())
    try:
        streak, grew = _record(db, user_id, today)
    except IntegrityError:
        # Another tab created the row first; its row is locked and read now.
        db.rollback()
        streak, grew = _record(db, user_id, today)
    return VisitOut(
        current_streak=streak.current,
        longest_streak=streak.longest,
        today=today,
        grew=grew,
    )
