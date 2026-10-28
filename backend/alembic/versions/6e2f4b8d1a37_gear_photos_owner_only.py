"""gear photos are owner-only, even in a public gear section

User-uploaded gear photos are no longer part of a public profile, so they
never need moderating: visitors see the catalogue photo or the line-art
icon instead. Journal photos are unchanged.

- Storage: the "gear_photos_select_public" policy goes, so only the owner
  (gear_photos_select_own) can read or sign objects in gear-photos.
- private.photo_visible drops its gear-photos branch, in case a later
  policy reuses it.
- user_gear_items.image_path leaves the client column grant, so a visitor
  can't read the path through the REST API either. The app reads the
  owner's own items through the API, as postgres, so nothing else changes.

Revision ID: 6e2f4b8d1a37
Revises: 5d1c0e7a9b42
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6e2f4b8d1a37"
down_revision: Union[str, Sequence[str], None] = "5d1c0e7a9b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def _photo_visible(with_gear: bool) -> str:
    gear = (
        """
                WHEN 'gear-photos' THEN EXISTS (
                    SELECT 1 FROM public.user_gear_items g
                    WHERE g.image_path = object_name
                      AND g.user_id::text = split_part(object_name, '/', 1)
                      AND private.section_visible(g.user_id, 'gear'))"""
        if with_gear
        else ""
    )
    return f"""
        CREATE OR REPLACE FUNCTION private.photo_visible(bucket text, object_name text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT CASE bucket{gear}
                WHEN 'hike-photos' THEN EXISTS (
                    SELECT 1 FROM public.hike_logs h
                    WHERE h.photo_path = object_name
                      AND h.user_id::text = split_part(object_name, '/', 1)
                      AND private.section_visible(h.user_id, 'journal'))
                ELSE false
            END
        $$
        """


def upgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "gear_photos_select_public" ON storage.objects')
    op.execute(_photo_visible(with_gear=False))
    op.execute(f"REVOKE SELECT (image_path) ON public.user_gear_items FROM {CLIENTS}")
    op.execute("DROP INDEX IF EXISTS public.user_gear_items_image_path_idx")


def downgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS user_gear_items_image_path_idx ON public.user_gear_items (image_path) WHERE image_path IS NOT NULL")
    op.execute(f"GRANT SELECT (image_path) ON public.user_gear_items TO {CLIENTS}")
    op.execute(_photo_visible(with_gear=True))
    op.execute(
        'CREATE POLICY "gear_photos_select_public" ON storage.objects '
        f"FOR SELECT TO {CLIENTS} USING (bucket_id = 'gear-photos' AND private.photo_visible(bucket_id, name))"
    )
