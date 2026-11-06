"""Points and ranks, computed from a user's hike logs on every request.

The values are in app/points_config.py. Nothing is stored: adding or
deleting a hike, or retuning the config, changes the result next time.
Only the owner sees points (app/routers/me_rank.py); visitors get the rank
name and level alone, and only when the owner shows their rank
(app/routers/public_profiles.py).

Ranks are personal: every hike counts, including undated ones from before
Trekly and ones that were never GPS-verified, because nobody else's standing
depends on them.

COMPETITIVE FEATURES MUST COUNT VERIFIED HIKES ONLY. Anything that compares
users or awards a place against others (leaderboards, challenges, "first to
hike", contests) must use verified_hikes() below, never facts.hikes or
user_rank(). Unverified hikes are self-reported, and the only limit on them
is the "a few hikes dated today" fair-use check (app/routers/me_hike_logs.py),
which bulk past entries don't have.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.milestones import Facts, Hike, gather, milestone_points
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


def verified_hikes(facts: Facts) -> list[Hike]:
    """The hikes a competitive feature may count (see the module docstring)."""
    return [hike for hike in facts.hikes if hike.verified]


def score(facts: Facts) -> Breakdown:
    """Points for a user's hikes, and the milestones (by tier) they've earned.

    Personal rank only. A leaderboard or challenge must score
    verified_hikes(facts) instead (see the module docstring)."""
    trails = facts.trails
    return Breakdown(
        trails=sum(TRAIL_POINTS[trail.terrain_difficulty] for trail in trails),
        nights=sum(POINTS_PER_NIGHT * hike.nights for hike in facts.hikes),
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
