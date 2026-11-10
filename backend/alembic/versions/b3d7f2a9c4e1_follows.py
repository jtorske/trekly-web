"""follows: follow and follow requests, follower-aware section visibility

- follows: one row per (follower, followee). 'accepted' follows a public
  profile at once; a private profile gets a 'pending' request until its
  owner approves it (or the row is deleted: declined, cancelled, removed).
  Only the API writes it. Clients may read only the rows they're part of,
  so a hidden followers list can't be read around the API.
- profile_settings.hide_follow_lists ("Hide my followers and following
  lists"): counts still show; the lists open only for the owner.
- private.is_approved_follower(owner): the signed-in user follows `owner`
  with an approved follow.
- private.section_visible: an approved follower of a private profile sees
  the sections its owner has switched on, as a visitor sees a public
  profile's. Community features ("Hiked by") stay public-only, and the
  Activity feed's rule (private.activity_post_visible) is unchanged.

Revision ID: b3d7f2a9c4e1
Revises: d2b6e8f4a1c9
Create Date: 2026-11-09 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b3d7f2a9c4e1"
down_revision: Union[str, Sequence[str], None] = "d2b6e8f4a1c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def _section_visible(opened: str, community_open: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION private.section_visible(owner uuid, section text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM public.profiles p
                JOIN public.profile_settings s ON s.user_id = p.id
                WHERE p.id = owner
                  AND p.username IS NOT NULL
                  AND {opened}
                  AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = p.id)
                  AND CASE section
                        WHEN 'profile' THEN true
                        WHEN 'journal' THEN s.show_journal
                        WHEN 'rank' THEN s.show_rank
                        WHEN 'gear' THEN s.show_gear
                        WHEN 'saved_trails' THEN s.show_saved_trails
                        WHEN 'trip_plans' THEN s.show_trip_plans
                        WHEN 'community' THEN {community_open} AND s.show_journal AND s.show_in_community
                        ELSE false
                      END
            )
        $$
        """


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.profile_settings ADD COLUMN hide_follow_lists boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT UPDATE (hide_follow_lists) ON public.profile_settings TO authenticated")

    op.execute(
        """
        CREATE TABLE public.follows (
            follower_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            followee_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            status text NOT NULL CONSTRAINT follows_status_check CHECK (status IN ('pending', 'accepted')),
            created_at timestamptz NOT NULL DEFAULT now(),
            accepted_at timestamptz,
            CONSTRAINT follows_pkey PRIMARY KEY (follower_id, followee_id),
            CONSTRAINT follows_not_self_check CHECK (follower_id <> followee_id)
        )
        """
    )
    op.execute("CREATE INDEX follows_followee_idx ON public.follows (followee_id, status)")
    op.execute("CREATE INDEX follows_follower_idx ON public.follows (follower_id, status)")

    op.execute("ALTER TABLE public.follows ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.follows FROM {CLIENTS}")
    op.execute("GRANT SELECT (follower_id, followee_id, status) ON public.follows TO authenticated")
    op.execute(
        'CREATE POLICY "follows_select_own" ON public.follows FOR SELECT TO authenticated '
        "USING (follower_id = (SELECT auth.uid()) OR followee_id = (SELECT auth.uid()))"
    )

    op.execute(
        """
        CREATE FUNCTION private.is_approved_follower(owner uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.follows f
                WHERE f.follower_id = (SELECT auth.uid())
                  AND f.followee_id = owner
                  AND f.status = 'accepted'
            )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION private.is_approved_follower(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION private.is_approved_follower(uuid) TO {CLIENTS}")
    # CREATE OR REPLACE keeps the existing grants on the function.
    op.execute(_section_visible("(NOT s.is_private OR private.is_approved_follower(p.id))", "NOT s.is_private"))


def downgrade() -> None:
    op.execute(_section_visible("NOT s.is_private", "true"))
    op.execute("DROP FUNCTION IF EXISTS private.is_approved_follower(uuid)")
    op.execute("DROP TABLE IF EXISTS public.follows")
    op.execute("REVOKE UPDATE (hide_follow_lists) ON public.profile_settings FROM authenticated")
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS hide_follow_lists")
