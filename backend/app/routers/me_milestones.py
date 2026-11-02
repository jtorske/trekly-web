"""The signed-in user's Trail Journal milestones.

GET returns every milestone in journal order with the categories' headings:
earned or not, and progress where a count makes sense. The rules are in
app/milestones.py, the definitions in app/milestones_config.py. Unearned
secret milestones come back as "???" with a hint and no id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.milestones import CategoryOut, MilestoneOut, evaluate, gather, milestone_out
from app.milestones_config import CATEGORIES, TIER_POINTS

router = APIRouter(prefix="/api/me/milestones", tags=["trail journal"])


class MilestonesOut(BaseModel):
    categories: list[CategoryOut]
    milestones: list[MilestoneOut]
    tier_points: dict[str, int]


@router.get("", response_model=MilestonesOut)
def get_my_milestones(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    results = evaluate(gather(db, user_id))
    used = {milestone.category for milestone, _ in results}
    return MilestonesOut(
        categories=[CategoryOut(id=key, title=title) for key, title in CATEGORIES if key in used],
        milestones=[milestone_out(milestone, result) for milestone, result in results],
        tier_points=dict(TIER_POINTS),
    )
