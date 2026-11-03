"""home province or territory, with its own privacy switch

- profiles.home_province: one of the 13 two-letter codes, or null for
  "Prefer not to say" (everyone starts there). Like home_region it gets no
  client column grant, so it's never readable through the REST API; the
  API shows it to visitors only when the switch below is on.
- profile_settings.show_home_province: "Home province" under Settings →
  Privacy. Off for everyone, new and existing, until they turn it on.
  Clients may update it directly, like the other switches.

Revision ID: 4f8b2c6d9e13
Revises: d3b8f1a6c2e4
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "4f8b2c6d9e13"
down_revision: Union[str, Sequence[str], None] = "d3b8f1a6c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODES = "'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.profiles ADD COLUMN home_province text "
        f"CONSTRAINT profiles_home_province_check CHECK (home_province IS NULL OR home_province IN ({CODES}))"
    )
    op.execute(
        "ALTER TABLE public.profile_settings ADD COLUMN show_home_province boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT UPDATE (show_home_province) ON public.profile_settings TO authenticated")


def downgrade() -> None:
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS show_home_province")
    op.execute("ALTER TABLE public.profiles DROP COLUMN IF EXISTS home_province")
