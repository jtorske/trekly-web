"""Public-profile privacy: each user's settings, admin moderation and reports.

Visibility is enforced twice: by row-level security for direct Supabase
access (private.section_visible in migration 214aa07bf743) and by the API
(app/routers/public_profiles.py), which reads these same rows.

New users get the column defaults below (a public profile with trip plans
private). Users from before public profiles were backfilled fully private.
A missing row is treated as private.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Text, Uuid, false, true
from sqlalchemy.sql import func

from app.database import Base

# Section -> settings column. "profile" (name, bio) has no switch of its own:
# it's governed by is_private alone.
SECTION_COLUMNS = {
    "journal": "show_journal",
    "rank": "show_rank",
    "gear": "show_gear",
    "saved_trails": "show_saved_trails",
    "trip_plans": "show_trip_plans",
}

MAX_REPORT_DETAILS = 1000


class ProfileSettings(Base):
    __tablename__ = "profile_settings"

    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, primary_key=True)
    is_private = Column(Boolean, nullable=False, default=False, server_default=false())
    show_journal = Column(Boolean, nullable=False, default=True, server_default=true())
    show_rank = Column(Boolean, nullable=False, default=True, server_default=true())
    show_gear = Column(Boolean, nullable=False, default=True, server_default=true())
    show_saved_trails = Column(Boolean, nullable=False, default=True, server_default=true())
    show_trip_plans = Column(Boolean, nullable=False, default=False, server_default=false())
    hide_hike_dates = Column(Boolean, nullable=False, default=False, server_default=false())
    allow_search_indexing = Column(Boolean, nullable=False, default=False, server_default=false())
    public_notice_pending = Column(Boolean, nullable=False, default=False, server_default=false())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProfileModeration(Base):
    """A profile an admin has hidden. Clients have no access to this table."""

    __tablename__ = "profile_moderation"
    __table_args__ = (
        CheckConstraint("reason is null or length(reason) <= 500", name="profile_moderation_reason_length_check"),
    )

    user_id = Column(Uuid, primary_key=True)
    hidden_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    hidden_by = Column(Uuid)
    reason = Column(Text)


class ProfileReport(Base):
    """A "Report profile" submission, kept so reports can be rate-limited."""

    __tablename__ = "profile_reports"
    __table_args__ = (
        CheckConstraint("length(reason) between 1 and 40", name="profile_reports_reason_length_check"),
        CheckConstraint(
            f"details is null or length(details) <= {MAX_REPORT_DETAILS}",
            name="profile_reports_details_length_check",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    reporter_id = Column(Uuid, nullable=False, index=True)
    profile_id = Column(Uuid, nullable=False)
    reason = Column(Text, nullable=False)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
