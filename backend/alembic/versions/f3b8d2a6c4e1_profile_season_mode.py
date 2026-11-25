"""profile_preferences.season_mode: Explore's Summer / Winter choice

Null (the default) follows the season (app/season.py); 'summer' or 'winter'
is a choice the person made with Explore's toggle, remembered across devices.
Written only through PATCH /api/me/preferences, like the other columns.

Revision ID: f3b8d2a6c4e1
Revises: e1a7c4b9d2f6
Create Date: 2026-11-24 19:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3b8d2a6c4e1"
down_revision: Union[str, Sequence[str], None] = "e1a7c4b9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE public.profile_preferences
          ADD COLUMN season_mode text,
          ADD CONSTRAINT profile_preferences_season_mode_check
            CHECK (season_mode IS NULL OR season_mode IN ('summer', 'winter'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE public.profile_preferences DROP COLUMN IF EXISTS season_mode")
