"""Up to three badges a user features on their profile, in order.

A badge is either a trail badge (a trail they've logged in their Trail
Journal) or a milestone badge (app/journal.py). A trail badge references
the user's own hike log, so deleting the hike deletes the badge with it;
milestone badges no longer earned are removed by the API when a hike is
deleted (app/featured.py). Positions 0-2, one row each, make "at most
three" a database rule. RLS (migration 8b3e5f1c2d40): only the owner
writes; visitors read through the Trail Journal's privacy switch.
"""

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, SmallInteger, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.journal import MILESTONES

MAX_FEATURED = 3


class FeaturedBadge(Base):
    __tablename__ = "featured_badges"
    __table_args__ = (
        UniqueConstraint("user_id", "position", name="featured_badges_position_key"),
        UniqueConstraint("user_id", "trail_id", name="featured_badges_trail_key"),
        UniqueConstraint("user_id", "milestone", name="featured_badges_milestone_key"),
        CheckConstraint(f"position between 0 and {MAX_FEATURED - 1}", name="featured_badges_position_check"),
        CheckConstraint("(trail_id is null) <> (milestone is null)", name="featured_badges_one_kind_check"),
        CheckConstraint(
            "milestone is null or milestone in (" + ", ".join(f"'{m}'" for m in MILESTONES) + ")",
            name="featured_badges_milestone_check",
        ),
        # A trail badge needs the hike behind it, and goes when the hike does.
        ForeignKeyConstraint(
            ["user_id", "trail_id"],
            ["hike_logs.user_id", "hike_logs.trail_id"],
            ondelete="CASCADE",
            name="featured_badges_hike_fkey",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    position = Column(SmallInteger, nullable=False)
    trail_id = Column(Uuid)
    milestone = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trail = relationship(
        "Trail",
        primaryjoin="FeaturedBadge.trail_id == Trail.id",
        foreign_keys=[trail_id],
        viewonly=True,
    )
