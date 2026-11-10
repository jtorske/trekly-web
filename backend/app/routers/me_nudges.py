"""The signed-in user's nudges toward the community settings (app/nudges.py).

GET lists the ones to show now; PUT puts one away for good. Neither ever
changes a setting: turning one on goes through PATCH /api/me/privacy, like
everywhere else, which also puts its nudges away.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.nudges import active, commit_quietly, dismiss

router = APIRouter(prefix="/api/me/nudges", tags=["account"])

Nudge = Literal["hike_share", "activity_card", "hiked_by"]


class NudgesOut(BaseModel):
    active: list[Nudge]


@router.get("", response_model=NudgesOut)
def get_nudges(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return NudgesOut(active=active(db, user.id))


@router.put("/{nudge}/dismissed", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_nudge(nudge: Nudge, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    dismiss(db, user.id, nudge)
    commit_quietly(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
