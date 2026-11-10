"""Accounts that aren't ordinary hikers: the official Trekly account and demo hikers.

A label is set only by the scripts (scripts/official_account.py,
scripts/demo_accounts.py) through the backend's own database connection.
Clients can't read or write the table (migration f4a9c2e7b1d3); the API puts
the label on every author it returns, so the "Trekly team" and "Demo account"
badges show wherever the name does. app/account_labels.py holds the rules.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base

ACCOUNT_LABELS = ("official", "demo")


class AccountLabel(Base):
    __tablename__ = "account_labels"
    __table_args__ = (CheckConstraint("label in ('official', 'demo')", name="account_labels_label_check"),)

    # Same value as auth.users.id; the FK (ON DELETE CASCADE) is added in the migration.
    user_id = Column(Uuid, primary_key=True)
    label = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
