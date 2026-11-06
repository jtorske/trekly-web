"""A user's completed hikes: the Trail Journal.

One row per user per trail, with the date hiked and an optional note and
photo. Only the owner can change entries. Others can read them only while
the owner's public profile shows the Trail Journal, through the API (which
also applies "Hide dates on my hikes") or row-level security, which never
lets a client read the date columns at all (migrations 739722285c4e,
214aa07bf743). Trails are retired, never deleted, so a journal entry always
keeps its trail.

hiked_on is null for a hike from before the user joined, picked without a
date (onboarding or "Add past hikes"). verified, match_score and nights are
only ever set by the API from a matched GPX track (see migration
b4e7a2c9d1f3); clients can't write this table directly.
"""

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

MAX_NOTE_LENGTH = 500


class HikeLog(Base):
    __tablename__ = "hike_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "trail_id", name="hike_logs_user_trail_key"),
        CheckConstraint(
            f"note is null or length(note) between 1 and {MAX_NOTE_LENGTH}",
            name="hike_logs_note_length_check",
        ),
        CheckConstraint(
            "match_score is null or (match_score >= 0 and match_score <= 1)", name="hike_logs_match_score_check"
        ),
        CheckConstraint("nights is null or (nights >= 0 and nights <= 60)", name="hike_logs_nights_check"),
        CheckConstraint(
            "not verified or (hiked_on is not null and match_score is not null)", name="hike_logs_verified_check"
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), nullable=False, index=True)
    # Null: hiked before joining Trekly, date unknown.
    hiked_on = Column(Date)
    note = Column(Text)
    # `{user_id}/{uuid}.webp|jpg` in the private hike-photos bucket.
    photo_path = Column(Text)
    # Matched against a GPS track (the track itself is never kept).
    verified = Column(Boolean, nullable=False, default=False, server_default="false")
    # 0-1: how much of the trail's route the track covered.
    match_score = Column(Numeric(4, 3))
    # The track's own nights for an overnight trip; null means the trail's typical nights.
    nights = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trail = relationship("Trail")
