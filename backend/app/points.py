"""Points and ranks, computed from a user's hike logs on every request.

The values are in app/points_config.py. Nothing is stored: adding or
deleting a hike, or retuning the config, changes the result next time.
Only the owner sees points (app/routers/me_rank.py); visitors get the rank
name and level alone, and only when the owner shows their rank
(app/routers/public_profiles.py).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.milestones import Facts, gather, milestone_points
from app.points_config import NEW_REGION_POINTS, POINTS_PER_NIGHT, RANKS, TRAIL_POINTS


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


def score(facts: Facts) -> Breakdown:
    """Points for a user's hikes, and the milestones (by tier) they've earned."""
    trails = facts.trails
    return Breakdown(
        trails=sum(TRAIL_POINTS[trail.terrain_difficulty] for trail in trails),
        nights=sum(POINTS_PER_NIGHT * (trail.typical_duration_nights or 0) for trail in trails),
        regions=NEW_REGION_POINTS * len({trail.region for trail in trails}),
        milestones=milestone_points(facts),
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


def user_rank(db: Session, user_id: UUID) -> tuple[Breakdown, Rank]:
    breakdown = score(gather(db, user_id))
    return breakdown, rank_for(breakdown.total)
