"""Following: who follows whom, follow requests, and who may see the lists.

The rules (row-level security has the same ones, migration b3d7f2a9c4e1):
- Following a public profile is instant. Following a private one sends a
  request, which its owner approves or declines. When a private profile
  goes public, its pending requests are approved.
- An approved follower of a private profile sees the sections its owner
  has switched on (app/privacy.py).
- Counts always show. The lists open for the owner, and for anyone who can
  see the profile (public, or an approved follower) unless the owner chose
  "Hide my followers and following lists".
- Lists, counts and requests only include people who are listed (have a
  username and aren't hidden by an admin), so a hidden account never shows
  up by way of someone else's list.

Only the API writes follows; nothing here is cached.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.models.account import Profile
from app.models.privacy import ProfileModeration
from app.models.social import Follow
from app.privacy import Visibility

FollowState = Literal["none", "requested", "following"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def listed_where(user_id: ColumnElement) -> ColumnElement[bool]:
    """SQL: the user has a username and isn't hidden by an admin."""
    # Aliased, so it never correlates with a Profile in the outer query.
    listed = aliased(Profile)
    return and_(
        exists(select(listed.id).where(listed.id == user_id, listed.username.is_not(None))),
        ~exists().where(ProfileModeration.user_id == user_id),
    )


def state(row: Follow | None) -> FollowState:
    if row is None:
        return "none"
    return "following" if row.status == "accepted" else "requested"


def state_of(db: Session, follower_id: UUID, followee_id: UUID) -> FollowState:
    return state(db.get(Follow, (follower_id, followee_id)))


def states(db: Session, viewer_id: UUID | None, user_ids) -> dict[UUID, FollowState]:
    """The viewer's follow state toward each of `user_ids` (missing = "none")."""
    ids = set(user_ids)
    if viewer_id is None or not ids:
        return {}
    rows = db.execute(
        select(Follow.followee_id, Follow.status).where(Follow.follower_id == viewer_id, Follow.followee_id.in_(ids))
    )
    return {followee: ("following" if status == "accepted" else "requested") for followee, status in rows}


def follower_count(db: Session, user_id: UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Follow).where(
            Follow.followee_id == user_id, Follow.status == "accepted", listed_where(Follow.follower_id)
        )
    ) or 0


def following_count(db: Session, user_id: UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Follow).where(
            Follow.follower_id == user_id, Follow.status == "accepted", listed_where(Follow.followee_id)
        )
    ) or 0


def request_count(db: Session, user_id: UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Follow).where(
            Follow.followee_id == user_id, Follow.status == "pending", listed_where(Follow.follower_id)
        )
    ) or 0


def follows_anyone(db: Session, user_id: UUID) -> bool:
    return db.scalar(
        select(exists().where(Follow.follower_id == user_id, Follow.status == "accepted"))
    ) or False


def lists_open(viewer_id: UUID | None, owner: Profile, seen: Visibility) -> bool:
    if viewer_id is not None and viewer_id == owner.id:
        return True
    return seen.opened and not bool(seen.settings.hide_follow_lists)


def follow(db: Session, follower_id: UUID, owner: Profile, seen: Visibility) -> tuple[FollowState, bool]:
    """Follow `owner` (or ask to). Idempotent. Returns the new state and
    whether anything changed."""
    row = db.get(Follow, (follower_id, owner.id))
    if row is not None:
        return state(row), False
    now = _now()
    accepted = seen.public
    db.add(Follow(
        follower_id=follower_id, followee_id=owner.id, status="accepted" if accepted else "pending",
        created_at=now, accepted_at=now if accepted else None,
    ))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()  # a concurrent request got there first
        return state_of(db, follower_id, owner.id), False
    return ("following" if accepted else "requested"), True


def unfollow(db: Session, follower_id: UUID, followee_id: UUID) -> Follow | None:
    """Unfollow, or cancel a request. Returns the removed row, if any."""
    row = db.get(Follow, (follower_id, followee_id))
    if row is not None:
        db.delete(row)
        db.flush()
    return row


def approve(db: Session, owner_id: UUID, follower_id: UUID) -> bool:
    row = db.get(Follow, (follower_id, owner_id))
    if row is None or row.status != "pending":
        return False
    row.status, row.accepted_at = "accepted", _now()
    db.flush()
    return True


def approve_all_pending(db: Session, owner_id: UUID) -> list[UUID]:
    """A private profile went public: its requests become follows."""
    followers = list(db.scalars(
        select(Follow.follower_id).where(Follow.followee_id == owner_id, Follow.status == "pending")
    ))
    if followers:
        db.execute(
            update(Follow)
            .where(Follow.followee_id == owner_id, Follow.status == "pending")
            .values(status="accepted", accepted_at=_now())
        )
        db.flush()
    return followers
