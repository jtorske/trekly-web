"""Points and rank: the signed-in user's own, and the public rules.

GET /api/me/rank is the owner's points, rank, next rank and progress.
GET /api/ranks is how ranks work (the values in app/points_config.py),
the same for everyone; it says nothing about any user.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.points import next_rank, user_rank
from app.points_config import MILESTONE_POINTS, NEW_REGION_POINTS, POINTS_PER_NIGHT, RANKS, TRAIL_POINTS

router = APIRouter(tags=["ranks"])


class RankOut(BaseModel):
    level: int
    title: str
    threshold: int


class PointsBreakdownOut(BaseModel):
    trails: int
    nights: int
    regions: int
    milestones: int


class MyRankOut(BaseModel):
    points: int
    rank: RankOut
    # None at the top rank.
    next: RankOut | None
    # 0-1 from this rank's threshold to the next one's (1 at the top).
    progress: float
    breakdown: PointsBreakdownOut


class RankRulesOut(BaseModel):
    trail_points: dict[str, int]
    points_per_night: int
    new_region_points: int
    milestone_points: int
    ranks: list[RankOut]


@router.get("/api/me/rank", response_model=MyRankOut)
def get_my_rank(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    breakdown, rank = user_rank(db, user_id)
    upcoming = next_rank(rank)
    points = breakdown.total
    progress = 1.0 if upcoming is None else (points - rank.threshold) / (upcoming.threshold - rank.threshold)
    return MyRankOut(
        points=points,
        rank=RankOut(level=rank.level, title=rank.title, threshold=rank.threshold),
        next=None if upcoming is None else RankOut(level=upcoming.level, title=upcoming.title, threshold=upcoming.threshold),
        progress=round(progress, 4),
        breakdown=PointsBreakdownOut(
            trails=breakdown.trails, nights=breakdown.nights, regions=breakdown.regions, milestones=breakdown.milestones
        ),
    )


@router.get("/api/ranks", response_model=RankRulesOut)
def get_rank_rules():
    return RankRulesOut(
        trail_points=dict(TRAIL_POINTS),
        points_per_night=POINTS_PER_NIGHT,
        new_region_points=NEW_REGION_POINTS,
        milestone_points=MILESTONE_POINTS,
        ranks=[RankOut(level=i + 1, title=title, threshold=threshold) for i, (threshold, title) in enumerate(RANKS)],
    )
