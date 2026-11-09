"""home "Outside Canada", the visibility choice, and no interests step

- profiles.home_province also takes 'outside' ("Outside Canada"), alongside
  the 13 two-letter codes and null ("Prefer not to say"). It earns its own
  badge and shows under the same show_home_province switch.
- profile_settings.visibility_chosen_at: when the user last chose Public or
  Private themselves (the /welcome privacy step, or Settings → Privacy). The
  API sets it; clients get no grant on it. The setup flow can't be finished
  or skipped until it's set, so everyone makes that choice. Existing rows
  stay null: anyone who already finished or skipped the flow isn't asked.
- The /welcome "What gets you out there?" (interests) step is gone: anyone
  paused on it resumes at the step after it ("regions"), and the step check
  no longer allows it. profile_preferences.interests stays, unused, for now.

Revision ID: c7e3a9f1d5b2
Revises: c4f8e2a6d1b3
Create Date: 2026-11-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7e3a9f1d5b2"
down_revision: Union[str, Sequence[str], None] = "c4f8e2a6d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODES = "'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'"

STEPS_BEFORE = (
    "'name', 'photo', 'home', 'style', 'experience', 'interests', 'regions', 'hiked', 'pack', 'units', 'privacy', 'done'"
)
STEPS_AFTER = "'name', 'photo', 'home', 'style', 'experience', 'regions', 'hiked', 'pack', 'units', 'privacy', 'done'"


def _step_check(steps: str) -> None:
    op.execute("ALTER TABLE public.profile_preferences DROP CONSTRAINT profile_preferences_onboarding_step_check")
    op.execute(
        "ALTER TABLE public.profile_preferences ADD CONSTRAINT profile_preferences_onboarding_step_check "
        f"CHECK (onboarding_step IS NULL OR onboarding_step IN ({steps}))"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_home_province_check")
    op.execute(
        "ALTER TABLE public.profiles ADD CONSTRAINT profiles_home_province_check "
        f"CHECK (home_province IS NULL OR home_province IN ({CODES}, 'outside'))"
    )
    op.execute("ALTER TABLE public.profile_settings ADD COLUMN visibility_chosen_at timestamptz")
    op.execute("UPDATE public.profile_preferences SET onboarding_step = 'regions' WHERE onboarding_step = 'interests'")
    _step_check(STEPS_AFTER)


def downgrade() -> None:
    _step_check(STEPS_BEFORE)
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS visibility_chosen_at")
    op.execute("UPDATE public.profiles SET home_province = NULL WHERE home_province = 'outside'")
    op.execute("ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_home_province_check")
    op.execute(
        "ALTER TABLE public.profiles ADD CONSTRAINT profiles_home_province_check "
        f"CHECK (home_province IS NULL OR home_province IN ({CODES}))"
    )
