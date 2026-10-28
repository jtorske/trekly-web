"""The signed-in user's Trail Journal: which trails they've hiked, when, and
an optional note and photo.

Entries are keyed to the verified access token; others see them only on a
public profile (app/routers/public_profiles.py). One entry per
trail: PUT creates it or replaces its fields. Retired trails stay listed
for anyone who logged them.
"""

import re
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user_id
from app.database import get_db
from app.featured import prune_featured
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


class HikeLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hiked_on: date
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
    hiked_on: date
    note: str | None
    photo_path: str | None
    logged_at: datetime
    updated_at: datetime


def _out(log: HikeLog) -> HikeLogOut:
    return HikeLogOut(
        trail=TrailListItemOut.model_validate(log.trail),
        hiked_on=log.hiked_on,
        note=log.note,
        photo_path=log.photo_path,
        logged_at=log.created_at,
        updated_at=log.updated_at,
    )


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
        .order_by(HikeLog.hiked_on.desc(), HikeLog.created_at.desc())
    ).all()
    return [_out(row) for row in rows]


@router.put("/{trail_id}", response_model=HikeLogOut)
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
    if payload.hiked_on > today + FUTURE_SLACK:
        raise HTTPException(status_code=422, detail="The hike date can't be in the future.")
    if payload.hiked_on < EARLIEST:
        raise HTTPException(status_code=422, detail="Pick a date after 1900.")
    if payload.photo_path is not None:
        folder, _, name = payload.photo_path.partition("/")
        if folder != str(user_id) or not PHOTO_NAME.match(name):
            raise HTTPException(status_code=422, detail="Photos must be uploaded to your own folder.")

    log = _find(db, user_id, trail_id)
    if log is None:
        if trail.retired_at is not None:
            raise HTTPException(status_code=409, detail="This trail has been retired and can't be added.")
        log = HikeLog(user_id=user_id, trail_id=trail_id)
        db.add(log)
        response.status_code = status.HTTP_201_CREATED
    log.hiked_on = payload.hiked_on
    log.note = payload.note
    log.photo_path = payload.photo_path
    try:
        db.commit()
    except IntegrityError:
        # A concurrent duplicate request created it first; apply this one on top.
        db.rollback()
        log = _find(db, user_id, trail_id)
        log.hiked_on, log.note, log.photo_path = payload.hiked_on, payload.note, payload.photo_path
        db.commit()
        response.status_code = status.HTTP_200_OK
    return _out(_find(db, user_id, trail_id))


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
