"""Trekly Guide chat counts: how many messages each user sent today (for the
daily cap) and daily totals for the admin area. Counts only: no message text,
no replies, no trails. Clients have no grants on either table; only the API
writes them (migration a9d4c7e2b6f1). A user's rows go with their account.
"""

from sqlalchemy import Column, Date, Integer, Uuid

from app.database import Base

METRICS = ("messages", "tool_calls", "fallbacks", "provider_errors", "rate_limited",
           "moderation_blocked", "cap_reached", "guarded")


class GuideChatUsage(Base):
    __tablename__ = "guide_chat_usage"

    # Same value as auth.users.id; the FK to auth.users (cascade) is in the migration.
    user_id = Column(Uuid, primary_key=True)
    day = Column(Date, primary_key=True)
    messages = Column(Integer, nullable=False, default=0, server_default="0")


class GuideChatMetrics(Base):
    """Daily totals across Trekly."""

    __tablename__ = "guide_chat_metrics"

    day = Column(Date, primary_key=True)
    messages = Column(Integer, nullable=False, default=0, server_default="0")
    tool_calls = Column(Integer, nullable=False, default=0, server_default="0")
    # Answered with the guided form instead (any reason).
    fallbacks = Column(Integer, nullable=False, default=0, server_default="0")
    provider_errors = Column(Integer, nullable=False, default=0, server_default="0")
    rate_limited = Column(Integer, nullable=False, default=0, server_default="0")
    moderation_blocked = Column(Integer, nullable=False, default=0, server_default="0")
    # A user's or the global daily cap was reached.
    cap_reached = Column(Integer, nullable=False, default=0, server_default="0")
    # Replies replaced by the guard (unknown trail name, "safe").
    guarded = Column(Integer, nullable=False, default=0, server_default="0")
