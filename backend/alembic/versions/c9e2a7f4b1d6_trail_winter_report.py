"""trails.winter_report_url: the official grooming or trail conditions report

Where to check today's grooming and trail conditions for a winter trail (for
example Parks Canada's trail conditions page). Nullable; written from
catalog_data/trail_winter.json by scripts/trail_winter.py sync-db. Public
read like the other trail columns.

Revision ID: c9e2a7f4b1d6
Revises: d5f8a1c3e7b2
Create Date: 2026-11-24 12:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c9e2a7f4b1d6"
down_revision: Union[str, Sequence[str], None] = "d5f8a1c3e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.trails ADD COLUMN winter_report_url text")


def downgrade() -> None:
    op.execute("ALTER TABLE public.trails DROP COLUMN IF EXISTS winter_report_url")
