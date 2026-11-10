"""Public-profile privacy: each user's settings, admin moderation and reports.

Visibility is enforced twice: by row-level security for direct Supabase
access (private.section_visible in migration 214aa07bf743) and by the API
(app/routers/public_profiles.py), which reads these same rows.

New users get the column defaults below (a public profile with trip plans
private). Users from before public profiles were backfilled fully private.
A missing row is treated as private.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Text, Uuid, false, true
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
    "home_province": "show_home_province",
    "visit_streak": "show_visit_streak",
}

MAX_REPORT_DETAILS = 1000
REPORT_STATUSES = ("open", "resolved")


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
    # "Show me in community features" ("Hiked by" on trail pages). Off for
    # everyone until they opt in, and only in effect while the journal is
    # public (migration 9d4f2a6c8e13).
    show_in_community = Column(Boolean, nullable=False, default=False, server_default=false())
    # "Home province" on the public profile. Off until they turn it on
    # (migration 4f8b2c6d9e13).
    show_home_province = Column(Boolean, nullable=False, default=False, server_default=false())
    # "Visit streak" on the public profile. Off until they turn it on
    # (migration f9c2d4e6a8b1).
    show_visit_streak = Column(Boolean, nullable=False, default=False, server_default=false())
    # "Share my activity in the feed": hike, milestone and rank posts on the
    # Activity page. Off until they turn it on, and only in effect while the
    # profile is public (migration a8c3f1d5e7b2). Turning it off hides every
    # post they've made.
    share_activity = Column(Boolean, nullable=False, default=False, server_default=false())
    # "Hide my followers and following lists": the counts still show, the
    # lists open only for them (migration b3d7f2a9c4e1).
    hide_follow_lists = Column(Boolean, nullable=False, default=False, server_default=false())
    public_notice_pending = Column(Boolean, nullable=False, default=False, server_default=false())
    # When they last chose Public or Private themselves; the setup flow can't
    # finish or be skipped without it (migration c7e3a9f1d5b2). API-only.
    visibility_chosen_at = Column(DateTime(timezone=True))
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
    """A "Report profile" submission: rate-limits reporters, and is the admin
    area's report queue (open until an admin resolves it). A report with a
    trail_id is about that user's trip note on the trail; one with a post_id
    is about one of their Activity posts."""

    __tablename__ = "profile_reports"
    __table_args__ = (
        CheckConstraint("length(reason) between 1 and 40", name="profile_reports_reason_length_check"),
        CheckConstraint(
            f"details is null or length(details) <= {MAX_REPORT_DETAILS}",
            name="profile_reports_details_length_check",
        ),
        CheckConstraint("status in ('open', 'resolved')", name="profile_reports_status_check"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    reporter_id = Column(Uuid, nullable=False, index=True)
    profile_id = Column(Uuid, nullable=False)
    reason = Column(Text, nullable=False)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="SET NULL"))
    # Set when reporting one of their Activity posts.
    post_id = Column(Uuid, ForeignKey("activity_posts.id", ondelete="SET NULL"))
    status = Column(Text, nullable=False, default="open", server_default="open")
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(Uuid)
