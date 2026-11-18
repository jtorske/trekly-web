"""hike_logs.unshared: the owner took this hike off the Activity feed

The profile's Activity tab now posts every hike that never was (logged while
sharing was off, onboarding, "Add past hikes"; app/activity.py backfill_posts).
A hike whose owner unticked "Share to Activity" or deleted its post is marked
here so it's never posted again unless they tick the box.

API-only: clients keep their column grants on hike_logs (none for this one).

Revision ID: e3c7a9d5f1b2
Revises: e6b2d8a4c0f7
Create Date: 2026-11-17 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e3c7a9d5f1b2"
down_revision: Union[str, Sequence[str], None] = "e6b2d8a4c0f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.hike_logs ADD COLUMN unshared boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS unshared")
