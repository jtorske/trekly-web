"""private trail preferences and /welcome progress

- profile_preferences: one row per user, made by the API on the first save.
  Hiking style, experience, interests and favourite regions (used only to
  order trail recommendations), plus where the /welcome setup flow is up to
  and whether it was finished or skipped. No row = nothing answered, flow
  not done, so existing users see the flow once too.
- Private to the owner. Row-level security on; a signed-in client can read
  only its own row and can't write at all (the app writes through the API);
  anon gets nothing. Nothing here is joined into public profiles.

Revision ID: 6d1a8f3b2c57
Revises: f9c2d4e6a8b1
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6d1a8f3b2c57"
down_revision: Union[str, Sequence[str], None] = "f9c2d4e6a8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.profile_preferences (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            hiking_style text
                CONSTRAINT profile_preferences_hiking_style_check
                CHECK (hiking_style IS NULL OR hiking_style IN ('day', 'overnight', 'both')),
            experience text
                CONSTRAINT profile_preferences_experience_check
                CHECK (experience IS NULL OR experience IN ('new', 'few_seasons', 'seasoned')),
            interests jsonb NOT NULL DEFAULT '[]'::jsonb
                CONSTRAINT profile_preferences_interests_check CHECK (jsonb_typeof(interests) = 'array'),
            favourite_regions jsonb NOT NULL DEFAULT '[]'::jsonb
                CONSTRAINT profile_preferences_regions_check CHECK (jsonb_typeof(favourite_regions) = 'array'),
            onboarding_step text
                CONSTRAINT profile_preferences_onboarding_step_check
                CHECK (onboarding_step IS NULL OR onboarding_step IN (
                    'name', 'photo', 'home', 'style', 'experience', 'interests',
                    'regions', 'units', 'privacy', 'done')),
            onboarding_status text
                CONSTRAINT profile_preferences_onboarding_status_check
                CHECK (onboarding_status IS NULL OR onboarding_status IN ('completed', 'skipped')),
            onboarding_finished_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE public.profile_preferences ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.profile_preferences FROM {CLIENTS}")
    op.execute(
        'CREATE POLICY "profile_preferences_select_own" ON public.profile_preferences '
        "FOR SELECT TO authenticated USING (user_id = (select auth.uid()))"
    )
    op.execute("GRANT SELECT ON public.profile_preferences TO authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.profile_preferences")
