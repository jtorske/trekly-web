"""The admin area's own table, and a read-only view of Supabase's auth.users.

admin_audit_log records every admin action (who, what, when, on whom). It
has no client access and nothing in the app deletes from it; rows outlive
the accounts they mention (no foreign keys).

AUTH_USERS describes the columns of auth.users the admin area reads. It is
on its own MetaData, so it's never created, migrated or dropped from here:
Supabase owns that table. Writes to accounts (ban, password reset) go
through the Supabase admin API instead (app/supabase_admin.py).
"""

import uuid

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, MetaData, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base

AUDIT_ACTIONS = (
    "hide_profile",
    "unhide_profile",
    "clear_username",
    "ban_user",
    "unban_user",
    "send_password_reset",
    "resolve_report",
    "reopen_report",
)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        CheckConstraint(
            "action in (" + ",".join(f"'{a}'" for a in AUDIT_ACTIONS) + ")",
            name="admin_audit_log_action_check",
        ),
        Index("admin_audit_log_created_idx", "created_at"),
        Index("admin_audit_log_target_idx", "target_user_id", "created_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id = Column(Uuid, nullable=False)
    action = Column(Text, nullable=False)
    target_user_id = Column(Uuid)
    target_report_id = Column(Uuid)
    # What changed, e.g. {"username": "old_name"} or {"reason": "Spam"}.
    details = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


auth_metadata = MetaData(schema="auth")

AUTH_USERS = Table(
    "users",
    auth_metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("last_sign_in_at", DateTime(timezone=True)),
    Column("banned_until", DateTime(timezone=True)),
    Column("raw_app_meta_data", JSON().with_variant(JSONB(), "postgresql")),
)
