"""Per-user account data: profile and saved (bookmarked) trails.

Both tables are keyed to the Supabase auth user id. Rows are created and
changed only for the user identified by a verified access token (API) or by
auth.uid() (row-level security), never by a client-supplied id.

Saved trails are bookmarks only — not planned trips or completed hikes.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

USERNAME_PATTERN = r"^[a-z0-9_]{3,30}$"


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "display_name is null or length(display_name) between 1 and 60",
            name="profiles_display_name_length_check",
        ),
        CheckConstraint(
            "bio is null or length(bio) <= 280", name="profiles_bio_length_check"
        ),
        CheckConstraint(
            "home_region is null or length(home_region) <= 80",
            name="profiles_home_region_length_check",
        ),
        Index("profiles_username_key", "username", unique=True),
    )

    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    id = Column(Uuid, primary_key=True)
    display_name = Column(Text)
    # Lowercase handle, unique when set. Format enforced in the migration
    # (Postgres regex) and in the API.
    username = Column(Text)
    bio = Column(Text)
    home_region = Column(Text)
    avatar_path = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SavedTrail(Base):
    __tablename__ = "saved_trails"

    user_id = Column(Uuid, primary_key=True)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trail = relationship("Trail")
