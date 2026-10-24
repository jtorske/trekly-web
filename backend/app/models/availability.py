"""Campground availability: cached provider responses, the shared request
budget, the alert poller's job lock, and users' availability alerts.

Availability is only ever fetched on demand (a user checking dates on a trail
page) or by the alert poller for active alerts, never bulk-polled. Both paths
share availability_cache (short TTL) and provider_request_budget (a global
cap on requests to the provider per minute), so they can't add up to more
traffic than the budget allows.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.catalog import JsonType, _timestamps

ALERT_STATUSES = ("active", "notified", "cancelled", "expired")
MAX_ALERT_NIGHTS = 14
MAX_ACTIVE_ALERTS_PER_USER = 10
MAX_PARTY_SIZE = 12


class AvailabilityCache(Base):
    __tablename__ = "availability_cache"

    # "<provider>:<location>:<map>:<booking category>:<start>:<end>:<party>"
    cache_key = Column(Text, primary_key=True)
    response = Column(JsonType, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, index=True)


class ProviderRequestBudget(Base):
    """One row per provider: a fixed one-minute window and how many requests
    were made in it. Every live availability request takes from it."""

    __tablename__ = "provider_request_budget"

    provider = Column(Text, primary_key=True)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    window_count = Column(Integer, nullable=False, default=0)
    total_requests = Column(Integer, nullable=False, default=0)


class JobLock(Base):
    """A lease so two runs of a scheduled job can't overlap, plus the last
    start time so runs can't happen more often than the job allows."""

    __tablename__ = "job_locks"

    name = Column(Text, primary_key=True)
    locked_by = Column(Text)
    locked_until = Column(DateTime(timezone=True))
    last_started_at = Column(DateTime(timezone=True))
    last_finished_at = Column(DateTime(timezone=True))
    last_result = Column(Text)


class AvailabilityAlert(Base):
    __tablename__ = "availability_alerts"
    __table_args__ = (
        CheckConstraint(
            "status in (" + ",".join(f"'{s}'" for s in ALERT_STATUSES) + ")",
            name="availability_alerts_status_check",
        ),
        CheckConstraint(
            f"nights between 1 and {MAX_ALERT_NIGHTS}", name="availability_alerts_nights_check"
        ),
        CheckConstraint(
            f"party_size between 1 and {MAX_PARTY_SIZE}", name="availability_alerts_party_check"
        ),
        Index("availability_alerts_user_idx", "user_id", "status"),
        Index("availability_alerts_active_idx", "status", "start_date"),
        # One active alert per user, campground and stay, even when two
        # requests race past the API's duplicate check.
        Index(
            "availability_alerts_active_unique",
            "user_id", "site_id", "start_date", "nights",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False)
    # Where to send the notification: the account email when the alert was set.
    email = Column(Text, nullable=False)
    site_id = Column(Uuid, ForeignKey("backcountry_sites.id", ondelete="RESTRICT"), nullable=False)
    # The trail the alert was set from, for linking back. Optional.
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="SET NULL"))
    start_date = Column(Date, nullable=False)
    nights = Column(Integer, nullable=False)
    party_size = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="active")
    last_checked_at = Column(DateTime(timezone=True))
    # Per-night statuses from the last check, e.g. ["full", "available"].
    last_result = Column(JsonType)
    notified_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    created_at, updated_at = _timestamps()

    site = relationship("BackcountrySite")
    trail = relationship("Trail")
