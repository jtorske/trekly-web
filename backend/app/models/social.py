"""Following between hikers.

A follow of a public profile is 'accepted' at once. A private profile gets
a 'pending' request until its owner approves it; declining, cancelling or
removing a follower deletes the row. An approved follower of a private
profile sees the sections its owner has switched on (app/privacy.py,
private.section_visible in migration b3d7f2a9c4e1). Only the API writes
this table; clients can read only the rows they're part of.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Index, PrimaryKeyConstraint, Text, Uuid
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
