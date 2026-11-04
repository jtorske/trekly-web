"""visit streaks, with their own privacy switch

- visit_streaks: one row per user with the last visit's date and the
  current and longest streak (app/streaks.py). Written only by the API.
  Row-level security is on with no policies, and anon/authenticated hold
  no grants, so clients can neither read nor set the counts.
- profile_settings.show_visit_streak: "Visit streak" under Settings →
  Privacy. Off for everyone, new and existing, until they turn it on.
  Clients may update it directly, like the other switches.

Revision ID: f9c2d4e6a8b1
Revises: e8f1c3a5b7d9
Create Date: 2026-11-03 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f9c2d4e6a8b1"
down_revision: Union[str, Sequence[str], None] = "e8f1c3a5b7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.visit_streaks (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            current_streak integer NOT NULL CONSTRAINT visit_streaks_current_check CHECK (current_streak >= 1),
            longest_streak integer NOT NULL,
            last_visit_date date NOT NULL,
            CONSTRAINT visit_streaks_longest_check CHECK (longest_streak >= current_streak)
        )
        """
    )
    op.execute("ALTER TABLE public.visit_streaks ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.visit_streaks FROM {CLIENTS}")
    op.execute(
        "ALTER TABLE public.profile_settings ADD COLUMN show_visit_streak boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT UPDATE (show_visit_streak) ON public.profile_settings TO authenticated")


def downgrade() -> None:
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS show_visit_streak")
    op.execute("DROP TABLE IF EXISTS public.visit_streaks")
