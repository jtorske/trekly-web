"""the full milestone set: trail tags, and any configured milestone can be featured

- trails.tags: catalogue labels (jsonb array, default empty). The Rockies
  trails known for autumn larches are tagged "larch" here, matching
  catalog_data/trails_canada.json, so the Larch madness milestone works
  without a reseed.
- featured_badges.milestone: the check listed the four original milestones.
  Which ids exist now lives in app/milestones_config.py (the API refuses
  unknown or unearned ones and never shows them), so the check only bounds
  the length.

Idempotent, so it can be applied by hand on a database where another
branch's migration is current.

Revision ID: a4c7e2b9d1f3
Revises: 0c5e7d2b9f41
Create Date: 2026-10-28 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a4c7e2b9d1f3"
down_revision: Union[str, Sequence[str], None] = "0c5e7d2b9f41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LARCH = (
    ("Sentinel Pass via Larch Valley", "AB"),
    ("Eiffel Lake", "AB"),
    ("Lake Agnes Tea House", "AB"),
    ("Sunshine Meadows", "AB"),
    ("Egypt Lake / Healy Pass", "AB"),
    ("Shadow Lake - Twin Lakes - Redearth Creek Loop", "AB"),
    ("Skoki Valley Trail", "AB"),
    ("Elizabeth Parker Hut / Lake O'Hara", "BC"),
    ("Mount Assiniboine via Sunshine Meadows", "BC"),
    ("Rockwall Trail", "BC"),
    ("Chester Lake", "AB"),
    ("Ptarmigan Cirque", "AB"),
    ("Rawson Lake", "AB"),
    ("Burstall Pass", "AB"),
    ("Tent Ridge Horseshoe", "AB"),
    ("Galatea Lakes", "AB"),
    ("Northover Ridge / Three Isle Lake", "AB"),
)
ORIGINAL = "'first-hike', 'first-overnight', 'five-parks', 'hundred-km'"


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("ALTER TABLE public.trails ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '[]'::jsonb")
    pairs = ", ".join(f"({_quote(name)}, {_quote(province)})" for name, province in LARCH)
    op.execute(
        f"""
        UPDATE public.trails SET tags = '["larch"]'::jsonb
        WHERE (name, province_code) IN ({pairs})
        """
    )

    op.execute("ALTER TABLE public.featured_badges DROP CONSTRAINT IF EXISTS featured_badges_milestone_check")
    op.execute(
        """
        ALTER TABLE public.featured_badges ADD CONSTRAINT featured_badges_milestone_check
            CHECK (milestone IS NULL OR length(milestone) BETWEEN 1 AND 40)
        """
    )


def downgrade() -> None:
    # Picks of the newer milestones can't satisfy the old check.
    op.execute(f"DELETE FROM public.featured_badges WHERE milestone IS NOT NULL AND milestone NOT IN ({ORIGINAL})")
    op.execute("ALTER TABLE public.featured_badges DROP CONSTRAINT featured_badges_milestone_check")
    op.execute(
        f"""
        ALTER TABLE public.featured_badges ADD CONSTRAINT featured_badges_milestone_check
            CHECK (milestone IS NULL OR milestone IN ({ORIGINAL}))
        """
    )
    op.execute("ALTER TABLE public.trails DROP COLUMN tags")
