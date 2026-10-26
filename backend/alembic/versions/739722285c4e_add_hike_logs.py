"""add hike logs (the Trail Journal) and a private hike-photos bucket

- hike_logs: one row per user per trail they've hiked, with the date and an
  optional note and photo. Private: RLS lets only the owner select, insert,
  update or delete their rows. Deleting an auth user cascades; trails are
  retired, never deleted, so the trail FK is RESTRICT and a log never loses
  its trail.
- hike-photos: private Storage bucket (signed URLs only). The client resizes
  and re-encodes photos before upload, which strips EXIF/GPS, so the bucket
  only takes small WebP/JPEG files at `{uid}/{uuid}.webp|jpg`. As with
  avatars there is no UPDATE policy: a new photo is a new object.

Revision ID: 739722285c4e
Revises: f3a4b5c6d7e8
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "739722285c4e"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_FOLDER = "(storage.foldername(name))[1] = (select auth.uid())::text"
PHOTO_NAME = r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.(webp|jpg)$"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.hike_logs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
            trail_id uuid NOT NULL REFERENCES public.trails (id) ON DELETE RESTRICT,
            hiked_on date NOT NULL CHECK (hiked_on >= date '1900-01-01'),
            note text CHECK (note IS NULL OR length(note) BETWEEN 1 AND 500),
            photo_path text CHECK (photo_path IS NULL OR photo_path ~ '{PHOTO_NAME}'),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT hike_logs_user_trail_key UNIQUE (user_id, trail_id),
            -- The photo must live in the owner's own folder.
            CONSTRAINT hike_logs_photo_owner_check
                CHECK (photo_path IS NULL OR split_part(photo_path, '/', 1) = user_id::text)
        )
        """.replace("{PHOTO_NAME}", PHOTO_NAME)
    )
    op.execute("CREATE INDEX hike_logs_trail_idx ON public.hike_logs (trail_id)")

    op.execute("ALTER TABLE public.hike_logs ENABLE ROW LEVEL SECURITY")
    own = "user_id = (select auth.uid())"
    policies = [
        ("select", f"USING ({own})"),
        ("insert", f"WITH CHECK ({own})"),
        ("update", f"USING ({own}) WITH CHECK ({own})"),
        ("delete", f"USING ({own})"),
    ]
    for action, clause in policies:
        op.execute(
            f'CREATE POLICY "hike_logs_{action}_own" ON public.hike_logs '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    op.execute("REVOKE ALL ON public.hike_logs FROM anon")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.hike_logs TO authenticated")

    op.execute(
        "INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        "VALUES ('hike-photos', 'hike-photos', false, 1048576, ARRAY['image/webp','image/jpeg']) "
        "ON CONFLICT (id) DO NOTHING"
    )
    op.execute(
        'CREATE POLICY "hike_photos_insert_own" ON storage.objects '
        "FOR INSERT TO authenticated WITH CHECK "
        f"(bucket_id = 'hike-photos' AND {OWN_FOLDER} AND name ~ '{PHOTO_NAME}')"
    )
    for action in ("select", "delete"):
        op.execute(
            f'CREATE POLICY "hike_photos_{action}_own" ON storage.objects '
            f"FOR {action.upper()} TO authenticated USING "
            f"(bucket_id = 'hike-photos' AND {OWN_FOLDER})"
        )


def downgrade() -> None:
    for action in ("select", "insert", "delete"):
        op.execute(f'DROP POLICY IF EXISTS "hike_photos_{action}_own" ON storage.objects')
    # Objects must be removed through the Storage API before a bucket can be
    # deleted, so the (private, empty-by-policy) bucket is left in place.
    op.execute("DROP TABLE IF EXISTS public.hike_logs")
