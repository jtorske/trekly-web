"""featured badges: up to three earned badges a user shows on their profile

- featured_badges: one row per slot (position 0-2), each a trail badge
  (trail_id) or a milestone badge (milestone). Unique per user by position,
  trail and milestone, so "at most three" and "no duplicates" are database
  rules. A trail badge references the owner's own hike log
  (user_id, trail_id), so it can only exist while that hike does and is
  deleted with it. Whether a milestone is earned is checked by the API
  (app/featured.py), which also never shows one that isn't.
- RLS: only the owner inserts, updates or deletes their rows; anyone reads
  them while the owner's Trail Journal is public (private.section_visible,
  migration 214aa07bf743), the same switch the API follows.

Revision ID: 8b3e5f1c2d40
Revises: 6e2f4b8d1a37
Create Date: 2026-10-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "8b3e5f1c2d40"
down_revision: Union[str, Sequence[str], None] = "6e2f4b8d1a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
MILESTONES = "'first-hike', 'first-overnight', 'five-parks', 'hundred-km'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE public.featured_badges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
            position smallint NOT NULL CHECK (position BETWEEN 0 AND 2),
            trail_id uuid,
            milestone text CHECK (milestone IS NULL OR milestone IN ({MILESTONES})),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT featured_badges_one_kind_check CHECK ((trail_id IS NULL) <> (milestone IS NULL)),
            CONSTRAINT featured_badges_position_key UNIQUE (user_id, position),
            CONSTRAINT featured_badges_trail_key UNIQUE (user_id, trail_id),
            CONSTRAINT featured_badges_milestone_key UNIQUE (user_id, milestone),
            -- Only a trail you've logged, and it goes when the hike does.
            CONSTRAINT featured_badges_hike_fkey FOREIGN KEY (user_id, trail_id)
                REFERENCES public.hike_logs (user_id, trail_id) ON DELETE CASCADE
        )
        """
    )

    op.execute("ALTER TABLE public.featured_badges ENABLE ROW LEVEL SECURITY")
    own = "user_id = (select auth.uid())"
    for action, clause in (
        ("insert", f"WITH CHECK ({own})"),
        ("update", f"USING ({own}) WITH CHECK ({own})"),
        ("delete", f"USING ({own})"),
    ):
        op.execute(
            f'CREATE POLICY "featured_badges_{action}_own" ON public.featured_badges '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    op.execute(
        'CREATE POLICY "featured_badges_select_own" ON public.featured_badges '
        f"FOR SELECT TO authenticated USING ({own})"
    )
    op.execute(
        'CREATE POLICY "featured_badges_select_public" ON public.featured_badges '
        f"FOR SELECT TO {CLIENTS} USING (private.section_visible(user_id, 'journal'))"
    )
    op.execute("REVOKE ALL ON public.featured_badges FROM anon")
    op.execute("GRANT SELECT ON public.featured_badges TO anon")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.featured_badges TO authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.featured_badges")
