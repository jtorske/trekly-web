"""The signed-in user's private trail preferences, /welcome progress, and the
trail picks those answers drive.

Owner-only: there is no route that shows these to anyone else, and the public
profile (app/routers/public_profiles.py) never reads this table.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.models.account import Profile, SavedTrail
from app.models.preferences import ProfilePreferences
from app.models.trail import Trail
from app.preferences import (
    INTERESTS,
    ONBOARDING_STEPS,
    REGION_SLUGS,
    Preferences,
    recommend,
)
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/me", tags=["preferences"])

HikingStyle = Literal["day", "overnight", "both"]
Experience = Literal["new", "few_seasons", "seasoned"]
OnboardingStep = Literal[ONBOARDING_STEPS]  # type: ignore[valid-type]
OnboardingOutcome = Literal["completed", "skipped"]


class OnboardingOut(BaseModel):
    step: str | None
    status: OnboardingOutcome | None
    finished_at: datetime | None


class PreferencesOut(BaseModel):
    hiking_style: HikingStyle | None
    experience: Experience | None
    interests: list[str]
    favourite_regions: list[str]
    onboarding: OnboardingOut


def _unique_in(allowed: tuple[str, ...], label: str):
    def check(values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        unknown = [value for value in values if value not in allowed]
        if unknown:
            raise ValueError(f"Unknown {label}: {', '.join(unknown)}")
        # Keep the order they were picked in, once each.
        return list(dict.fromkeys(values))

    return check


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hiking_style: HikingStyle | None = None
    experience: Experience | None = None
    interests: list[str] | None = Field(default=None, max_length=len(INTERESTS))
    favourite_regions: list[str] | None = Field(default=None, max_length=len(REGION_SLUGS))
    onboarding_step: OnboardingStep | None = None
    # Finishing or "Skip for now". Once set it stays: the flow shows once.
    onboarding_status: OnboardingOutcome | None = None

    _check_interests = field_validator("interests")(_unique_in(INTERESTS, "interest"))
    _check_regions = field_validator("favourite_regions")(_unique_in(REGION_SLUGS, "region"))

    @field_validator("onboarding_status", mode="before")
    @classmethod
    def _no_reopening(cls, value):
        if value is None:
            raise ValueError("The setup flow can be finished or skipped, not reopened.")
        return value


def get_preferences_row(db: Session, user_id: UUID) -> ProfilePreferences | None:
    return db.get(ProfilePreferences, user_id)


def _ensure_row(db: Session, user_id: UUID) -> ProfilePreferences:
    row = db.get(ProfilePreferences, user_id)
    if row is not None:
        return row
    db.add(ProfilePreferences(user_id=user_id, interests=[], favourite_regions=[]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # created by a concurrent request
    return db.get(ProfilePreferences, user_id)


def preferences_out(row: ProfilePreferences | None) -> PreferencesOut:
    if row is None:
        return PreferencesOut(
            hiking_style=None,
            experience=None,
            interests=[],
            favourite_regions=[],
            onboarding=OnboardingOut(step=None, status=None, finished_at=None),
        )
    return PreferencesOut(
        hiking_style=row.hiking_style,
        experience=row.experience,
        interests=list(row.interests or []),
        favourite_regions=list(row.favourite_regions or []),
        onboarding=OnboardingOut(
            step=row.onboarding_step, status=row.onboarding_status, finished_at=row.onboarding_finished_at
        ),
    )


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return preferences_out(get_preferences_row(db, user.id))


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _ensure_row(db, user.id)
    data = payload.model_dump(exclude_unset=True)
    status = data.pop("onboarding_status", None)
    for field, value in data.items():
        setattr(row, field, value)
    if status and row.onboarding_status is None:
        row.onboarding_status = status
        row.onboarding_finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return preferences_out(row)


@router.get("/recommendations", response_model=list[TrailListItemOut])
def get_recommendations(
    limit: int = Query(default=5, ge=1, le=12),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trails picked for this person from their answers and home province,
    leaving out ones they've already saved."""
    row = get_preferences_row(db, user.id)
    profile = db.get(Profile, user.id)
    prefs = Preferences(
        hiking_style=row.hiking_style if row else None,
        experience=row.experience if row else None,
        interests=tuple(row.interests or ()) if row else (),
        favourite_regions=tuple(row.favourite_regions or ()) if row else (),
        home_province=profile.home_province if profile else None,
    )
    saved = select(SavedTrail.trail_id).where(SavedTrail.user_id == user.id)
    trails = db.scalars(select(Trail).where(Trail.retired_at.is_(None), Trail.id.not_in(saved))).all()
    return [TrailListItemOut.model_validate(trail) for trail in recommend(trails, prefs, limit)]
