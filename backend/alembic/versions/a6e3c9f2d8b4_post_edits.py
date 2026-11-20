"""post edits: the "Edited" mark, and journal writes through the API only

- activity_posts.edited_at: when its author last changed the hike behind a
  post (note, photo or date), for the "Edited" label. Only the API writes it.
- hike_logs: clients lose INSERT, UPDATE and DELETE. The app has always
  written the journal through the API (app/routers/me_hike_logs.py), which
  screens new and edited notes and photos (app/moderation.py), keeps the
  feed's posts and badges in step and marks the post edited; a direct write
  would skip all of that. Owners still read their own rows; nobody else's.

Revision ID: a6e3c9f2d8b4
Revises: f2c8a4e6b1d9
Create Date: 2026-11-19 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a6e3c9f2d8b4"
down_revision: Union[str, Sequence[str], None] = "f2c8a4e6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# What migration b4e7a2c9d1f3 let clients write, put back on downgrade.
CLIENT_COLUMNS = "id, user_id, trail_id, hiked_on, note, photo_path, created_at, updated_at"


def upgrade() -> None:
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN edited_at timestamptz")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON public.hike_logs FROM anon, authenticated")


def downgrade() -> None:
    op.execute(f"GRANT INSERT ({CLIENT_COLUMNS}), UPDATE ({CLIENT_COLUMNS}) ON public.hike_logs TO authenticated")
    op.execute("GRANT DELETE ON public.hike_logs TO authenticated")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS edited_at")
