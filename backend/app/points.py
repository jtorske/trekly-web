"""Points and ranks, computed from a user's hike logs on every request.

The values are in app/points_config.py. Nothing is stored: adding or
deleting a hike, or retuning the config, changes the result next time.
Only the owner sees points (app/routers/me_rank.py); visitors get the rank
name and level alone, and only when the owner shows their rank
(app/routers/public_profiles.py).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.journal import earned_milestones
from app.models.hike_log import HikeLog
from app.models.trail import Trail
from app.points_config import MILESTONE_POINTS, NEW_REGION_POINTS, POINTS_PER_NIGHT, RANKS, TRAIL_POINTS


@dataclass(frozen=True)
class Breakdown:
    trails: int
    nights: int
    regions: int
    milestones: int

    @property
    def total(self) -> int:
        return self.trails + self.nights + self.regions + self.milestones


@dataclass(frozen=True)
class Rank:
    level: int
    """1 (the first rank) up to len(RANKS)."""
    title: str
    threshold: int


def score(trails: Iterable[Trail]) -> Breakdown:
    """Points for having hiked these trails (one per hike log)."""
    trails = list(trails)
    return Breakdown(
        trails=sum(TRAIL_POINTS[trail.terrain_difficulty] for trail in trails),
        nights=sum(POINTS_PER_NIGHT * (trail.typical_duration_nights or 0) for trail in trails),
        regions=NEW_REGION_POINTS * len({trail.region for trail in trails}),
        milestones=MILESTONE_POINTS * len(earned_milestones(trails)),
    )


def rank_for(points: int) -> Rank:
    level = max(index for index, (threshold, _) in enumerate(RANKS) if points >= threshold)
    threshold, title = RANKS[level]
    return Rank(level=level + 1, title=title, threshold=threshold)


def next_rank(rank: Rank) -> Rank | None:
    if rank.level >= len(RANKS):
        return None
    threshold, title = RANKS[rank.level]
    return Rank(level=rank.level + 1, title=title, threshold=threshold)


def user_trails(db: Session, user_id: UUID) -> list[Trail]:
    logs = db.scalars(select(HikeLog).where(HikeLog.user_id == user_id).options(joinedload(HikeLog.trail))).all()
    return [log.trail for log in logs]


def user_rank(db: Session, user_id: UUID) -> tuple[Breakdown, Rank]:
    breakdown = score(user_trails(db, user_id))
    return breakdown, rank_for(breakdown.total)
