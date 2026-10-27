"""add trail photos (one credited hero photo per trail) and a public bucket

- trail_photos: the current photo for a trail, with what the credit line
  needs: photographer, license, license URL and source page. `source` is
  'commons' or 'openverse' for a reviewed candidate (license and source URL
  required) or 'owner' for a photo the site owner uploaded (credited by
  name, no license). Public read; only the backend writes.
- trail_photo_reviews: the last review decision per trail ('approved',
  'rejected' or 'uploaded'), so the review page knows what's done. Private:
  no client access at all.
- trail-photos: public Storage bucket for the processed WebP files at
  `{trail_id}/{uuid}-hero.webp` and `{trail_id}/{uuid}-thumb.webp`. There
  are no client write policies: only the backend (service role) uploads or
  deletes, after checking PHOTO_ADMIN_USER_IDS. Each publish uses new names,
  so nothing is overwritten and every change gets a fresh, cache-busting URL.

Revision ID: dfc16ffa2de3
Revises: 9b2ea6b22b6c
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "dfc16ffa2de3"
down_revision: Union[str, Sequence[str], None] = "9b2ea6b22b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHOTO_NAME = r"^[0-9a-f-]{36}/[0-9a-f-]{36}-(hero|thumb)\.webp$"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.trail_photos (
            trail_id uuid PRIMARY KEY REFERENCES public.trails (id) ON DELETE RESTRICT,
            source text NOT NULL CHECK (source IN ('commons', 'openverse', 'owner')),
            -- Where the photo was first published: 'Wikimedia Commons', 'Flickr', ...
            origin text CHECK (origin IS NULL OR length(origin) BETWEEN 1 AND 80),
            candidate_id text CHECK (candidate_id IS NULL OR length(candidate_id) <= 120),
            photographer text NOT NULL CHECK (length(photographer) BETWEEN 1 AND 200),
            license text CHECK (license IS NULL OR length(license) BETWEEN 1 AND 80),
            license_url text CHECK (license_url IS NULL OR license_url ~ '^https?://'),
            source_url text CHECK (source_url IS NULL OR source_url ~ '^https?://'),
            hero_path text NOT NULL CHECK (hero_path ~ '{PHOTO_NAME}'),
            thumb_path text NOT NULL CHECK (thumb_path ~ '{PHOTO_NAME}'),
            hero_width integer NOT NULL CHECK (hero_width > 0),
            hero_height integer NOT NULL CHECK (hero_height > 0),
            approved_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            -- A reused photo must say whose it is, under what license, and where it came from.
            CONSTRAINT trail_photos_credit_check
                CHECK (source = 'owner' OR (license IS NOT NULL AND source_url IS NOT NULL))
        )
        """.replace("{PHOTO_NAME}", PHOTO_NAME)
    )
    op.execute(
        """
        CREATE TABLE public.trail_photo_reviews (
            trail_id uuid PRIMARY KEY REFERENCES public.trails (id) ON DELETE RESTRICT,
            decision text NOT NULL CHECK (decision IN ('approved', 'rejected', 'uploaded')),
            candidate_id text CHECK (candidate_id IS NULL OR length(candidate_id) <= 120),
            reviewed_by uuid NOT NULL,
            reviewed_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute("ALTER TABLE public.trail_photos ENABLE ROW LEVEL SECURITY")
    op.execute(
        'CREATE POLICY "trail_photos_select_all" ON public.trail_photos '
        "FOR SELECT TO anon, authenticated USING (true)"
    )
    op.execute("REVOKE ALL ON public.trail_photos FROM anon, authenticated")
    op.execute("GRANT SELECT ON public.trail_photos TO anon, authenticated")

    op.execute("ALTER TABLE public.trail_photo_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.trail_photo_reviews FROM anon, authenticated")

    op.execute(
        "INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        "VALUES ('trail-photos', 'trail-photos', true, 2097152, ARRAY['image/webp']) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.trail_photo_reviews")
    op.execute("DROP TABLE IF EXISTS public.trail_photos")
    # Objects must be removed through the Storage API before a bucket can be
    # deleted, so the bucket is left in place (as with hike-photos).
