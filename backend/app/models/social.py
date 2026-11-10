"""Following between hikers, and in-app notifications.

A follow of a public profile is 'accepted' at once. A private profile gets
a 'pending' request until its owner approves it; declining, cancelling or
removing a follower deletes the row. An approved follower of a private
profile sees the sections its owner has switched on (app/privacy.py,
private.section_visible in migration b3d7f2a9c4e1). Only the API writes
this table; clients can read only the rows they're part of.
"""

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, PrimaryKeyConstraint, Text, Uuid, true,
)
from sqlalchemy.sql import func

from app.database import Base

FOLLOW_STATUSES = ("pending", "accepted")


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        PrimaryKeyConstraint("follower_id", "followee_id", name="follows_pkey"),
        CheckConstraint("status in ('pending', 'accepted')", name="follows_status_check"),
        CheckConstraint("follower_id <> followee_id", name="follows_not_self_check"),
        Index("follows_followee_idx", "followee_id", "status"),
        Index("follows_follower_idx", "follower_id", "status"),
    )

    # Same values as auth.users.id; the FKs to auth.users are added in the migration.
    follower_id = Column(Uuid, nullable=False)
    followee_id = Column(Uuid, nullable=False)
    status = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    accepted_at = Column(DateTime(timezone=True))


NOTIFICATION_KINDS = ("new_follower", "follow_request", "request_approved", "high_five", "comment")


class Notification(Base):
    """One in-app notification for one recipient (migration c6e1a4d8b2f5).
    Grouped when read (app/notifications.py). API-only: no client access."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "kind in ('new_follower', 'follow_request', 'request_approved', 'high_five', 'comment')",
            name="notifications_kind_check",
        ),
        CheckConstraint("user_id <> actor_id", name="notifications_not_self_check"),
        Index("notifications_user_idx", "user_id", "created_at"),
        Index("notifications_actor_idx", "actor_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # The recipient and who did it; FKs to auth.users are added in the migration.
    user_id = Column(Uuid, nullable=False)
    actor_id = Column(Uuid, nullable=False)
    kind = Column(Text, nullable=False)
    post_id = Column(Uuid, ForeignKey("activity_posts.id", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True))


class NotificationPreferences(Base):
    """Which notification types a user wants. A missing row means all on."""

    __tablename__ = "notification_preferences"

    user_id = Column(Uuid, primary_key=True)
    new_follower = Column(Boolean, nullable=False, default=True, server_default=true())
    follow_request = Column(Boolean, nullable=False, default=True, server_default=true())
    request_approved = Column(Boolean, nullable=False, default=True, server_default=true())
    high_five = Column(Boolean, nullable=False, default=True, server_default=true())
    comment = Column(Boolean, nullable=False, default=True, server_default=true())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
