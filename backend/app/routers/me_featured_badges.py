"""The signed-in user's featured badges (up to three, in order).

GET returns what the profile shows: the user's picks, or their most recent
trail badges while they haven't picked any (`picked: false`). PUT replaces
the picks; an empty list goes back to the most recent. The rules are in
app/featured.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.featured import BadgeChoiceError, FeaturedBadgeOut, Pick, featured_badges, set_featured
from app.models.featured_badge import MAX_FEATURED

router = APIRouter(prefix="/api/me/featured-badges", tags=["trail journal"])


class BadgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trail_id: UUID | None = None
    milestone: str | None = Field(default=None, max_length=40)


class FeaturedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Over the limit is refused by the rules (with a clear message), not here.
    badges: list[BadgeIn] = Field(max_length=MAX_FEATURED * 4)


class FeaturedOut(BaseModel):
    picked: bool
    badges: list[FeaturedBadgeOut]


@router.get("", response_model=FeaturedOut)
def get_featured(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    picked, badges = featured_badges(db, user_id)
    return FeaturedOut(picked=picked, badges=badges)


@router.put("", response_model=FeaturedOut)
def put_featured(payload: FeaturedIn, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    try:
        set_featured(db, user_id, [Pick(trail_id=b.trail_id, milestone=b.milestone) for b in payload.badges])
    except BadgeChoiceError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    picked, badges = featured_badges(db, user_id)
    return FeaturedOut(picked=picked, badges=badges)
