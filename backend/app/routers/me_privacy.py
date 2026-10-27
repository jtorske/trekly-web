"""The signed-in user's public-profile privacy settings (Settings → Privacy).

Changes apply immediately: nothing caches visibility (app/privacy.py).
Availability alerts have no setting; they're always private.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.models.account import Profile
from app.models.privacy import ProfileModeration
from app.privacy import ensure_settings

router = APIRouter(prefix="/api/me/privacy", tags=["account"])


class PrivacyOut(BaseModel):
    is_private: bool
    show_journal: bool
    show_rank: bool
    show_gear: bool
    show_saved_trails: bool
    show_trip_plans: bool
    hide_hike_dates: bool
    allow_search_indexing: bool
    public_notice_pending: bool
    username: str | None
    hidden_by_moderators: bool


class PrivacyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_private: bool | None = None
    show_journal: bool | None = None
    show_rank: bool | None = None
    show_gear: bool | None = None
    show_saved_trails: bool | None = None
    show_trip_plans: bool | None = None
    hide_hike_dates: bool | None = None
    allow_search_indexing: bool | None = None
    # The one-time notice can only be dismissed, never brought back.
    public_notice_pending: Literal[False] | None = None


def _out(db: Session, user: CurrentUser) -> PrivacyOut:
    settings = ensure_settings(db, user.id)
    profile = db.get(Profile, user.id)
    return PrivacyOut(
        **{field: getattr(settings, field) for field in PrivacyUpdate.model_fields},
        username=profile.username if profile else None,
        hidden_by_moderators=db.get(ProfileModeration, user.id) is not None,
    )


@router.get("", response_model=PrivacyOut)
def get_privacy(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.patch("", response_model=PrivacyOut)
def update_privacy(
    payload: PrivacyUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = ensure_settings(db, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(settings, field, value)
    db.commit()
    return _out(db, user)
