"""'Hiked by' on trail pages: opted-in hikers who logged a trail, and their notes.

Someone is listed only while app.privacy.in_community holds for them (a
public profile with the Trail Journal shown, and "Show me in community
features" on), and only if they're a real hiker: demo accounts never count
as having hiked a trail (app/account_labels.py). Row-level security applies the same rule to direct Supabase
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

from app import follows
from app.auth import CurrentUser
from app.database import get_db
from app.follows import FollowState
from app.models.account import Profile
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileSettings
from app.models.trail import Trail
from app.account_labels import real_user
from app.privacy import in_community
from app.routers.activity import optional_user

router = APIRouter(prefix="/api/trails", tags=["trails"])

MAX_HIKERS = 8
MAX_NOTES = 3


class CommunityHiker(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    # Signed in: whether you follow them (None for yourself and for guests).
    follow: FollowState | None = None


class CommunityNote(CommunityHiker):
    note: str
    # None when they hide the dates of their hikes, or it's from before they joined.
    hiked_on: date | None
    # Matched against a GPS track.
    verified: bool
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
        .where(HikeLog.trail_id == trail_id, in_community(HikeLog.user_id), real_user(HikeLog.user_id))
        .order_by(
            hide,
            case((hide, None), else_=HikeLog.hiked_on).desc().nulls_last(),
            case((hide, None), else_=HikeLog.created_at).desc().nulls_last(),
            Profile.username,
        )
    )


def _hiker(profile: Profile, viewer_id: UUID | None, states: dict) -> dict:
    return {
        "username": profile.username, "display_name": profile.display_name, "avatar_path": profile.avatar_path,
        "follow": None if viewer_id is None or profile.id == viewer_id else states.get(profile.id, "none"),
    }


@router.get("/{trail_id}/hikers", response_model=TrailHikersOut)
def trail_hikers(
    trail_id: UUID,
    response: Response,
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    if db.get(Trail, trail_id) is None:
        raise HTTPException(status_code=404, detail="Trail not found")

    total = db.scalar(
        select(func.count()).select_from(HikeLog).where(
            HikeLog.trail_id == trail_id, in_community(HikeLog.user_id), real_user(HikeLog.user_id)
        )
    ) or 0
    viewer_id = viewer.id if viewer else None
    hiker_rows = db.execute(_listed(trail_id).limit(MAX_HIKERS)).all()
    note_rows = db.execute(_listed(trail_id).where(HikeLog.note.is_not(None)).limit(MAX_NOTES)).all()
    states = follows.states(db, viewer_id, {p.id for _, p, _ in hiker_rows} | {p.id for _, p, _ in note_rows})
    hikers = [CommunityHiker(**_hiker(profile, viewer_id, states)) for _, profile, _ in hiker_rows]
    notes = [
        CommunityNote(
            **_hiker(profile, viewer_id, states),
            note=log.note,
            hiked_on=None if hide_dates else log.hiked_on,
            verified=bool(log.verified),
            photo_path=log.photo_path,
        )
        for log, profile, hide_dates in note_rows
    ]
    return TrailHikersOut(hikers=hikers, others=max(total - len(hikers), 0), notes=notes)
