"""hike_logs.unshared and activity_posts.owner_only: every hike in its owner's Activity tab

The profile's Activity tab now shows every hike to its owner: hikes that never
posted (logged while sharing was off, onboarding, "Add past hikes") get a post
that only the owner sees (app/activity.py backfill_posts), until they share it
or share their past hikes all at once.

- activity_posts.owner_only: the post shows to its owner only, whatever their
  settings. private.activity_post_visible (row-level security, last defined in
  f4a9c2e7b1d3) gains `NOT a.owner_only`, matching app/activity.py visible_where.
  Existing posts were all shared on purpose, so they default to false.
- profile_settings.past_hikes_answered_at: when the owner answered the
  one-time "Share your past hikes?" prompt.
- hike_logs.unshared: the owner deleted the hike's post; the backfill leaves
  that hike off their Activity tab.

API-only: clients keep their column grants (none for these).

Revision ID: e3c7a9d5f1b2
Revises: d7a3f9c1e5b8
Create Date: 2026-11-17 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e3c7a9d5f1b2"
down_revision: Union[str, Sequence[str], None] = "d7a3f9c1e5b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _visible_function(owner_only: bool) -> str:
    """private.activity_post_visible as in f4a9c2e7b1d3, plus (after) owner-only posts never show."""
    extra = "AND NOT a.owner_only" if owner_only else ""
    return f"""
        CREATE OR REPLACE FUNCTION private.activity_post_visible(post uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM public.activity_posts a
                JOIN public.profiles p ON p.id = a.user_id
                JOIN public.profile_settings s ON s.user_id = a.user_id
                LEFT JOIN public.hike_logs h ON h.id = a.hike_log_id
                WHERE a.id = post
                  AND a.hidden_at IS NULL
                  {extra}
                  AND p.username IS NOT NULL
                  AND NOT s.is_private
                  AND s.share_activity
                  AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = a.user_id)
                  AND CASE a.kind WHEN 'rank' THEN s.show_rank WHEN 'announcement' THEN EXISTS (
                      SELECT 1 FROM public.account_labels l WHERE l.user_id = a.user_id AND l.label = 'official'
                  ) ELSE s.show_journal END
                  AND NOT (a.reveals_date AND s.hide_hike_dates)
                  AND (a.kind <> 'hike' OR h.hiked_on IS NULL OR h.hiked_on <= current_date + 1)
            )
        $$
        """


def upgrade() -> None:
    op.execute("ALTER TABLE public.hike_logs ADD COLUMN unshared boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN owner_only boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE public.profile_settings ADD COLUMN past_hikes_answered_at timestamptz")
    op.execute(_visible_function(owner_only=True))


def downgrade() -> None:
    op.execute(_visible_function(owner_only=False))
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS past_hikes_answered_at")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS owner_only")
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS unshared")
