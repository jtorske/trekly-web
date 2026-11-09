"""activity feed: posts from real activity, high fives, opt-in sharing

- profile_settings.share_activity ("Share my activity in the feed"), off for
  everyone, existing users included. Owners can change it through RLS like
  the other switches.
- activity_posts: a shared hike, a milestone or a rank. No free-form text:
  a hike post reads its trail, date, note and photo from its hike log, and
  goes when the hike does (ON DELETE CASCADE). Milestone and rank posts keep
  the hike that earned them and go with it too. One post per hike, per
  milestone and per rank. hidden_* is an admin's hide (audited).
- activity_reactions: "High five", one per user per post (the primary key).
- profile_reports.post_id: a report about one Activity post.
- admin_audit_log may record hide_post / unhide_post.

Who can read a post (the API applies the same rule, app/activity.py):
the owner has a username, isn't hidden by an admin, isn't private and
shares their activity; the post isn't hidden; a hike or milestone post
also needs the Trail Journal shown, a rank post the rank; a seasonal
milestone (reveals_date) needs dates not hidden; and a hike post's hike
can't be dated in the future (a browser can still edit its own hike_logs
row directly, so this is checked on read, not only when posting).

Clients get no writes at all (only the API posts, reacts and deletes) and
can read only the columns that say what a post is: never created_at (it
would date a hike whose owner hides dates), the hike link or the moderation
columns. Reactions show only their post_id to others, so a reaction never
reveals who gave it; the owner of a reaction can see their own.

Revision ID: a8c3f1d5e7b2
Revises: c7e3a9f1d5b2
Create Date: 2026-11-09 12:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a8c3f1d5e7b2"
down_revision: Union[str, Sequence[str], None] = "c7e3a9f1d5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
ACTIONS_BEFORE = (
    "hide_profile", "unhide_profile", "clear_username", "ban_user", "unban_user",
    "send_password_reset", "resolve_report", "reopen_report",
)
ACTIONS_AFTER = (*ACTIONS_BEFORE, "hide_post", "unhide_post")


def _audit_check(actions: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{a}'" for a in actions)
    op.execute("ALTER TABLE public.admin_audit_log DROP CONSTRAINT admin_audit_log_action_check")
    op.execute(
        "ALTER TABLE public.admin_audit_log ADD CONSTRAINT admin_audit_log_action_check "
        f"CHECK (action IN ({listed}))"
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.profile_settings ADD COLUMN share_activity boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT UPDATE (share_activity) ON public.profile_settings TO authenticated")

    op.execute(
        """
        CREATE TABLE public.activity_posts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            kind text NOT NULL CONSTRAINT activity_posts_kind_check CHECK (kind IN ('hike', 'milestone', 'rank')),
            hike_log_id uuid REFERENCES public.hike_logs (id) ON DELETE CASCADE,
            milestone text,
            rank_level smallint,
            reveals_date boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            hidden_at timestamptz,
            hidden_by uuid,
            hidden_reason text,
            CONSTRAINT activity_posts_shape_check CHECK (
                (kind = 'hike' AND hike_log_id IS NOT NULL AND milestone IS NULL AND rank_level IS NULL)
                OR (kind = 'milestone' AND milestone IS NOT NULL AND rank_level IS NULL)
                OR (kind = 'rank' AND rank_level IS NOT NULL AND milestone IS NULL)
            ),
            CONSTRAINT activity_posts_hidden_reason_length_check CHECK (
                hidden_reason IS NULL OR length(hidden_reason) <= 500
            )
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX activity_posts_hike_key ON public.activity_posts (hike_log_id) WHERE kind = 'hike'")
    op.execute(
        "CREATE UNIQUE INDEX activity_posts_milestone_key ON public.activity_posts (user_id, milestone) "
        "WHERE kind = 'milestone'"
    )
    op.execute(
        "CREATE UNIQUE INDEX activity_posts_rank_key ON public.activity_posts (user_id, rank_level) WHERE kind = 'rank'"
    )
    op.execute("CREATE INDEX activity_posts_feed_idx ON public.activity_posts (created_at, id)")
    op.execute("CREATE INDEX activity_posts_user_idx ON public.activity_posts (user_id)")

    op.execute(
        """
        CREATE TABLE public.activity_reactions (
            post_id uuid NOT NULL REFERENCES public.activity_posts (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT activity_reactions_pkey PRIMARY KEY (post_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX activity_reactions_user_idx ON public.activity_reactions (user_id)")

    op.execute(
        "ALTER TABLE public.profile_reports "
        "ADD COLUMN post_id uuid REFERENCES public.activity_posts (id) ON DELETE SET NULL"
    )
    _audit_check(ACTIONS_AFTER)

    # The read rule, in one place for both tables' policies.
    op.execute(
        """
        CREATE FUNCTION private.activity_post_visible(post uuid)
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
                  AND p.username IS NOT NULL
                  AND NOT s.is_private
                  AND s.share_activity
                  AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = a.user_id)
                  AND CASE a.kind WHEN 'rank' THEN s.show_rank ELSE s.show_journal END
                  AND NOT (a.reveals_date AND s.hide_hike_dates)
                  AND (a.kind <> 'hike' OR h.hiked_on IS NULL OR h.hiked_on <= current_date + 1)
            )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION private.activity_post_visible(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION private.activity_post_visible(uuid) TO {CLIENTS}")

    op.execute("ALTER TABLE public.activity_posts ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.activity_posts FROM {CLIENTS}")
    op.execute(f"GRANT SELECT (id, user_id, kind, milestone, rank_level) ON public.activity_posts TO {CLIENTS}")
    op.execute(
        'CREATE POLICY "activity_posts_select_own" ON public.activity_posts '
        "FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()))"
    )
    op.execute(
        'CREATE POLICY "activity_posts_select_public" ON public.activity_posts '
        f"FOR SELECT TO {CLIENTS} USING (private.activity_post_visible(id))"
    )

    op.execute("ALTER TABLE public.activity_reactions ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.activity_reactions FROM {CLIENTS}")
    op.execute(f"GRANT SELECT (post_id) ON public.activity_reactions TO {CLIENTS}")
    op.execute(
        'CREATE POLICY "activity_reactions_select_own" ON public.activity_reactions '
        "FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()))"
    )
    op.execute(
        'CREATE POLICY "activity_reactions_select_public" ON public.activity_reactions '
        f"FOR SELECT TO {CLIENTS} USING (private.activity_post_visible(post_id))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM public.admin_audit_log WHERE action IN ('hide_post', 'unhide_post')")
    _audit_check(ACTIONS_BEFORE)
    op.execute("ALTER TABLE public.profile_reports DROP COLUMN IF EXISTS post_id")
    op.execute("DROP TABLE IF EXISTS public.activity_reactions")
    op.execute("DROP TABLE IF EXISTS public.activity_posts")
    op.execute("DROP FUNCTION IF EXISTS private.activity_post_visible(uuid)")
    op.execute("REVOKE UPDATE (share_activity) ON public.profile_settings FROM authenticated")
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS share_activity")
