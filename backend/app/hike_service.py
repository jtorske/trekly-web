"""Adding hikes to a user's Trail Journal: the one path for every entry point.

"Mark as hiked" (PUT /api/me/hike-logs/{trail_id} for a new entry), the
onboarding picker and "Add past hikes" (POST /api/me/hike-logs/past) all call
add_hikes(), and a GPX import must too. It creates the entries that aren't
there yet, then evaluates the journal once, however many hikes were added, and
says what that changed: trails stamped, milestones newly earned, points and
rank before and after.

Nothing about milestones or points is stored (app/milestones.py and
app/points.py work them out from the hike logs on every request), so the
evaluation here is only to report the change, for the onboarding summary and
the client's celebrations; the journal is correct either way.

Validation that depends on the entry point (dates, photos, fair use, retired
trails for a single hike) stays with the caller. Here, a trail that's already
in the journal keeps its entry and is skipped, as is a retired or unknown one.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.milestones import Facts, earned_ids, gather
from app.milestones_config import ACTIVE, Milestone
from app.models.hike_log import HikeLog
from app.models.trail import Trail
from app.points import Rank, rank_for, score


@dataclass(frozen=True)
class NewHike:
    trail_id: UUID
    # None: hiked before Trekly, date unknown.
    hiked_on: date | None = None
    note: str | None = None
    photo_path: str | None = None


@dataclass(frozen=True)
class Standing:
    """A journal's totals at one moment."""

    stamps: int
    earned: frozenset[str]
    points: int
    rank: Rank


@dataclass(frozen=True)
class Progress:
    before: Standing
    after: Standing

    @property
    def new_milestones(self) -> list[Milestone]:
        """Newly earned, in journal order."""
        return [m for m in ACTIVE if m.id in self.after.earned and m.id not in self.before.earned]

    @property
    def ranked_up(self) -> bool:
        return self.after.rank.level > self.before.rank.level


@dataclass(frozen=True)
class AddResult:
    added: list[HikeLog]
    # Already in the journal (left as they were), retired or unknown.
    skipped: int
    progress: Progress


def standing(facts: Facts) -> Standing:
    points = score(facts).total
    return Standing(
        stamps=len({hike.trail.id for hike in facts.hikes}),
        earned=frozenset(earned_ids(facts)),
        points=points,
        rank=rank_for(points),
    )


def _insert(db: Session, user_id: UUID, hikes: list[NewHike]) -> list[UUID]:
    """Add the entries in one commit; if a concurrent request added some of
    them first, add the rest one at a time. Returns the trails added."""

    def row(hike: NewHike) -> HikeLog:
        return HikeLog(
            user_id=user_id, trail_id=hike.trail_id, hiked_on=hike.hiked_on, note=hike.note, photo_path=hike.photo_path
        )

    for hike in hikes:
        db.add(row(hike))
    try:
        db.commit()
        return [hike.trail_id for hike in hikes]
    except IntegrityError:
        db.rollback()
    added = []
    for hike in hikes:
        db.add(row(hike))
        try:
            db.commit()
            added.append(hike.trail_id)
        except IntegrityError:
            db.rollback()
    return added


def add_hikes(db: Session, user_id: UUID, hikes: Sequence[NewHike]) -> AddResult:
    """Create the journal entries that aren't there yet, then evaluate once."""
    # One entry per trail; the first wins if a trail is listed twice.
    wanted = list({hike.trail_id: hike for hike in reversed(hikes)}.values())[::-1]
    ids = [hike.trail_id for hike in wanted]
    before = gather(db, user_id)
    logged = {hike.trail.id for hike in before.hikes}
    addable = set(db.scalars(select(Trail.id).where(Trail.id.in_(ids), Trail.retired_at.is_(None)))) if ids else set()
    new = [hike for hike in wanted if hike.trail_id in addable and hike.trail_id not in logged]

    added_ids = _insert(db, user_id, new) if new else []
    added = (
        db.scalars(
            select(HikeLog)
            .where(HikeLog.user_id == user_id, HikeLog.trail_id.in_(added_ids))
            .options(joinedload(HikeLog.trail))
        ).all()
        if added_ids
        else []
    )
    order = {trail_id: index for index, trail_id in enumerate(added_ids)}
    added = sorted(added, key=lambda log: order[log.trail_id])

    # The one evaluation, however many hikes were added.
    after = gather(db, user_id) if added else before
    return AddResult(added=added, skipped=len(wanted) - len(added), progress=Progress(standing(before), standing(after)))
