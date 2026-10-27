"""A user's completed hikes: the Trail Journal.

One row per user per trail, with the date hiked and an optional note and
photo. Only the owner can change entries. Others can read them only while
the owner's public profile shows the Trail Journal, through the API (which
also applies "Hide dates on my hikes") or row-level security, which never
lets a client read the date columns at all (migrations 739722285c4e,
214aa07bf743). Trails are retired, never deleted, so a journal entry always
keeps its trail.
"""

import uuid

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Text, UniqueConstraint, Uuid
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
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), nullable=False, index=True)
    hiked_on = Column(Date, nullable=False)
    note = Column(Text)
    # `{user_id}/{uuid}.webp|jpg` in the private hike-photos bucket.
    photo_path = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trail = relationship("Trail")
