"""make avatars publicly readable and accept only processed images

The client now crops avatars to a square, resizes them to 512x512 and
re-encodes them (which strips EXIF) before upload, so the bucket only needs
to take small WebP/JPEG files. A 1 MB cap means an unprocessed phone photo
can't be stored even if the client is bypassed.

- avatars bucket: public read (anyone with the URL), 1 MB, WebP/JPEG only.
- Writes stay owner-only: INSERT is limited to `{uid}/{uuid}.webp|jpg` in
  the user's own folder; there is still no UPDATE policy, so nobody can
  overwrite an existing object (each change uploads a new file and deletes
  the old one, which also gives every change a fresh, cache-busting URL).
- SELECT stays owner-only: public URLs don't go through RLS, but listing a
  folder does, so other users can't enumerate avatars.

Revision ID: 9a769eeb0dae
Revises: f270bc5e799a
Create Date: 2026-10-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9a769eeb0dae"
down_revision: Union[str, Sequence[str], None] = "f270bc5e799a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_FOLDER = "(storage.foldername(name))[1] = (select auth.uid())::text"
AVATAR_NAME = r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.(webp|jpg)$"


def upgrade() -> None:
    op.execute(
        "UPDATE storage.buckets SET public = true, file_size_limit = 1048576, "
        "allowed_mime_types = ARRAY['image/webp','image/jpeg'] WHERE id = 'avatars'"
    )
    op.execute('DROP POLICY IF EXISTS "avatars_insert_own" ON storage.objects')
    op.execute(
        'CREATE POLICY "avatars_insert_own" ON storage.objects '
        "FOR INSERT TO authenticated WITH CHECK "
        f"(bucket_id = 'avatars' AND {OWN_FOLDER} AND name ~ '{AVATAR_NAME}')"
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "avatars_insert_own" ON storage.objects')
    op.execute(
        'CREATE POLICY "avatars_insert_own" ON storage.objects '
        f"FOR INSERT TO authenticated WITH CHECK (bucket_id = 'avatars' AND {OWN_FOLDER})"
    )
    op.execute(
        "UPDATE storage.buckets SET public = false, file_size_limit = 2097152, "
        "allowed_mime_types = ARRAY['image/jpeg','image/png','image/webp'] WHERE id = 'avatars'"
    )
