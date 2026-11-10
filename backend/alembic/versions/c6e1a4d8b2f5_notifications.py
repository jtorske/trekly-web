"""notifications: in-app notifications and which types each user wants

- notifications: one row per event for one recipient: a new follower, a
  follow request, a request approved, a high five (with its post), and
  later a comment. Grouping ("Ana and 3 others high-fived your hike") is
  done when they're read, so each row keeps its own read state. Rows go
  with either user (ON DELETE CASCADE) and with the post.
- notification_preferences: one row per user who changed anything; a
  missing row means every type is on.

Only the API reads and writes both tables: row-level security is on with
no policies, and clients hold no grants. Nothing is emailed or pushed.

Revision ID: c6e1a4d8b2f5
Revises: b3d7f2a9c4e1
Create Date: 2026-11-10 09:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c6e1a4d8b2f5"
down_revision: Union[str, Sequence[str], None] = "b3d7f2a9c4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
KINDS = "'new_follower', 'follow_request', 'request_approved', 'high_five', 'comment'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE public.notifications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            actor_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            kind text NOT NULL CONSTRAINT notifications_kind_check CHECK (kind IN ({KINDS})),
            post_id uuid REFERENCES public.activity_posts (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            read_at timestamptz,
            CONSTRAINT notifications_not_self_check CHECK (user_id <> actor_id)
        )
        """
    )
    op.execute("CREATE INDEX notifications_user_idx ON public.notifications (user_id, created_at DESC)")
    op.execute("CREATE INDEX notifications_actor_idx ON public.notifications (actor_id)")
    op.execute(
        """
        CREATE TABLE public.notification_preferences (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            new_follower boolean NOT NULL DEFAULT true,
            follow_request boolean NOT NULL DEFAULT true,
            request_approved boolean NOT NULL DEFAULT true,
            high_five boolean NOT NULL DEFAULT true,
            comment boolean NOT NULL DEFAULT true,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for table in ("notifications", "notification_preferences"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM {CLIENTS}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.notification_preferences")
    op.execute("DROP TABLE IF EXISTS public.notifications")
