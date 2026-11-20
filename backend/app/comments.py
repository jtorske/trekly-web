"""Comments on Activity posts: who may see and write them, and how they read.

Seeing (checked on every read; the table is closed to clients):
- the post: as the feed's rules allow (app/activity.py readable_where: anyone
  may see it, or it's your own), and nobody blocked anybody between you and
  its author. Private profiles never post to the feed, so a private hiker's
  post (and its comments) is seen only by them, approved followers included.
- each comment: its author is listed (a username, not hidden by an admin),
  neither of you has blocked the other, and it isn't withheld by moderation
  (body null), unless it's your own, which you see with "Being reviewed".

Writing: signed in, able to see the post (and, for a reply, the comment
replied to), comments not turned off, no block either way with the post's
author, and moderation's own rules (app/moderation.py ensure_can_comment:
not restricted, a confirmed email, the rate limits in moderation_config).
Every new or edited text is screened; a flagged one is held, seen only by
its author, and goes to the admin queue.

Replies are one level deep: replying to a reply files the new one under the
same top-level comment.

Notifications (app/notifications.py), only for published comments and never
between blocked hikers: the post's author ("commented on your hike"), the
author of the comment replied to ("replied to your comment"), and anyone
@mentioned who may see the post ("mentioned you"); one notification per
person per comment, the most specific one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.account_labels import AccountLabelName, labels_for
from app.activity import readable_query
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.comment import ActivityComment
from app.models.privacy import ProfileModeration
from app.models.social import Block
from app.moderation import review_state, withheld_items

PREVIEW = 2
# "@ana_hikes": not part of a longer word or an email address.
MENTION = re.compile(r"(?<![\w@.])@([a-z0-9_]{3,30})(?![\w])", re.IGNORECASE)


class CommentAuthor(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    label: AccountLabelName | None = None


class CommentOut(BaseModel):
    id: UUID
    # A reply: the top-level comment it's under.
    parent_id: UUID | None
    author: CommentAuthor
    body: str
    created_at: datetime
    # Set once its author has changed it.
    edited_at: datetime | None
    # Signed in: it's yours (edit, delete), and you may delete it (yours, or on your post).
    mine: bool = False
    can_delete: bool = False
    # Your own, withheld by moderation: "pending" (being reviewed) or "hidden" (removed).
    review: Literal["pending", "hidden"] | None = None


def blocked_either_way(a, b):
    """SQL: one of the two (user id columns or values) has blocked the other."""
    return or_(
        exists().where(Block.blocker_id == a, Block.blocked_id == b),
        exists().where(Block.blocker_id == b, Block.blocked_id == a),
    )


def is_blocked(db: Session, a: UUID, b: UUID) -> bool:
    return a != b and bool(db.scalar(select(blocked_either_way(a, b))))


def readable_post(db: Session, post_id: UUID, viewer_id: UUID | None, today: date) -> ActivityPost | None:
    """The post, if this reader may see it (and so its comments)."""
    query = readable_query(today, viewer_id).where(ActivityPost.id == post_id)
    if viewer_id is not None:
        query = query.where(~blocked_either_way(ActivityPost.user_id, viewer_id))
    row = db.execute(query).first()
    return row[0] if row else None


def _listed():
    return and_(
        Profile.username.is_not(None),
        ~exists().where(ProfileModeration.user_id == ActivityComment.user_id),
    )


def _shown(viewer_id: UUID | None):
    """The comments this reader sees (on posts they may see)."""
    if viewer_id is None:
        return and_(_listed(), ActivityComment.body.is_not(None))
    return and_(
        _listed(),
        or_(ActivityComment.body.is_not(None), ActivityComment.user_id == viewer_id),
        ~blocked_either_way(ActivityComment.user_id, viewer_id),
    )


def _rows(viewer_id: UUID | None):
    return (
        select(ActivityComment, Profile)
        .join(Profile, Profile.id == ActivityComment.user_id)
        .where(_shown(viewer_id))
    )


def counts(db: Session, post_ids: list[UUID], viewer_id: UUID | None) -> dict[UUID, int]:
    if not post_ids:
        return {}
    rows = db.execute(
        select(ActivityComment.post_id, func.count())
        .join(Profile, Profile.id == ActivityComment.user_id)
        .where(ActivityComment.post_id.in_(post_ids), _shown(viewer_id))
        .group_by(ActivityComment.post_id)
    )
    return {post_id: count for post_id, count in rows}


@dataclass
class PostComments:
    count: int
    # The newest PREVIEW, oldest first.
    preview: list[CommentOut]


def previews(db: Session, posts: list[ActivityPost], viewer_id: UUID | None) -> dict[UUID, PostComments]:
    """Each post's comment count and its newest few comments, as this reader sees them."""
    ids = [post.id for post in posts]
    if not ids:
        return {}
    numbered = (
        select(
            ActivityComment.id.label("comment_id"),
            func.row_number().over(
                partition_by=ActivityComment.post_id,
                order_by=(ActivityComment.created_at.desc(), ActivityComment.id.desc()),
            ).label("n"),
        )
        .join(Profile, Profile.id == ActivityComment.user_id)
        .where(ActivityComment.post_id.in_(ids), _shown(viewer_id))
        .subquery()
    )
    rows = db.execute(
        select(ActivityComment, Profile)
        .join(numbered, numbered.c.comment_id == ActivityComment.id)
        .join(Profile, Profile.id == ActivityComment.user_id)
        .where(numbered.c.n <= PREVIEW)
        .order_by(ActivityComment.created_at, ActivityComment.id)
    ).all()
    owners = {post.id: post.user_id for post in posts}
    out = render(db, rows, viewer_id, owners)
    total = counts(db, ids, viewer_id)
    found: dict[UUID, PostComments] = {post_id: PostComments(total.get(post_id, 0), []) for post_id in ids}
    for (comment, _), item in zip(rows, out):
        found[comment.post_id].preview.append(item)
    return found


