"""The signed-in user's profile, saved trails and account lifecycle.

Identity always comes from the verified access token. Saved trails are
bookmarks — they are not trips, packing lists or completed hikes.
"""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.models.account import USERNAME_PATTERN, Profile, SavedTrail
from app.models.setup import GearSetup
from app.models.trail import Trail
from app.models.user_gear import UserGearItem
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/me", tags=["account"])

AVATAR_NAME = re.compile(r"^[0-9a-f-]{36}\.(?:jpg|jpeg|png|webp)$")
DELETE_CONFIRMATION = "delete my account"


class ProfileCounts(BaseModel):
    saved_trails: int
    gear_items: int


class ProfileOut(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    username: str | None
    bio: str | None
    home_region: str | None
    avatar_path: str | None
    member_since: datetime | None
    counts: ProfileCounts
    visibility: Literal["private"] = "private"


def _clean(value):
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=60)
    username: str | None = Field(default=None, max_length=30)
    bio: str | None = Field(default=None, max_length=280)
    home_region: str | None = Field(default=None, max_length=80)
    avatar_path: str | None = Field(default=None, max_length=200)

    _clean_fields = field_validator("display_name", "home_region", mode="before")(_clean)

    @field_validator("bio", mode="before")
    @classmethod
    def _clean_bio(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("username", mode="before")
    @classmethod
    def _clean_username(cls, value):
        if isinstance(value, str):
            value = value.strip().lower() or None
        if value is not None and not re.fullmatch(USERNAME_PATTERN, value):
            raise ValueError("Use 3–30 lowercase letters, numbers or underscores.")
        return value


class SavedTrailOut(BaseModel):
    trail: TrailListItemOut
    saved_at: datetime


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _ensure_profile(db: Session, user_id: UUID) -> Profile:
    """The signup trigger creates profiles; this self-heals any that are missing."""
    profile = db.get(Profile, user_id)
    if profile is not None:
        return profile
    profile = Profile(id=user_id)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # created concurrently by the trigger or another request
    return db.get(Profile, user_id)


def _profile_out(db: Session, user: CurrentUser, profile: Profile) -> ProfileOut:
    member_since = None
    if _is_postgres(db):
        member_since = db.scalar(
            text("select created_at from auth.users where id = :id"), {"id": user.id}
        )
    counts = ProfileCounts(
        saved_trails=db.scalar(
            select(func.count()).select_from(SavedTrail).where(SavedTrail.user_id == user.id)
        )
        or 0,
        gear_items=db.scalar(
            select(func.count()).select_from(UserGearItem).where(UserGearItem.user_id == user.id)
        )
        or 0,
    )
    return ProfileOut(
        id=profile.id,
        email=user.email,
        display_name=profile.display_name,
        username=profile.username,
        bio=profile.bio,
        home_region=profile.home_region,
        avatar_path=profile.avatar_path,
        member_since=member_since or profile.created_at,
        counts=counts,
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _profile_out(db, user, _ensure_profile(db, user.id))


@router.patch("/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _ensure_profile(db, user.id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("avatar_path") is not None:
        folder, _, name = data["avatar_path"].partition("/")
        if folder != str(user.id) or not AVATAR_NAME.match(name):
            raise HTTPException(status_code=422, detail="Avatars must be uploaded to your own folder.")
    if data.get("username"):
        taken = db.scalar(
            select(Profile.id).where(Profile.username == data["username"], Profile.id != user.id)
        )
        if taken is not None:
            raise HTTPException(status_code=409, detail="That username is taken.")
    for field, value in data.items():
        setattr(profile, field, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Lost a race for the same username.
        raise HTTPException(status_code=409, detail="That username is taken.") from error
    db.refresh(profile)
    return _profile_out(db, user, profile)


@router.get("/saved-trails", response_model=list[SavedTrailOut])
def list_saved_trails(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(SavedTrail)
        .where(SavedTrail.user_id == user.id)
        .options(joinedload(SavedTrail.trail))
        .order_by(SavedTrail.created_at.desc())
    ).all()
    return [
        SavedTrailOut(trail=TrailListItemOut.model_validate(row.trail), saved_at=row.created_at)
        for row in rows
    ]


@router.put("/saved-trails/{trail_id}", response_model=SavedTrailOut)
def save_trail(
    trail_id: UUID,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotent: saving an already-saved trail returns 200 with the existing bookmark."""
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    existing = db.get(SavedTrail, (user.id, trail_id))
    if existing is None:
        existing = SavedTrail(user_id=user.id, trail_id=trail_id)
        db.add(existing)
        try:
            db.commit()
            response.status_code = status.HTTP_201_CREATED
        except IntegrityError:
            db.rollback()  # a concurrent duplicate request saved it first
        existing = db.get(SavedTrail, (user.id, trail_id))
    return SavedTrailOut(trail=TrailListItemOut.model_validate(trail), saved_at=existing.created_at)


@router.delete("/saved-trails/{trail_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_trail(
    trail_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotent: removing a trail that isn't saved still returns 204."""
    db.execute(
        delete(SavedTrail).where(SavedTrail.user_id == user.id, SavedTrail.trail_id == trail_id)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the account and everything it owns.

    Removes the user's gear inventory, saved trails and profile, then the
    Supabase auth user itself. Uploaded photos are removed by the client
    through the Storage API beforehand (Storage files can't be deleted from
    SQL without orphaning the underlying objects). Shared catalogue data is
    never touched.
    """
    if payload.confirm.strip().lower() != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=422, detail=f'Type "{DELETE_CONFIRMATION}" to confirm.'
        )
    for setup in db.scalars(select(GearSetup).where(GearSetup.user_id == user.id)):
        db.delete(setup)
    db.flush()
    db.execute(delete(UserGearItem).where(UserGearItem.user_id == user.id))
    db.execute(delete(SavedTrail).where(SavedTrail.user_id == user.id))
    db.execute(delete(Profile).where(Profile.id == user.id))
    if _is_postgres(db):
        db.execute(text("delete from auth.users where id = :id"), {"id": user.id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
