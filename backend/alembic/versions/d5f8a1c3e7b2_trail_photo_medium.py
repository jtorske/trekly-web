"""trail photos: a medium (~1000 px) rendition

- trail_photos.medium_path: `{trail_id}/{uuid}-medium.webp` in the
  trail-photos bucket, made from the hero by scripts/trail_photo_medium.py
  (existing photos) and by the approval flow (new ones). Phones get it from
  the hero's srcset instead of the 1600 px file. Null until made, and for
  heroes already 1000 px or narrower; the page then uses the hero alone.

Additive only: no existing column or file changes.

Revision ID: d5f8a1c3e7b2
Revises: b3d9f6a2c8e4
Create Date: 2026-11-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d5f8a1c3e7b2"
down_revision: Union[str, Sequence[str], None] = "b3d9f6a2c8e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.trail_photos ADD COLUMN medium_path text")


def downgrade() -> None:
    op.execute("ALTER TABLE public.trail_photos DROP COLUMN IF EXISTS medium_path")
