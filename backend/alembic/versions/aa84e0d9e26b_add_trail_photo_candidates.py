"""add trail_photo_candidates: the search results the review page shows

One row per trail with its top candidates from scripts/find_trail_photos.py,
loaded by scripts/load_photo_candidates.py (trails matched by name and
province, so each database gets its own trail ids). This replaces reading a
local JSON file, so photos can be reviewed on the deployed site.

Private like trail_photo_reviews: RLS on, no client grants. Only the backend
(as postgres) reads it, for photo admins.

Revision ID: aa84e0d9e26b
Revises: 214aa07bf743
Create Date: 2026-10-27 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "aa84e0d9e26b"
down_revision: Union[str, Sequence[str], None] = "214aa07bf743"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.trail_photo_candidates (
            trail_id uuid PRIMARY KEY REFERENCES public.trails (id) ON DELETE RESTRICT,
            destination text,
            best_confidence text CHECK (best_confidence IS NULL OR best_confidence IN ('high', 'medium', 'low', 'off_topic')),
            -- The candidate the review page selects first; null starts on the topo fallback.
            default_choice text CHECK (default_choice IS NULL OR length(default_choice) <= 120),
            low_res boolean NOT NULL DEFAULT false,
            candidates jsonb NOT NULL CHECK (jsonb_typeof(candidates) = 'array'),
            searched_on date,
            loaded_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE public.trail_photo_candidates ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.trail_photo_candidates FROM anon, authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.trail_photo_candidates")
