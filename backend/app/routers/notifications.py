"""The signed-in user's notifications and which types they want.

Grouped as app/notifications.py describes. Every response is built from the
models below: people are only their username, display name and photo, and
a post is only its id and what it was about. Nothing is cached.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import follows, notifications
from app.activity import MILESTONES
from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.follows import FollowState
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.points_config import RANKS

router = APIRouter(prefix="/api/me", tags=["notifications"])

NO_STORE = {"Cache-Control": "no-store"}
NotificationKind = Literal["new_follower", "follow_request", "request_approved", "high_five", "comment"]


class NotificationActor(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None


class NotificationPost(BaseModel):
    id: UUID
    kind: Literal["hike", "milestone", "rank", "announcement"]
    # What it's about: a trail, a badge or a rank name.
    title: str
    # A hike post's trail, to link to.
    trail_id: UUID | None = None


class NotificationOut(BaseModel):
    # The newest notification in the group, and all of them (for marking read).
    id: UUID
    ids: list[UUID]
    kind: NotificationKind
    # The most recent few, newest first.
    actors: list[NotificationActor]
    # Everyone in the group, counting those not in `actors`.
    actor_count: int
    created_at: datetime
    unread: bool
    post: NotificationPost | None = None
    # A one-person group: your follow state toward them ("Follow back").
    follow: FollowState | None = None


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class UnreadOut(BaseModel):
    unread: int


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None marks everything read.
    ids: list[UUID] | None = Field(default=None, max_length=500)


class PreferencesOut(BaseModel):
    new_follower: bool
    follow_request: bool
    request_approved: bool
    high_five: bool
    comment: bool


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_follower: bool | None = None
    follow_request: bool | None = None
    request_approved: bool | None = None
    high_five: bool | None = None
    comment: bool | None = None


def _post_title(post: ActivityPost) -> str:
    if post.kind == "hike":
        return post.hike_log.trail.name if post.hike_log else "a hike"
    if post.kind == "milestone":
        milestone = MILESTONES.get(post.milestone)
        return milestone.title if milestone else "a badge"
    if post.kind == "announcement":
        return "a Trekly post"
    return RANKS[post.rank_level - 1][1] if 1 <= post.rank_level <= len(RANKS) else "a new rank"


def _list(db: Session, user_id: UUID) -> NotificationList:
    found = notifications.groups(db, user_id)
    people_ids = {actor for group in found for actor in group.actors[: notifications.SHOWN_ACTORS]}
    people = {p.id: p for p in db.scalars(select(Profile).where(Profile.id.in_(people_ids)))} if people_ids else {}
    post_ids = {group.post_id for group in found if group.post_id}
    posts = {
        p.id: p for p in db.scalars(
            select(ActivityPost).where(ActivityPost.id.in_(post_ids))
            .options(joinedload(ActivityPost.hike_log).joinedload(HikeLog.trail))
        )
    } if post_ids else {}
    singles = {group.actors[0] for group in found if len(group.actors) == 1}
    states = follows.states(db, user_id, singles)
    items = []
    for group in found:
        post = posts.get(group.post_id) if group.post_id else None
        items.append(NotificationOut(
            id=group.ids[0],
            ids=group.ids,
            kind=group.kind,
            actors=[
                NotificationActor(username=people[a].username, display_name=people[a].display_name,
                                  avatar_path=people[a].avatar_path)
                for a in group.actors[: notifications.SHOWN_ACTORS]
            ],
            actor_count=len(group.actors),
            created_at=group.latest,
            unread=group.unread,
            post=NotificationPost(
                id=post.id, kind=post.kind, title=_post_title(post),
                trail_id=post.hike_log.trail_id if post.kind == "hike" and post.hike_log else None,
            ) if post else None,
            follow=states.get(group.actors[0], "none") if len(group.actors) == 1 else None,
        ))
    return NotificationList(items=items, unread=sum(1 for item in items if item.unread))


@router.get("/notifications", response_model=NotificationList)
def list_notifications(response: Response, user: CurrentUser = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return _list(db, user.id)


@router.get("/notifications/unread", response_model=UnreadOut)
def unread(response: Response, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """For the bell's badge: how many groups are unread."""
    response.headers.update(NO_STORE)
    return UnreadOut(unread=notifications.unread_count(db, user.id))


@router.post("/notifications/read", response_model=UnreadOut)
def mark_read(payload: ReadIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark some (by id) or all of your notifications read. Read state is kept on the server."""
    notifications.mark_read(db, user.id, payload.ids)
    db.commit()
    return UnreadOut(unread=notifications.unread_count(db, user.id))


@router.get("/notification-settings", response_model=PreferencesOut)
def get_preferences(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return PreferencesOut(**notifications.preferences(db, user.id))


@router.patch("/notification-settings", response_model=PreferencesOut)
def update_preferences(payload: PreferencesIn, user: CurrentUser = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Turning a type off stops new ones and hides the ones you have."""
    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    saved = notifications.set_preferences(db, user.id, changes)
    db.commit()
    return PreferencesOut(**saved)
