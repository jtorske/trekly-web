"""The signed-in user's Trail Journal: which trails they've hiked, when, and
an optional note and photo.

Entries are keyed to the verified access token; others see them only on a
public profile (app/routers/public_profiles.py). One entry per
trail: PUT creates it or replaces its fields. Retired trails stay listed
for anyone who logged them.

POST /past adds hikes from before the user joined, with no date, many at
once (onboarding's "Which of these have you hiked?" and "Add past hikes").

Every new entry, one or many, goes through app/hike_service.add_hikes, which
evaluates the journal once and says what the hikes earned; both responses
carry that as `progress` (None when PUT only edits an entry).

Fair use: at most TODAY_LIMIT different trails dated today (or the day either
side, for time zones) per user, so nobody racks up a day of hikes they
couldn't have done. Hikes further back, and undated ones, are unlimited.

verified, match_score and nights come only from a matched GPS track. Editing
a verified hike's date drops its verification: the date no longer comes from
the track.
"""

import re
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user_id
from app.database import get_db
from app.featured import prune_featured
from app.hike_service import NewHike, Progress, add_hikes
from app.milestones import MilestoneBadgeOut, badge_out
from app.models.hike_log import MAX_NOTE_LENGTH, HikeLog
from app.models.trail import Trail
from app.routers.availability import get_today
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/me/hike-logs", tags=["trail journal"])

# Matches what the client uploads after resizing/re-encoding (see migration 739722285c4e).
PHOTO_NAME = re.compile(r"^[0-9a-f-]{36}\.(?:webp|jpg)$")
EARLIEST = date(1900, 1, 1)
# A user east of the server can already be on "tomorrow".
FUTURE_SLACK = timedelta(days=1)
# Different trails a user can log as hiked "today" (see the module docstring).
TODAY_LIMIT = 3
MAX_PAST_BATCH = 500


class HikeLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None: hiked before joining Trekly, date unknown.
    hiked_on: date | None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)
    photo_path: str | None = Field(default=None, max_length=200)

    @field_validator("note", mode="before")
    @classmethod
    def _clean_note(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class HikeLogOut(BaseModel):
    trail: TrailListItemOut
    hiked_on: date | None
    note: str | None
    photo_path: str | None
    # Matched against a GPS track.
    verified: bool
    # The track's nights for an overnight trip; None means the trail's typical nights.
    nights: int | None
    logged_at: datetime
    updated_at: datetime


class PastHikesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trail_ids: list[UUID] = Field(min_length=1, max_length=MAX_PAST_BATCH)


class RankBriefOut(BaseModel):
    level: int
    title: str


class JournalProgressOut(BaseModel):
    """What new hikes changed, from one evaluation of the whole journal."""

    # Trails in the journal now.
    stamps: int
    new_stamps: int
    # Earned by these hikes, in journal order.
    new_milestones: list[MilestoneBadgeOut]
    milestones_earned: int
    points: int
    points_gained: int
    rank: RankBriefOut
    ranked_up: bool


def progress_out(progress: Progress) -> JournalProgressOut:
    before, after = progress.before, progress.after
    return JournalProgressOut(
        stamps=after.stamps,
        new_stamps=after.stamps - before.stamps,
        new_milestones=[badge_out(m) for m in progress.new_milestones],
        milestones_earned=len(after.earned),
        points=after.points,
        points_gained=after.points - before.points,
        rank=RankBriefOut(level=after.rank.level, title=after.rank.title),
        ranked_up=progress.ranked_up,
    )


class HikeSavedOut(HikeLogOut):
    # Set when the entry is new; None for an edit.
    progress: JournalProgressOut | None = None


class PastHikesOut(BaseModel):
    added: list[HikeLogOut]
    # Already in the journal (left as they were), retired or unknown.
    skipped: int
    progress: JournalProgressOut


def _out(log: HikeLog) -> HikeLogOut:
    return HikeLogOut(
        trail=TrailListItemOut.model_validate(log.trail),
        hiked_on=log.hiked_on,
        note=log.note,
        photo_path=log.photo_path,
        verified=bool(log.verified),
        nights=log.nights,
        logged_at=log.created_at,
        updated_at=log.updated_at,
    )


def check_fair_use(db: Session, user_id: UUID, trail_id: UUID, hiked_on: date | None, today: date) -> None:
    """Refuse a hike dated around today once TODAY_LIMIT other trails already are.
    "Around today" is a day either side, the slack the date check allows."""
    if hiked_on is None or abs((hiked_on - today).days) > 1:
        return
    recent = db.scalar(
        select(func.count())
        .select_from(HikeLog)
        .where(
            HikeLog.user_id == user_id,
            HikeLog.trail_id != trail_id,
            HikeLog.hiked_on.between(today - timedelta(days=1), today + FUTURE_SLACK),
        )
    ) or 0
    if recent >= TODAY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've already logged {TODAY_LIMIT} hikes for today. "
            "If this one was on another day, pick that date.",
        )


