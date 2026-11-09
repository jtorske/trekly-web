"""The signed-in user's Trail Journal milestones.

GET returns every milestone in journal order with the categories' headings:
earned or not (with the day it was first earned), and progress where a count
makes sense. The rules are in app/milestones.py, the definitions in
app/milestones_config.py, the dates in app/milestone_dates.py. Unearned
secret milestones come back as "???" with a hint and no id. Trail-data
milestones the catalogue can't support yet are flagged needs_data. Ones earned on the
strength of undated hikes say so in earned_with ("joining" when the hikes came
from onboarding).
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.milestone_dates import gather_earned_dates
from app.milestones import CategoryOut, MilestoneOut, evaluate, gather, milestone_out, needs_trail_data
from app.milestones_config import CATEGORIES, TIER_POINTS
from app.models.preferences import ProfilePreferences

router = APIRouter(prefix="/api/me/milestones", tags=["trail journal"])


class MilestonesOut(BaseModel):
    categories: list[CategoryOut]
    milestones: list[MilestoneOut]
    tier_points: dict[str, int]


@router.get("", response_model=MilestonesOut)
def get_my_milestones(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    facts = gather(db, user_id)
    results = evaluate(facts)
    waiting = needs_trail_data(facts)
    earned = gather_earned_dates(db, user_id, facts, results)
    # Onboarding's picks are added before it finishes; still going counts too.
    finished = db.scalar(select(ProfilePreferences.onboarding_finished_at).where(ProfilePreferences.user_id == user_id))

    def earned_with(milestone_id: str):
        if milestone_id not in earned.from_past_hikes:
            return None
        day = earned.dates[milestone_id]
        return "joining" if finished is None or day <= finished.date() else "past_hikes"

    used = {milestone.category for milestone, _ in results}
    return MilestonesOut(
        categories=[CategoryOut(id=key, title=title) for key, title in CATEGORIES if key in used],
        milestones=[
            milestone_out(m, result, m.id in waiting, earned.dates.get(m.id), earned_with(m.id)) for m, result in results
        ],
        tier_points=dict(TIER_POINTS),
    )
