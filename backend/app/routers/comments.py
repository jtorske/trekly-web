"""Comments on Activity posts (the rules are in app/comments.py).

GET  /api/activity/{post_id}/comments   all of them, as you may see them
POST /api/activity/{post_id}/comments   write one (or a reply: parent_id)
PUT  /api/activity/{post_id}/comments-off   the post's author turns them off/on
PATCH  /api/comments/{id}   its author edits it (screened again)
DELETE /api/comments/{id}   its author, or the post's author, deletes it

Every response is built from the models in app/comments.py: never a user id.
"""

import re
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.account_labels import may_interact
from app.auth import CurrentUser, get_current_user
from app.comments import CommentOut, is_blocked, mentioned, readable_post, render, thread
from app.database import get_db
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.comment import MAX_COMMENT, ActivityComment
from app.models.social import Notification
from app.moderation import (
    Services, content_removed, ensure_can_comment, ensure_can_publish, find_item, get_moderation_services,
    record_screening, run_screening, unchanged,
)
from app.notifications import notify
from app.routers.activity import NO_STORE, optional_user
from app.routers.availability import get_today

router = APIRouter(prefix="/api/activity", tags=["comments"])
comment_router = APIRouter(prefix="/api/comments", tags=["comments"])

COMMENTS_OFF = "Comments are off for this post."


def clean_body(value):
    """Trim it, use plain newlines, and keep at most one blank line in a row."""
    if not isinstance(value, str):
        return value
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", value).strip()


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_COMMENT)
    # Replying: the comment replied to (a reply's reply files under its parent).
    parent_id: UUID | None = None

    _clean = field_validator("body", mode="before")(classmethod(lambda cls, v: clean_body(v)))


class CommentEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_COMMENT)

    _clean = field_validator("body", mode="before")(classmethod(lambda cls, v: clean_body(v)))


class CommentsOut(BaseModel):
    comments: list[CommentOut]
    count: int
    comments_off: bool
    # Signed in and allowed to write here (moderation's own checks come on posting).
    can_comment: bool
    # The post is yours: you can turn comments off and delete any of them.
    post_mine: bool = False


class CommentsOffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    off: bool


class CommentsOffOut(BaseModel):
    comments_off: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _post_or_404(db: Session, post_id: UUID, viewer_id: UUID | None, today: date) -> ActivityPost:
    post = readable_post(db, post_id, viewer_id, today)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def can_comment(db: Session, post: ActivityPost, viewer_id: UUID | None) -> bool:
    return viewer_id is not None and not post.comments_off and may_interact(db, viewer_id, post.user_id)


def _one(db: Session, comment: ActivityComment, viewer_id: UUID, post: ActivityPost) -> CommentOut:
    profile = db.get(Profile, comment.user_id)
    return render(db, [(comment, profile)], viewer_id, {post.id: post.user_id})[0]


def _notify_about(db: Session, comment: ActivityComment, post: ActivityPost, today: date,
                  mentions: list[Profile]) -> None:
    """The post's author, the author of the comment replied to, and anyone
    mentioned who may see the post: one notification each, the most specific."""
    author = comment.user_id
    sent: set[UUID] = {author}

    def send(recipient: UUID, kind: str) -> None:
        if recipient in sent or is_blocked(db, recipient, author):
            return
        if readable_post(db, post.id, recipient, today) is None:
            return
        sent.add(recipient)
        notify(db, recipient, author, kind, post.id, comment_id=comment.id)

    if comment.parent_id is not None:
        parent = db.get(ActivityComment, comment.parent_id)
        if parent is not None and parent.body is not None:
            send(parent.user_id, "comment_reply")
    for profile in mentions:
        if profile.id != post.user_id:
            send(profile.id, "mention")
    send(post.user_id, "comment")


def _screen(db: Session, services: Services, comment: ActivityComment, body: str) -> bool:
    """Screens the text; writes it to the comment if it may publish. Returns that."""
    verdict = run_screening(services, "comment", body)
    outcome = record_screening(db, services, verdict, kind="comment", target_id=comment.id,
                               author_id=comment.user_id, text=body)
    comment.body = body if outcome.publish else None
    if not outcome.publish:
        db.execute(delete(Notification).where(Notification.comment_id == comment.id))
    return outcome.publish


