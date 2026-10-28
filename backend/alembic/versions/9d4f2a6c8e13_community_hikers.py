"""community features: "Hiked by" on trail pages, opt-in

A new privacy setting, profile_settings.show_in_community, off for
everyone (existing users included). Someone appears in a trail's "Hiked by"
list, with their trip note, only while all of these hold: they have a
username, aren't hidden by an admin, their profile isn't private, their
Trail Journal is shown, and they've opted in. The API applies the same rule
(app/privacy.py, app/routers/trail_hikers.py).

- private.section_visible gains a 'community' section: show_journal AND
  show_in_community, on top of the existing public-profile checks.
- hike_logs' public read policy moves from 'journal' to 'community'.
  Before, a client could list everyone with a public journal who logged a
  trail (`hike_logs?trail_id=eq.…`), which is "Hiked by" without the
  opt-in. Nothing in the app reads other people's hike_logs directly (the
  API does, as postgres), and journal photos still follow the journal
  switch alone (private.photo_visible is unchanged), so a community note's
  photo is visible exactly when it already is on the public journal.
- Owners can change the new column through RLS like the others.

Revision ID: 9d4f2a6c8e13
Revises: 6e2f4b8d1a37
Create Date: 2026-10-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9d4f2a6c8e13"
down_revision: Union[str, Sequence[str], None] = "6e2f4b8d1a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def _section_visible(extra_case: str) -> str:
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
                  AND NOT s.is_private
                  AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = p.id)
                  AND CASE section
                        WHEN 'profile' THEN true
                        WHEN 'journal' THEN s.show_journal
                        WHEN 'rank' THEN s.show_rank
                        WHEN 'gear' THEN s.show_gear
                        WHEN 'saved_trails' THEN s.show_saved_trails
                        WHEN 'trip_plans' THEN s.show_trip_plans{extra_case}
                        ELSE false
                      END
            )
        $$
        """


def _hike_logs_policy(section: str) -> None:
    op.execute('DROP POLICY IF EXISTS "hike_logs_select_public" ON public.hike_logs')
    op.execute(
        'CREATE POLICY "hike_logs_select_public" ON public.hike_logs '
        f"FOR SELECT TO {CLIENTS} USING (private.section_visible(user_id, '{section}'))"
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.profile_settings "
        "ADD COLUMN show_in_community boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT UPDATE (show_in_community) ON public.profile_settings TO authenticated")
    # CREATE OR REPLACE keeps the existing grants on the function.
    op.execute(_section_visible("\n                        WHEN 'community' THEN s.show_journal AND s.show_in_community"))
    _hike_logs_policy("community")


def downgrade() -> None:
    _hike_logs_policy("journal")
    op.execute(_section_visible(""))
    op.execute("REVOKE UPDATE (show_in_community) ON public.profile_settings FROM authenticated")
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN show_in_community")
