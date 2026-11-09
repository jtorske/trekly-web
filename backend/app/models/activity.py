"""The Activity feed: posts made from real activity, and their high fives.

A post is never free-form text. It's one of:
- "hike": a Trail Journal entry the owner chose to share. Its trail, date,
  note and photo are read live from the hike log, so editing the hike edits
  the post, and deleting the hike deletes the post (ON DELETE CASCADE).
- "milestone": a milestone the owner earned by logging a shared hike.
- "rank": a rank the owner reached by logging a shared hike.

Milestone and rank posts keep the hike that earned them (hike_log_id), so
removing that hike removes them too. Trip plans, alerts, saved trails and
future dates are never posted: there's no kind for them, and the feed drops
a hike post whose date is in the future (app/activity.py).

Who sees a post is decided on every read (app/activity.py, and row-level
security in migration a8c3f1d5e7b2): the owner shares their activity, has a
public profile, shows the section the post draws on, and no admin has hidden
the post. Only the API writes these tables.
"""

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, PrimaryKeyConstraint, SmallInteger, Text, Uuid,
    false, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

POST_KINDS = ("hike", "milestone", "rank")
MAX_HIDE_REASON = 500


class ActivityPost(Base):
    __tablename__ = "activity_posts"
    __table_args__ = (
        CheckConstraint("kind in ('hike', 'milestone', 'rank')", name="activity_posts_kind_check"),
        CheckConstraint(
            "(kind = 'hike' and hike_log_id is not null and milestone is null and rank_level is null)"
            " or (kind = 'milestone' and milestone is not null and rank_level is null)"
            " or (kind = 'rank' and rank_level is not null and milestone is null)",
            name="activity_posts_shape_check",
        ),
        CheckConstraint(
            f"hidden_reason is null or length(hidden_reason) <= {MAX_HIDE_REASON}",
            name="activity_posts_hidden_reason_length_check",
        ),
        # One post per hike, milestone and rank.
        Index("activity_posts_hike_key", "hike_log_id", unique=True,
              postgresql_where=text("kind = 'hike'"), sqlite_where=text("kind = 'hike'")),
        Index("activity_posts_milestone_key", "user_id", "milestone", unique=True,
              postgresql_where=text("kind = 'milestone'"), sqlite_where=text("kind = 'milestone'")),
        Index("activity_posts_rank_key", "user_id", "rank_level", unique=True,
              postgresql_where=text("kind = 'rank'"), sqlite_where=text("kind = 'rank'")),
        Index("activity_posts_feed_idx", "created_at", "id"),
        Index("activity_posts_user_idx", "user_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    kind = Column(Text, nullable=False)
    # The shared hike, or for a milestone or rank, the hike that earned it.
    hike_log_id = Column(Uuid, ForeignKey("hike_logs.id", ondelete="CASCADE"))
    # A milestone id from app/milestones_config.py.
    milestone = Column(Text)
    # 1-based, as in app/points.py.
    rank_level = Column(SmallInteger)
    # A seasonal milestone: it hints at when they hiked, so it's left out
    # while they hide their hike dates.
    reveals_date = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Set by an admin (audited); a hidden post shows to nobody.
    hidden_at = Column(DateTime(timezone=True))
    hidden_by = Column(Uuid)
    hidden_reason = Column(Text)

    hike_log = relationship("HikeLog")


class ActivityReaction(Base):
    """A "High five": one per user per post."""

    __tablename__ = "activity_reactions"
    __table_args__ = (PrimaryKeyConstraint("post_id", "user_id", name="activity_reactions_pkey"),)

    post_id = Column(Uuid, ForeignKey("activity_posts.id", ondelete="CASCADE"), nullable=False)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
