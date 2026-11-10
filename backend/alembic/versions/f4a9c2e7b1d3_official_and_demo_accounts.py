"""official and demo accounts: account labels, announcement posts

- account_labels: 'official' (the @trekly account, at most one) or 'demo' (a
  clearly labeled demo hiker). Written only by the backend's scripts; clients
  get no access at all. Deleting the auth user deletes the label (CASCADE).
- The username trigger lets the official account hold a reserved name
  ("trekly"); everyone else is still refused one.
- activity_posts gains the 'announcement' kind: a short text (1-500 chars),
  an optional linked trail (SET NULL if the trail goes) and an optional photo
  path in the public trail-photos bucket. Only the official account's
  announcements are ever readable (API and RLS), and only the API writes.
  Clients still read only id, user_id, kind, milestone and rank_level.
- admin_audit_log may record official_post / delete_official_post.

Revision ID: f4a9c2e7b1d3
Revises: c6e1a4d8b2f5
Create Date: 2026-11-10 12:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f4a9c2e7b1d3"
down_revision: Union[str, Sequence[str], None] = "c6e1a4d8b2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
ACTIONS_BEFORE = (
    "hide_profile", "unhide_profile", "clear_username", "ban_user", "unban_user",
    "send_password_reset", "resolve_report", "reopen_report", "hide_post", "unhide_post",
)
ACTIONS_AFTER = (*ACTIONS_BEFORE, "official_post", "delete_official_post")

SHAPE_BEFORE = """
    (kind = 'hike' AND hike_log_id IS NOT NULL AND milestone IS NULL AND rank_level IS NULL)
    OR (kind = 'milestone' AND milestone IS NOT NULL AND rank_level IS NULL)
    OR (kind = 'rank' AND rank_level IS NOT NULL AND milestone IS NULL)
"""
SHAPE_AFTER = SHAPE_BEFORE + """
    OR (kind = 'announcement' AND body IS NOT NULL AND hike_log_id IS NULL AND milestone IS NULL
        AND rank_level IS NULL)
"""


def _audit_check(actions: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{a}'" for a in actions)
    op.execute("ALTER TABLE public.admin_audit_log DROP CONSTRAINT admin_audit_log_action_check")
    op.execute(
        "ALTER TABLE public.admin_audit_log ADD CONSTRAINT admin_audit_log_action_check "
        f"CHECK (action IN ({listed}))"
    )


def _post_checks(kinds: str, shape: str) -> None:
    op.execute("ALTER TABLE public.activity_posts DROP CONSTRAINT activity_posts_kind_check")
    op.execute("ALTER TABLE public.activity_posts DROP CONSTRAINT activity_posts_shape_check")
    op.execute(f"ALTER TABLE public.activity_posts ADD CONSTRAINT activity_posts_kind_check CHECK (kind IN ({kinds}))")
    op.execute(f"ALTER TABLE public.activity_posts ADD CONSTRAINT activity_posts_shape_check CHECK ({shape})")


def _visible_function(announcements: bool) -> str:
    """private.activity_post_visible as in a8c3f1d5e7b2, plus (after) an
    announcement shows only when its author is the official account."""
    if announcements:
        kind_rule = (
            "CASE a.kind WHEN 'rank' THEN s.show_rank WHEN 'announcement' THEN EXISTS ("
            "SELECT 1 FROM public.account_labels l WHERE l.user_id = a.user_id AND l.label = 'official'"
            ") ELSE s.show_journal END"
        )
    else:
        kind_rule = "CASE a.kind WHEN 'rank' THEN s.show_rank ELSE s.show_journal END"
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
                  AND p.username IS NOT NULL
                  AND NOT s.is_private
                  AND s.share_activity
                  AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = a.user_id)
                  AND {kind_rule}
                  AND NOT (a.reveals_date AND s.hide_hike_dates)
                  AND (a.kind <> 'hike' OR h.hiked_on IS NULL OR h.hiked_on <= current_date + 1)
            )
        $$
        """


def _username_function(official_exempt: bool) -> str:
    """public.enforce_username_rules as in 5d1c0e7a9b42, plus (after) the
    official account may keep a reserved name."""
    exempt = (
        "AND NOT EXISTS (SELECT 1 FROM public.account_labels l WHERE l.user_id = NEW.id AND l.label = 'official')"
        if official_exempt else ""
    )
    return f"""
        CREATE OR REPLACE FUNCTION public.enforce_username_rules()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NEW.username IS NOT DISTINCT FROM OLD.username THEN
                    RETURN NEW;
                END IF;
                -- Clients can't remove theirs; the API refuses it too, and admins
                -- (no client claims) still can, e.g. to clear an offensive name.
                IF NEW.username IS NULL
                   AND (NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
                       IN ('anon', 'authenticated') THEN
                    RAISE EXCEPTION 'username_required: a username can be changed, not removed'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
            IF NEW.username IS NOT NULL
               AND EXISTS (SELECT 1 FROM public.reserved_usernames r WHERE r.name = lower(NEW.username))
               {exempt} THEN
                RAISE EXCEPTION 'username_reserved: % is reserved', NEW.username
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.account_labels (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            label text NOT NULL CONSTRAINT account_labels_label_check CHECK (label IN ('official', 'demo')),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE public.account_labels ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.account_labels FROM PUBLIC, {CLIENTS}")
    op.execute(
        "CREATE UNIQUE INDEX account_labels_one_official ON public.account_labels (label) WHERE label = 'official'"
    )

    op.execute(_username_function(official_exempt=True))

    op.execute("ALTER TABLE public.activity_posts ADD COLUMN body text")
    op.execute(
        "ALTER TABLE public.activity_posts ADD COLUMN trail_id uuid REFERENCES public.trails (id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN photo_path text")
    op.execute(
        "ALTER TABLE public.activity_posts ADD CONSTRAINT activity_posts_body_length_check "
        "CHECK (body IS NULL OR length(body) BETWEEN 1 AND 500)"
    )
    _post_checks("'hike', 'milestone', 'rank', 'announcement'", SHAPE_AFTER)
    op.execute(_visible_function(announcements=True))
    _audit_check(ACTIONS_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM public.admin_audit_log WHERE action IN ('official_post', 'delete_official_post')")
    _audit_check(ACTIONS_BEFORE)
    op.execute(_visible_function(announcements=False))
    op.execute("DELETE FROM public.activity_posts WHERE kind = 'announcement'")
    _post_checks("'hike', 'milestone', 'rank'", SHAPE_BEFORE)
    op.execute("ALTER TABLE public.activity_posts DROP CONSTRAINT IF EXISTS activity_posts_body_length_check")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS photo_path")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS trail_id")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS body")
    op.execute(_username_function(official_exempt=False))
    op.execute("DROP TABLE IF EXISTS public.account_labels")