@router.get("/{post_id}/comments", response_model=CommentsOut)
def list_comments(
    post_id: UUID,
    response: Response,
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Guests too: the comments anyone may see. Top-level ones oldest first,
    each followed by its replies."""
    response.headers.update(NO_STORE)
    viewer_id = viewer.id if viewer else None
    post = _post_or_404(db, post_id, viewer_id, today)
    comments = thread(db, post, viewer_id)
    return CommentsOut(comments=comments, count=len(comments), comments_off=bool(post.comments_off),
                       can_comment=can_comment(db, post, viewer_id),
                       post_mine=viewer_id is not None and post.user_id == viewer_id)


@router.post("/{post_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    post_id: UUID,
    payload: CommentIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    services: Services = Depends(get_moderation_services),
):
    post = _post_or_404(db, post_id, user.id, today)
    if post.comments_off:
        raise HTTPException(status_code=403, detail=COMMENTS_OFF)
    if not may_interact(db, user.id, post.user_id):
        raise HTTPException(status_code=403, detail="Demo accounts only interact with other demo accounts.")
    parent_id = None
    if payload.parent_id is not None:
        parent = db.get(ActivityComment, payload.parent_id)
        # The comment replied to must be one this user can see, on this post.
        if (parent is None or parent.post_id != post.id
                or (parent.body is None and parent.user_id != user.id)
                or is_blocked(db, parent.user_id, user.id)):
            raise HTTPException(status_code=404, detail="That comment isn't there any more.")
        parent_id = parent.parent_id or parent.id

    def count_since(since: datetime) -> int:
        return db.scalar(select(func.count()).select_from(ActivityComment).where(
            ActivityComment.user_id == user.id, ActivityComment.created_at >= since)) or 0

    ensure_can_comment(db, user.id, count_since)
    comment = ActivityComment(post_id=post.id, user_id=user.id, parent_id=parent_id, body=None, created_at=_now())
    db.add(comment)
    db.flush()
    if _screen(db, services, comment, payload.body):
        _notify_about(db, comment, post, today, mentioned(db, payload.body))
    db.commit()
    services.run_after_commit()
    return _one(db, comment, user.id, post)


@comment_router.patch("/{comment_id}", response_model=CommentOut)
def edit_comment(
    comment_id: UUID,
    payload: CommentEditIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    services: Services = Depends(get_moderation_services),
):
    """Its author only (an admin can hide a comment, never change it). The new
    text is screened like a new comment; anyone newly @mentioned hears about it."""
    comment = db.get(ActivityComment, comment_id)
    if comment is None or comment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    post = _post_or_404(db, comment.post_id, user.id, today)
    ensure_can_publish(db, user.id)
    item = find_item(db, "comment", comment.id)
    if payload.body == comment.body or unchanged(item, payload.body, "text"):
        return _one(db, comment, user.id, post)
    before = {p.id for p in mentioned(db, comment.body or (item.text if item else "") or "")}
    comment.edited_at = _now()
    if _screen(db, services, comment, payload.body):
        new = [p for p in mentioned(db, payload.body) if p.id not in before]
        if new:
            # Only the newly mentioned hear about an edit.
            _notify_mentions(db, comment, post, today, new)
    db.commit()
    services.run_after_commit()
    return _one(db, comment, user.id, post)


def _notify_mentions(db: Session, comment: ActivityComment, post: ActivityPost, today: date,
                     people: list[Profile]) -> None:
    for profile in people:
        if profile.id in (comment.user_id, post.user_id) or is_blocked(db, profile.id, comment.user_id):
            continue
        if readable_post(db, post.id, profile.id, today) is not None:
            notify(db, profile.id, comment.user_id, "mention", post.id, comment_id=comment.id)


@comment_router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Its author, or the author of the post it's on. Its replies go with it,
    and so do the notifications about them."""
    comment = db.get(ActivityComment, comment_id)
    post = db.get(ActivityPost, comment.post_id) if comment else None
    if comment is None or post is None or user.id not in (comment.user_id, post.user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.body is None:
        content_removed(db, "comment", comment.id)
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{post_id}/comments-off", response_model=CommentsOffOut)
def set_comments_off(
    post_id: UUID,
    payload: CommentsOffIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The post's author only. Comments already there stay; no new ones."""
    post = db.get(ActivityPost, post_id)
    if post is None or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    post.comments_off = payload.off
    db.commit()
    return CommentsOffOut(comments_off=post.comments_off)
