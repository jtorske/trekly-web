"""Gentle pointers to the community settings, and which ones each user has
put away (app/nudges.py has the rules).

One row per user per nudge, written only by the API: when they tap ✕,
decide once in the Mark as hiked dialog, or turn the setting on. A row is
never removed, so a nudge never comes back. Clients have no grants on the
table at all (migration d2b6e8f4a1c9).
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base

NUDGES = ("hike_share", "activity_card", "hiked_by")


class NudgeDismissal(Base):
    __tablename__ = "nudge_dismissals"
    __table_args__ = (
        CheckConstraint(
            "nudge in (" + ", ".join(f"'{nudge}'" for nudge in NUDGES) + ")",
            name="nudge_dismissals_nudge_check",
        ),
    )

    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, primary_key=True)
    nudge = Column(Text, primary_key=True)
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