def thread(db: Session, post: ActivityPost, viewer_id: UUID | None) -> list[CommentOut]:
    """All of a post's comments this reader sees: top-level ones oldest first,
    each followed by its replies, oldest first. A reply whose comment this
    reader can't see is left out with it."""
    rows = db.execute(
        _rows(viewer_id).where(ActivityComment.post_id == post.id)
        .order_by(ActivityComment.created_at, ActivityComment.id)
    ).all()
    out = render(db, rows, viewer_id, {post.id: post.user_id})
    top = [item for item in out if item.parent_id is None]
    replies: dict[UUID, list[CommentOut]] = {}
    for item in out:
        if item.parent_id is not None:
            replies.setdefault(item.parent_id, []).append(item)
    ordered: list[CommentOut] = []
    for item in top:
        ordered.append(item)
        ordered.extend(replies.get(item.id, []))
    return ordered


def render(db: Session, rows: list, viewer_id: UUID | None, owners: dict[UUID, UUID]) -> list[CommentOut]:
    """Comments as this reader sees them (rows of (comment, author profile))."""
    own = [comment.id for comment, _ in rows if viewer_id is not None and comment.user_id == viewer_id]
    held = withheld_items(db, ("comment",), own)
    labels = labels_for(db, {comment.user_id for comment, _ in rows})
    out = []
    for comment, profile in rows:
        mine = viewer_id is not None and comment.user_id == viewer_id
        item = held.get(("comment", comment.id)) if mine else None
        body = comment.body if comment.body is not None else (item.text if item else None)
        if body is None:
            continue  # their own, cleared by them while withheld
        out.append(CommentOut(
            id=comment.id,
            parent_id=comment.parent_id,
            author=CommentAuthor(username=profile.username, display_name=profile.display_name,
                                 avatar_path=profile.avatar_path, label=labels.get(comment.user_id)),
            body=body,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            mine=mine,
            can_delete=mine or (viewer_id is not None and owners.get(comment.post_id) == viewer_id),
            review=review_state(item) if comment.body is None else None,
        ))
    return out


def mentioned(db: Session, body: str) -> list[Profile]:
    """The listed hikers a comment @mentions, in order, once each."""
    names = list(dict.fromkeys(name.lower() for name in MENTION.findall(body)))
    if not names:
        return []
    found = {p.username: p for p in db.scalars(select(Profile).where(Profile.username.in_(names)))}
    return [found[name] for name in names if name in found]
