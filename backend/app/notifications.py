"""In-app notifications: when they're made, undone, and how they're grouped.

Made by the API when something happens to you:
- new_follower: someone followed your public profile.
- follow_request: someone asked to follow your private profile. It goes
  away once you approve or decline it, or they cancel.
- request_approved: someone approved your request to follow them.
- high_five: someone high-fived one of your posts.
- comment: someone commented on one of your posts.

Undoing the action takes the notification back (unfollowing, cancelling a
request, taking back a high five), so nothing points at something that no
longer happened. Doing it again replaces the old one rather than adding a
second. Nobody is notified about their own actions, and nothing is made
for a type the recipient turned off in Settings → Notifications.

Grouped when read: new followers on the same day, and high fives or
comments on the same post, become one line ("Ana and 3 others"); requests
and approvals stay one per person. A group is unread while any of it is.
Only people who are listed (a username, not hidden by an admin) appear.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.account import Profile
from app.models.privacy import ProfileModeration
from app.models.social import NOTIFICATION_KINDS, Follow, Notification, NotificationPreferences

# The newest notifications read for the list; older ones fall off it.
WINDOW = 300
MAX_GROUPS = 60
SHOWN_ACTORS = 3
# Kept this long; older ones are deleted when new ones are made.
KEEP = timedelta(days=180)
GROUPED_BY_POST = {"high_five", "comment"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------ preferences


def preferences(db: Session, user_id: UUID) -> dict[str, bool]:
    row = db.get(NotificationPreferences, user_id)
    return {kind: True if row is None else bool(getattr(row, kind)) for kind in NOTIFICATION_KINDS}


def set_preferences(db: Session, user_id: UUID, changes: dict[str, bool]) -> dict[str, bool]:
    row = db.get(NotificationPreferences, user_id)
    if row is None:
        row = NotificationPreferences(user_id=user_id, **{kind: True for kind in NOTIFICATION_KINDS})
        db.add(row)
    for kind, on in changes.items():
        setattr(row, kind, on)
    db.flush()
    return preferences(db, user_id)


# ------------------------------------------------------------ making them


def retract(db: Session, recipient: UUID, actor: UUID, kind: str, post_id: UUID | None = None) -> None:
    where = [Notification.user_id == recipient, Notification.actor_id == actor, Notification.kind == kind]
    if post_id is not None:
        where.append(Notification.post_id == post_id)
    db.execute(delete(Notification).where(*where))


def notify(db: Session, recipient: UUID, actor: UUID, kind: str, post_id: UUID | None = None) -> bool:
    """Make one (replacing the same one from before). False when skipped."""
    if recipient == actor or not preferences(db, recipient)[kind]:
        return False
    if kind != "comment":
        retract(db, recipient, actor, kind, post_id)
    now = _now()
    db.add(Notification(user_id=recipient, actor_id=actor, kind=kind, post_id=post_id, created_at=now))
    db.execute(delete(Notification).where(Notification.user_id == recipient, Notification.created_at < now - KEEP))
    db.flush()
    return True


# ------------------------------------------------------------ reading them


@dataclass
class Group:
    kind: str
    key: tuple
    latest: datetime
    ids: list[UUID] = field(default_factory=list)
    actors: list[UUID] = field(default_factory=list)
    unread: bool = False
    post_id: UUID | None = None


def _visible(db: Session, user_id: UUID) -> list[Notification]:
    """The newest notifications that may show: from listed people, of types
    the user wants, and (for requests) still waiting."""
    wanted = [kind for kind, on in preferences(db, user_id).items() if on]
    if not wanted:
        return []
    rows = db.scalars(
        select(Notification)
        .join(Profile, Profile.id == Notification.actor_id)
        .where(
            Notification.user_id == user_id,
            Notification.kind.in_(wanted),
            Profile.username.is_not(None),
            ~select(ProfileModeration.user_id).where(ProfileModeration.user_id == Notification.actor_id).exists(),
        )
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(WINDOW)
    ).all()
    pending = set(db.scalars(
        select(Follow.follower_id).where(Follow.followee_id == user_id, Follow.status == "pending")
    ))
    return [row for row in rows if row.kind != "follow_request" or row.actor_id in pending]


def _key(row: Notification) -> tuple:
    if row.kind == "new_follower":
        return ("new_follower", _aware(row.created_at).date())
    if row.kind in GROUPED_BY_POST:
        return (row.kind, row.post_id)
    return (row.kind, row.id)


def groups(db: Session, user_id: UUID) -> list[Group]:
    found: OrderedDict[tuple, Group] = OrderedDict()
    for row in _visible(db, user_id):  # newest first, so each group's first row is its latest
        key = _key(row)
        group = found.get(key)
        if group is None:
            group = found[key] = Group(kind=row.kind, key=key, latest=_aware(row.created_at), post_id=row.post_id)
        group.ids.append(row.id)
        if row.actor_id not in group.actors:
            group.actors.append(row.actor_id)
        group.unread = group.unread or row.read_at is None
    return list(found.values())[:MAX_GROUPS]


def unread_count(db: Session, user_id: UUID) -> int:
    return sum(1 for group in groups(db, user_id) if group.unread)


def mark_read(db: Session, user_id: UUID, ids: list[UUID] | None = None) -> None:
    """Mark these (or all) of the user's notifications read. Others' ids are ignored."""
    query = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids is not None:
        query = query.where(Notification.id.in_(ids))
    db.execute(query.values(read_at=_now()))
    db.flush()
