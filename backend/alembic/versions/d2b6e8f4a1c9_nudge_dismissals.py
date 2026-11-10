"""nudges toward the community settings, and which ones each user put away

- nudge_dismissals: one row per user per nudge (hike_share, activity_card,
  hiked_by; app/nudges.py) once they tap ✕, decide once in the Mark as
  hiked dialog, or turn the setting it points at on. Rows are never
  removed, so a nudge never comes back. Written only by the API: row-level
  security is on with no policies, and anon/authenticated hold no grants.
- Backfill: anyone who already has "Share my activity in the feed" or "Show
  me in community features" on has made their choice, so those nudges are
  put away for them now (turning the setting off later won't bring them back).

No setting changes here: both stay as each user left them.

Revision ID: d2b6e8f4a1c9
Revises: a8c3f1d5e7b2
Create Date: 2026-11-09 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d2b6e8f4a1c9"
down_revision: Union[str, Sequence[str], None] = "a8c3f1d5e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.nudge_dismissals (
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            nudge text NOT NULL
                CONSTRAINT nudge_dismissals_nudge_check
                CHECK (nudge IN ('hike_share', 'activity_card', 'hiked_by')),
            dismissed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, nudge)
        )
        """
    )
    op.execute("ALTER TABLE public.nudge_dismissals ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.nudge_dismissals FROM {CLIENTS}")
    op.execute(
        """
        INSERT INTO public.nudge_dismissals (user_id, nudge)
        SELECT s.user_id, n.nudge
        FROM public.profile_settings s
        JOIN auth.users u ON u.id = s.user_id
        CROSS JOIN (VALUES ('hike_share', 'share_activity'), ('activity_card', 'share_activity'),
                           ('hiked_by', 'show_in_community')) AS n (nudge, setting)
        WHERE (n.setting = 'share_activity' AND s.share_activity)
           OR (n.setting = 'show_in_community' AND s.show_in_community)
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.nudge_dismissals")
