"""activity comments: comments on Activity posts, with one level of replies

- activity_comments: plain text (1-500 characters, null while moderation
  withholds it), a post (ON DELETE CASCADE), its author (auth.users, ON
  DELETE CASCADE: deleted with the account), and for a reply the top-level
  comment it's under (ON DELETE CASCADE). Closed to clients: RLS on, no
  grants; only the API reads and writes it (app/comments.py).
- activity_posts.comments_off: its author turned comments off.
- notifications: the comment_reply and mention kinds, and comment_id (ON
  DELETE CASCADE) so a deleted comment takes its notifications with it.
- notification_preferences: comment_reply and mention switches.
- profile_reports.comment_id: a report about a comment.

Revision ID: f2c8a4e6b1d9
Revises: c8d1f5a3e7b9
Create Date: 2026-11-19 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f2c8a4e6b1d9"
down_revision: Union[str, Sequence[str], None] = "c8d1f5a3e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
KINDS_BEFORE = "'new_follower', 'follow_request', 'request_approved', 'high_five', 'comment'"
KINDS_AFTER = f"{KINDS_BEFORE}, 'comment_reply', 'mention'"


def _kinds(kinds: str) -> None:
    op.execute("ALTER TABLE public.notifications DROP CONSTRAINT notifications_kind_check")
    op.execute(f"ALTER TABLE public.notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({kinds}))")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.activity_comments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES public.activity_posts (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            parent_id uuid REFERENCES public.activity_comments (id) ON DELETE CASCADE,
            body text CONSTRAINT activity_comments_body_length_check
                CHECK (body IS NULL OR length(body) BETWEEN 1 AND 500),
            created_at timestamptz NOT NULL DEFAULT now(),
            edited_at timestamptz,
            CONSTRAINT activity_comments_not_own_parent_check CHECK (parent_id IS NULL OR parent_id <> id)
        )
        """
    )
    op.execute("CREATE INDEX activity_comments_post_idx ON public.activity_comments (post_id, created_at)")
    op.execute("CREATE INDEX activity_comments_user_idx ON public.activity_comments (user_id, created_at)")
    op.execute("CREATE INDEX activity_comments_parent_idx ON public.activity_comments (parent_id)")
    op.execute("ALTER TABLE public.activity_comments ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.activity_comments FROM {CLIENTS}")

    op.execute("ALTER TABLE public.activity_posts ADD COLUMN comments_off boolean NOT NULL DEFAULT false")

    _kinds(KINDS_AFTER)
    op.execute(
        "ALTER TABLE public.notifications ADD COLUMN comment_id uuid "
        "REFERENCES public.activity_comments (id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX notifications_comment_idx ON public.notifications (comment_id)")
    op.execute("ALTER TABLE public.notification_preferences ADD COLUMN comment_reply boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE public.notification_preferences ADD COLUMN mention boolean NOT NULL DEFAULT true")

    op.execute(
        "ALTER TABLE public.profile_reports ADD COLUMN comment_id uuid "
        "REFERENCES public.activity_comments (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.profile_reports DROP COLUMN IF EXISTS comment_id")
    op.execute("ALTER TABLE public.notification_preferences DROP COLUMN IF EXISTS mention")
    op.execute("ALTER TABLE public.notification_preferences DROP COLUMN IF EXISTS comment_reply")
    op.execute("DELETE FROM public.notifications WHERE kind IN ('comment_reply', 'mention')")
    op.execute("DROP INDEX IF EXISTS public.notifications_comment_idx")
    op.execute("ALTER TABLE public.notifications DROP COLUMN IF EXISTS comment_id")
    _kinds(KINDS_BEFORE)
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS comments_off")
    op.execute("DROP TABLE IF EXISTS public.activity_comments")
