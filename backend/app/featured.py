"""Featured badges: what shows, and what may be picked.

Shared by the owner's endpoints (app/routers/me_featured_badges.py), the
public profile (app/routers/public_profiles.py) and hike deletion, so the
rules live in one place:

- Only earned badges: a trail the user has logged, or a milestone their
  logs earn (app/journal.py). No duplicates, at most MAX_FEATURED.
- Nothing picked: the most recent trail badges stand in. For visitors who
  can't see hike dates they're chosen by trail name instead, since "most
  recent" would hint at when.
- A pick that's no longer earned is never shown, and is deleted when the
  hike that earned it is.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.journal import MILESTONES, earned_milestones
from app.models.featured_badge import MAX_FEATURED, FeaturedBadge
from app.models.hike_log import HikeLog
from app.schemas.trail import TrailListItemOut


class FeaturedBadgeOut(BaseModel):
    kind: Literal["trail", "milestone"]
    trail: TrailListItemOut | None = None
    milestone: str | None = None


@dataclass(frozen=True)
class Pick:
    trail_id: UUID | None = None
    milestone: str | None = None


class BadgeChoiceError(ValueError):
    pass


def _logs(db: Session, user_id: UUID) -> list[HikeLog]:
    return db.scalars(
        select(HikeLog)
        .where(HikeLog.user_id == user_id)
        .options(joinedload(HikeLog.trail))
        .order_by(HikeLog.hiked_on.desc(), HikeLog.created_at.desc())
    ).all()


def featured_badges(db: Session, user_id: UUID, *, hide_dates: bool = False) -> tuple[bool, list[FeaturedBadgeOut]]:
    """(picked, badges): the user's own picks in order, or the stand-ins."""
    logs = _logs(db, user_id)
    by_trail = {log.trail_id: log for log in logs}
    earned = earned_milestones(log.trail for log in logs)
    rows = db.scalars(
        select(FeaturedBadge).where(FeaturedBadge.user_id == user_id).order_by(FeaturedBadge.position)
    ).all()
    if rows:
        shown = []
        for row in rows:
            if row.trail_id is not None and row.trail_id in by_trail:
                shown.append(FeaturedBadgeOut(kind="trail", trail=TrailListItemOut.model_validate(by_trail[row.trail_id].trail)))
            elif row.milestone is not None and row.milestone in earned:
                shown.append(FeaturedBadgeOut(kind="milestone", milestone=row.milestone))
        return True, shown
    if hide_dates:
        logs = sorted(logs, key=lambda log: log.trail.name.lower())
    return False, [
        FeaturedBadgeOut(kind="trail", trail=TrailListItemOut.model_validate(log.trail)) for log in logs[:MAX_FEATURED]
    ]


def set_featured(db: Session, user_id: UUID, picks: list[Pick]) -> None:
    """Replace the picks (an empty list goes back to the stand-ins). Raises BadgeChoiceError."""
    if len(picks) > MAX_FEATURED:
        raise BadgeChoiceError(f"Feature up to {MAX_FEATURED} badges.")
    keys = [(pick.trail_id, pick.milestone) for pick in picks]
    if len(set(keys)) != len(keys):
        raise BadgeChoiceError("Each badge can only be featured once.")
    logs = _logs(db, user_id)
    hiked = {log.trail_id for log in logs}
    earned = earned_milestones(log.trail for log in logs)
    for pick in picks:
        if (pick.trail_id is None) == (pick.milestone is None):
            raise BadgeChoiceError("Pick either a trail badge or a milestone badge.")
        if pick.trail_id is not None and pick.trail_id not in hiked:
            raise BadgeChoiceError("You can only feature badges you've earned: log the hike first.")
        if pick.milestone is not None and pick.milestone not in MILESTONES:
            raise BadgeChoiceError("That isn't a Trekly badge.")
        if pick.milestone is not None and pick.milestone not in earned:
            raise BadgeChoiceError("You can only feature badges you've earned.")
    db.execute(delete(FeaturedBadge).where(FeaturedBadge.user_id == user_id))
    # Flush the deletes first so the new positions don't collide with the old.
    db.flush()
    for position, pick in enumerate(picks):
        db.add(FeaturedBadge(user_id=user_id, position=position, trail_id=pick.trail_id, milestone=pick.milestone))
    db.commit()


def prune_featured(db: Session, user_id: UUID) -> None:
    """After a hike is deleted: drop milestone picks it no longer earns. Trail
    picks for that hike are already gone (the FK cascades)."""
    logs = _logs(db, user_id)
    earned = earned_milestones(log.trail for log in logs)
    # Belt and braces for trail picks, should the cascade ever be missing.
    hiked = {log.trail_id for log in logs}
    stale = [
        row.id
        for row in db.scalars(select(FeaturedBadge).where(FeaturedBadge.user_id == user_id))
        if (row.milestone is not None and row.milestone not in earned)
        or (row.trail_id is not None and row.trail_id not in hiked)
    ]
    if stale:
        db.execute(delete(FeaturedBadge).where(FeaturedBadge.id.in_(stale)))
        db.commit()