def _apply(log: HikeLog, payload: HikeLogIn) -> None:
    if log.verified and payload.hiked_on != log.hiked_on:
        log.verified, log.match_score, log.nights = False, None, None
    log.hiked_on, log.note, log.photo_path = payload.hiked_on, payload.note, payload.photo_path


def _find(db: Session, user_id: UUID, trail_id: UUID) -> HikeLog | None:
    return db.scalar(
        select(HikeLog)
        .where(HikeLog.user_id == user_id, HikeLog.trail_id == trail_id)
        .options(joinedload(HikeLog.trail))
    )


@router.get("", response_model=list[HikeLogOut])
def list_hike_logs(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(HikeLog)
        .where(HikeLog.user_id == user_id)
        .options(joinedload(HikeLog.trail))
        .order_by(HikeLog.hiked_on.desc().nulls_last(), HikeLog.created_at.desc())
    ).all()
    return [_out(row) for row in rows]


@router.put("/{trail_id}", response_model=HikeSavedOut)
def put_hike_log(
    trail_id: UUID,
    payload: HikeLogIn,
    response: Response,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Create (201) or replace (200) the entry for this trail.

    Retired trails can't be newly logged, but an existing entry on one can
    still be edited.
    """
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    if payload.hiked_on is not None and payload.hiked_on > today + FUTURE_SLACK:
        raise HTTPException(status_code=422, detail="The hike date can't be in the future.")
    if payload.hiked_on is not None and payload.hiked_on < EARLIEST:
        raise HTTPException(status_code=422, detail="Pick a date after 1900.")
    if payload.photo_path is not None:
        folder, _, name = payload.photo_path.partition("/")
        if folder != str(user_id) or not PHOTO_NAME.match(name):
            raise HTTPException(status_code=422, detail="Photos must be uploaded to your own folder.")

    log = _find(db, user_id, trail_id)
    if log is None or log.hiked_on != payload.hiked_on:
        check_fair_use(db, user_id, trail_id, payload.hiked_on, today)
    if log is None:
        if trail.retired_at is not None:
            raise HTTPException(status_code=409, detail="This trail has been retired and can't be added.")
        result = add_hikes(
            db, user_id, [NewHike(trail_id, payload.hiked_on, payload.note, payload.photo_path)]
        )
        if result.added:
            response.status_code = status.HTTP_201_CREATED
            return HikeSavedOut(**_out(result.added[0]).model_dump(), progress=progress_out(result.progress))
        # A concurrent duplicate request created it first; apply this one on top.
        log = _find(db, user_id, trail_id)
    _apply(log, payload)
    db.commit()
    return HikeSavedOut(**_out(_find(db, user_id, trail_id)).model_dump())


@router.post("/past", response_model=PastHikesOut, status_code=status.HTTP_201_CREATED)
def add_past_hikes(
    payload: PastHikesIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Add undated hikes from before Trekly. A trail already in the journal
    keeps its entry (a date is never dropped), and retired or unknown trails
    are skipped, so a retry adds nothing twice. The journal is evaluated once
    for the whole batch."""
    result = add_hikes(db, user_id, [NewHike(trail_id) for trail_id in payload.trail_ids])
    added = sorted(result.added, key=lambda log: log.trail.name.lower())
    return PastHikesOut(added=[_out(log) for log in added], skipped=result.skipped, progress=progress_out(result.progress))


@router.delete("/{trail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hike_log(
    trail_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Idempotent: removing a trail that isn't logged still returns 204. The
    client removes the entry's photo from Storage itself. Its featured badge
    goes with it, as do milestone badges it no longer earns."""
    db.execute(delete(HikeLog).where(HikeLog.user_id == user_id, HikeLog.trail_id == trail_id))
    db.commit()
    prune_featured(db, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
