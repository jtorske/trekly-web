"""profile display_name from OAuth metadata

Email sign-ups pass `display_name` in their user metadata; OAuth providers
such as Google put the person's name in `full_name` or `name` instead. The
new-user trigger now takes the first non-blank of the three, trimmed to the
profiles.display_name limit of 60. Existing profiles are not touched.

Revision ID: e7f8a9b0c1d2
Revises: d2e3f4a5b6c7
Create Date: 2026-10-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _function(display_name_sql: str) -> str:
    # Same shape as the original in e5f6a7b8c9d0: SECURITY DEFINER with an
    # empty search_path, and idempotent on the profile row.
    return f"""
        CREATE OR REPLACE FUNCTION public.handle_new_user_profile()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
            INSERT INTO public.profiles (id, display_name)
            VALUES (NEW.id, {display_name_sql})
            ON CONFLICT (id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """


NAME_FROM_ANY_PROVIDER = """NULLIF(left(btrim(COALESCE(
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'display_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'full_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'name'), '')
            )), 60), '')"""

NAME_FROM_SIGNUP_FORM = "NULLIF(left(btrim(NEW.raw_user_meta_data ->> 'display_name'), 60), '')"


def upgrade() -> None:
    op.execute(_function(NAME_FROM_ANY_PROVIDER))
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_profile() FROM PUBLIC, anon, authenticated")


def downgrade() -> None:
    op.execute(_function(NAME_FROM_SIGNUP_FORM))
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_profile() FROM PUBLIC, anon, authenticated")
