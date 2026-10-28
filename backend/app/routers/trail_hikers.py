"""'Hiked by' on trail pages: opted-in hikers who logged a trail, and their notes.

Someone is listed only while app.privacy.in_community holds for them (a
public profile with the Trail Journal shown, and "Show me in community
features" on). Row-level security applies the same rule to direct Supabase
access (migration 9d4f2a6c8e13). Nothing is cached, so turning a setting
off removes them from the very next response.

Like the public journal, nothing here hints at when someone who hides
their dates went: they're listed after everyone with dates, by username,
and their notes carry no date.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Profile
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileSettings
from app.models.trail import Trail
from app.privacy import in_community

router = APIRouter(prefix="/api/trails", tags=["trails"])

MAX_HIKERS = 8
MAX_NOTES = 3


class CommunityHiker(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None


class CommunityNote(CommunityHiker):
    note: str
    # None when they hide the dates of their hikes.
    hiked_on: date | None
    # Their journal is public whenever they're listed here, so this is a
    # photo visitors can already see on it (storage RLS agrees).
    photo_path: str | None


class TrailHikersOut(BaseModel):
    hikers: list[CommunityHiker]
    # How many more opted-in hikers there are beyond `hikers`.
    others: int
    notes: list[CommunityNote]


def _listed(trail_id: UUID):
    hide = ProfileSettings.hide_hike_dates
    return (
        select(HikeLog, Profile, hide)
        .join(Profile, Profile.id == HikeLog.user_id)
        .join(ProfileSettings, ProfileSettings.user_id == HikeLog.user_id)
        .where(HikeLog.trail_id == trail_id, in_community(HikeLog.user_id))
        .order_by(
            hide,
            case((hide, None), else_=HikeLog.hiked_on).desc().nulls_last(),
            case((hide, None), else_=HikeLog.created_at).desc().nulls_last(),
            Profile.username,
        )
    )


def _hiker(profile: Profile) -> dict:
    return {"username": profile.username, "display_name": profile.display_name, "avatar_path": profile.avatar_path}


@router.get("/{trail_id}/hikers", response_model=TrailHikersOut)
def trail_hikers(trail_id: UUID, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if db.get(Trail, trail_id) is None:
        raise HTTPException(status_code=404, detail="Trail not found")

    total = db.scalar(
        select(func.count()).select_from(HikeLog).where(HikeLog.trail_id == trail_id, in_community(HikeLog.user_id))
    ) or 0
    hikers = [CommunityHiker(**_hiker(profile)) for _, profile, _ in db.execute(_listed(trail_id).limit(MAX_HIKERS))]
    notes = [
        CommunityNote(
            **_hiker(profile),
            note=log.note,
            hiked_on=None if hide_dates else log.hiked_on,
            photo_path=log.photo_path,
        )
        for log, profile, hide_dates in db.execute(
            _listed(trail_id).where(HikeLog.note.is_not(None)).limit(MAX_NOTES)
        )
    ]
    return TrailHikersOut(hikers=hikers, others=max(total - len(hikers), 0), notes=notes)
