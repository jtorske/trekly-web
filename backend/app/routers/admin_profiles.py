"""Profile moderation: admins hide (and unhide) public profiles.

Admins are the user ids in ADMIN_USER_IDS or PHOTO_ADMIN_USER_IDS
(app/config.py), checked here on every request, never only in the UI. A
hidden profile is a 404 for everyone else, through the API and through
row-level security (private.section_visible).
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.config import admin_user_ids
from app.database import get_db
from app.models.account import Profile
from app.models.privacy import ProfileModeration

router = APIRouter(prefix="/api/admin/profiles", tags=["admin"])


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if str(user.id).lower() not in admin_user_ids():
        raise HTTPException(status_code=403, detail="Only Trekly admins can do that.")
    return user


class HiddenProfileOut(BaseModel):
    user_id: UUID
    username: str | None
    display_name: str | None
    hidden_at: datetime
    reason: str | None


class HideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


def _by_username(db: Session, username: str) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.username == username.strip().lower()))
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _out(db: Session, row: ProfileModeration) -> HiddenProfileOut:
    profile = db.get(Profile, row.user_id)
    return HiddenProfileOut(
        user_id=row.user_id,
        username=profile.username if profile else None,
        display_name=profile.display_name if profile else None,
        hidden_at=row.hidden_at,
        reason=row.reason,
    )


@router.get("/hidden", response_model=list[HiddenProfileOut])
def list_hidden(_: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ProfileModeration).order_by(ProfileModeration.hidden_at.desc())).all()
    return [_out(db, row) for row in rows]


@router.put("/{username}/hidden", response_model=HiddenProfileOut)
def hide_profile(
    username: str,
    payload: HideIn,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    profile = _by_username(db, username)
    row = db.get(ProfileModeration, profile.id)
    if row is None:
        row = ProfileModeration(user_id=profile.id, hidden_by=admin.id, hidden_at=datetime.now().astimezone())
        db.add(row)
    row.reason = (payload.reason or "").strip() or None
    db.commit()
    return _out(db, row)


@router.delete("/{username}/hidden", status_code=status.HTTP_204_NO_CONTENT)
def unhide_profile(username: str, _: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    profile = _by_username(db, username)
    row = db.get(ProfileModeration, profile.id)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
