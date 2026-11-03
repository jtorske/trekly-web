"""Featured badges: what shows, and what may be picked.

Shared by the owner's endpoints (app/routers/me_featured_badges.py), the
public profile (app/routers/public_profiles.py) and hike deletion, so the
rules live in one place:

- Only earned badges: a trail the user has logged, a milestone they've
  earned (app/milestones.py), or their home province badge while they have
  a home province set. No duplicates, at most MAX_FEATURED.
- The province badge shows only to viewers who may see the province: the
  owner, and visitors while "Home province" is on in Settings > Privacy.
  Callers pass the province the viewer may see, or None.
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

from app.milestones import MilestoneBadgeOut, badge_out, earned_ids, gather
from app.milestones_config import BY_ID
from app.models.featured_badge import MAX_FEATURED, FeaturedBadge
from app.models.hike_log import HikeLog
from app.provinces import PROVINCE_BADGE
from app.schemas.trail import TrailListItemOut


class FeaturedBadgeOut(BaseModel):
    kind: Literal["trail", "milestone", "province"]
    trail: TrailListItemOut | None = None
    milestone: str | None = None
    # The milestone's name, tier and icon, for milestone badges.
    badge: MilestoneBadgeOut | None = None
    # The two-letter code, for the province badge.
    province: str | None = None


@dataclass(frozen=True)
class Pick:
    trail_id: UUID | None = None
    milestone: str | None = None
    province: bool = False

    @property
    def stored_milestone(self) -> str | None:
        # The province badge lives in the milestone column under its own id.
        return PROVINCE_BADGE if self.province else self.milestone


class BadgeChoiceError(ValueError):
    pass


def _logs(db: Session, user_id: UUID) -> list[HikeLog]:
    return db.scalars(
        select(HikeLog)
        .where(HikeLog.user_id == user_id)
        .options(joinedload(HikeLog.trail))
        .order_by(HikeLog.hiked_on.desc(), HikeLog.created_at.desc())
    ).all()


def featured_badges(
    db: Session, user_id: UUID, *, hide_dates: bool = False, province: str | None = None
) -> tuple[bool, list[FeaturedBadgeOut]]:
    """(picked, badges): the user's own picks in order, or the stand-ins.
    `province` is the home province this viewer may see (None hides the badge)."""
    logs = _logs(db, user_id)
    by_trail = {log.trail_id: log for log in logs}
    earned = earned_ids(gather(db, user_id))
    rows = db.scalars(
        select(FeaturedBadge).where(FeaturedBadge.user_id == user_id).order_by(FeaturedBadge.position)
    ).all()
    if rows:
        shown = []
        for row in rows:
            if row.trail_id is not None and row.trail_id in by_trail:
                shown.append(FeaturedBadgeOut(kind="trail", trail=TrailListItemOut.model_validate(by_trail[row.trail_id].trail)))
            elif row.milestone == PROVINCE_BADGE:
                if province is not None:
                    shown.append(FeaturedBadgeOut(kind="province", province=province))
            elif row.milestone is not None and row.milestone in earned:
                shown.append(
                    FeaturedBadgeOut(kind="milestone", milestone=row.milestone, badge=badge_out(BY_ID[row.milestone]))
                )
        return True, shown
    if hide_dates:
        logs = sorted(logs, key=lambda log: log.trail.name.lower())
    return False, [
        FeaturedBadgeOut(kind="trail", trail=TrailListItemOut.model_validate(log.trail)) for log in logs[:MAX_FEATURED]
    ]


def set_featured(db: Session, user_id: UUID, picks: list[Pick], *, home_province: str | None = None) -> None:
    """Replace the picks (an empty list goes back to the stand-ins). Raises BadgeChoiceError."""
    if len(picks) > MAX_FEATURED:
        raise BadgeChoiceError(f"Feature up to {MAX_FEATURED} badges.")
    keys = [(pick.trail_id, pick.stored_milestone) for pick in picks]
    if len(set(keys)) != len(keys):
        raise BadgeChoiceError("Each badge can only be featured once.")
    logs = _logs(db, user_id)
    hiked = {log.trail_id for log in logs}
    earned = earned_ids(gather(db, user_id))
    for pick in picks:
        if sum((pick.trail_id is not None, pick.milestone is not None, pick.province)) != 1:
            raise BadgeChoiceError("Pick either a trail badge, a milestone badge or your province badge.")
        if pick.province:
            if home_province is None:
                raise BadgeChoiceError("Choose your home province or territory in Edit profile first.")
            continue
        if pick.trail_id is not None and pick.trail_id not in hiked:
            raise BadgeChoiceError("You can only feature badges you've earned: log the hike first.")
        if pick.milestone is not None and pick.milestone not in BY_ID:
            raise BadgeChoiceError("That isn't a Trekly badge.")
        if pick.milestone is not None and pick.milestone not in earned:
            raise BadgeChoiceError("You can only feature badges you've earned.")
    db.execute(delete(FeaturedBadge).where(FeaturedBadge.user_id == user_id))
    # Flush the deletes first so the new positions don't collide with the old.
    db.flush()
    for position, pick in enumerate(picks):
        db.add(FeaturedBadge(user_id=user_id, position=position, trail_id=pick.trail_id, milestone=pick.stored_milestone))
    db.commit()


def prune_featured(db: Session, user_id: UUID) -> None:
    """After a hike is deleted: drop milestone picks it no longer earns. Trail
    picks for that hike are already gone (the FK cascades). Picks lost some
    other way (a deleted plan, say) are simply never shown."""
    logs = _logs(db, user_id)
    earned = earned_ids(gather(db, user_id))
    # Belt and braces for trail picks, should the cascade ever be missing.
    hiked = {log.trail_id for log in logs}
    stale = [
        row.id
        for row in db.scalars(select(FeaturedBadge).where(FeaturedBadge.user_id == user_id))
        if (row.milestone is not None and row.milestone != PROVINCE_BADGE and row.milestone not in earned)
        or (row.trail_id is not None and row.trail_id not in hiked)
    ]
    if stale:
        db.execute(delete(FeaturedBadge).where(FeaturedBadge.id.in_(stale)))
        db.commit()
