"""Trekly Guide: personalisation settings, time on trail, dog rules

- profile_preferences.guide_use_history (default true): "Use my history to
  personalize Trekly Guide". hikes_with_dog (default false) and scenery
  (jsonb list) are planner defaults. Same owner-only table and grants as
  the other answers (clients may SELECT their own row, nobody writes).
- hike_logs.duration_minutes: the optional "Time on trail" for pace. No
  client column grant: hike_logs SELECT is granted per column
  (214aa07bf743), so it stays API-only and owner-only.
- trails.dog_policy ('on_leash' | 'not_allowed' | 'unknown', default
  unknown) with dog_policy_source_url (required for a rule, like ATES
  ratings) and dog_policy_note. Filled from catalog_data/trail_dogs.json by
  scripts/trail_dogs.py.

Additive only: no existing column or row changes.

Revision ID: e1a7c4b9d2f6
Revises: c9e2a7f4b1d6
Create Date: 2026-11-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e1a7c4b9d2f6"
down_revision: Union[str, Sequence[str], None] = "c9e2a7f4b1d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.profile_preferences ADD COLUMN guide_use_history boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE public.profile_preferences ADD COLUMN hikes_with_dog boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE public.profile_preferences ADD COLUMN scenery jsonb NOT NULL DEFAULT '[]'::jsonb")

    op.execute("ALTER TABLE public.hike_logs ADD COLUMN duration_minutes integer")
    op.execute(
        "ALTER TABLE public.hike_logs ADD CONSTRAINT hike_logs_duration_check "
        "CHECK (duration_minutes IS NULL OR duration_minutes BETWEEN 10 AND 20160)"
    )

    op.execute("ALTER TABLE public.trails ADD COLUMN dog_policy text NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE public.trails ADD COLUMN dog_policy_source_url text")
    op.execute("ALTER TABLE public.trails ADD COLUMN dog_policy_note text")
    op.execute(
        "ALTER TABLE public.trails ADD CONSTRAINT trails_dog_policy_check "
        "CHECK (dog_policy IN ('on_leash', 'not_allowed', 'unknown'))"
    )
    op.execute(
        "ALTER TABLE public.trails ADD CONSTRAINT trails_dog_policy_source_check "
        "CHECK (dog_policy = 'unknown' OR dog_policy_source_url IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.trails DROP CONSTRAINT IF EXISTS trails_dog_policy_source_check")
    op.execute("ALTER TABLE public.trails DROP CONSTRAINT IF EXISTS trails_dog_policy_check")
    op.execute("ALTER TABLE public.trails DROP COLUMN IF EXISTS dog_policy_note")
    op.execute("ALTER TABLE public.trails DROP COLUMN IF EXISTS dog_policy_source_url")
    op.execute("ALTER TABLE public.trails DROP COLUMN IF EXISTS dog_policy")
    op.execute("ALTER TABLE public.hike_logs DROP CONSTRAINT IF EXISTS hike_logs_duration_check")
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS duration_minutes")
    op.execute("ALTER TABLE public.profile_preferences DROP COLUMN IF EXISTS scenery")
    op.execute("ALTER TABLE public.profile_preferences DROP COLUMN IF EXISTS hikes_with_dog")
    op.execute("ALTER TABLE public.profile_preferences DROP COLUMN IF EXISTS guide_use_history")
