"""Hikes from before Trekly, and GPS-verified hikes

- hike_logs.hiked_on becomes nullable: a hike picked from "Which of these
  have you hiked?" has no date. The journal shows it as "Hiked before
  <join month>"; date-based milestones skip it (app/milestones.py).
- hike_logs.verified / match_score / nights: set only by the API after a GPX
  track matched the trail (verified needs a date and a score). nights is the
  track's own count for an overnight trip; null means the trail's typical
  nights. The track itself is never stored.
- Client INSERT and UPDATE on hike_logs become column grants on the columns
  they already had. Supabase had granted them table-wide, which would cover
  the new columns and let a browser mark its own hikes verified. RLS still
  limits them to their own rows.
- hike_logs_unverify_on_date_change: a verified hike whose date changes
  without a new match score (only the API writes one) stops being verified,
  however it was changed.
- hike_logs_user_hiked_idx serves the "hikes dated today" fair-use count.
- /welcome gains two steps after "regions": "hiked" (Which of these have you
  hiked?) and "pack" (What's in your pack?), so profile_preferences'
  onboarding_step check (migration 6d1a8f3b2c57) allows them.

Revision ID: b4e7a2c9d1f3
Revises: 6d1a8f3b2c57
Create Date: 2026-11-03 21:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b4e7a2c9d1f3"
down_revision: Union[str, Sequence[str], None] = "6d1a8f3b2c57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# What authenticated could write before, now as explicit column grants.
CLIENT_COLUMNS = "id, user_id, trail_id, hiked_on, note, photo_path, created_at, updated_at"

STEPS_BEFORE = "'name', 'photo', 'home', 'style', 'experience', 'interests', 'regions', 'units', 'privacy', 'done'"
STEPS_AFTER = (
    "'name', 'photo', 'home', 'style', 'experience', 'interests', 'regions', 'hiked', 'pack', 'units', 'privacy', 'done'"
)


def _step_check(steps: str) -> None:
    op.execute("ALTER TABLE public.profile_preferences DROP CONSTRAINT profile_preferences_onboarding_step_check")
    op.execute(
        "ALTER TABLE public.profile_preferences ADD CONSTRAINT profile_preferences_onboarding_step_check "
        f"CHECK (onboarding_step IS NULL OR onboarding_step IN ({steps}))"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE public.hike_logs ALTER COLUMN hiked_on DROP NOT NULL")
    op.execute("ALTER TABLE public.hike_logs ADD COLUMN verified boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE public.hike_logs ADD COLUMN match_score numeric(4, 3)")
    op.execute("ALTER TABLE public.hike_logs ADD COLUMN nights integer")
    op.execute(
        "ALTER TABLE public.hike_logs ADD CONSTRAINT hike_logs_match_score_check "
        "CHECK (match_score IS NULL OR (match_score >= 0 AND match_score <= 1))"
    )
    op.execute(
        "ALTER TABLE public.hike_logs ADD CONSTRAINT hike_logs_nights_check "
        "CHECK (nights IS NULL OR (nights >= 0 AND nights <= 60))"
    )
    op.execute(
        "ALTER TABLE public.hike_logs ADD CONSTRAINT hike_logs_verified_check "
        "CHECK (NOT verified OR (hiked_on IS NOT NULL AND match_score IS NOT NULL))"
    )
    op.execute("CREATE INDEX hike_logs_user_hiked_idx ON public.hike_logs (user_id, hiked_on)")
    op.execute("REVOKE INSERT, UPDATE ON public.hike_logs FROM anon, authenticated")
    op.execute(f"GRANT INSERT ({CLIENT_COLUMNS}), UPDATE ({CLIENT_COLUMNS}) ON public.hike_logs TO authenticated")
    op.execute(
        """
        CREATE FUNCTION private.hike_logs_unverify_on_date_change() RETURNS trigger
        LANGUAGE plpgsql SET search_path = '' AS $$
        BEGIN
            IF OLD.verified AND NEW.hiked_on IS DISTINCT FROM OLD.hiked_on
               AND NEW.match_score IS NOT DISTINCT FROM OLD.match_score THEN
                NEW.verified := false;
                NEW.match_score := NULL;
                NEW.nights := NULL;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION private.hike_logs_unverify_on_date_change() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER hike_logs_unverify_on_date_change BEFORE UPDATE ON public.hike_logs "
        "FOR EACH ROW EXECUTE FUNCTION private.hike_logs_unverify_on_date_change()"
    )
    _step_check(STEPS_AFTER)


def downgrade() -> None:
    # Anyone paused on a new step resumes at the one that followed it before.
    op.execute("UPDATE public.profile_preferences SET onboarding_step = 'units' WHERE onboarding_step IN ('hiked', 'pack')")
    _step_check(STEPS_BEFORE)
    op.execute("DROP TRIGGER IF EXISTS hike_logs_unverify_on_date_change ON public.hike_logs")
    op.execute("DROP FUNCTION IF EXISTS private.hike_logs_unverify_on_date_change()")
    op.execute("REVOKE INSERT, UPDATE ON public.hike_logs FROM authenticated")
    op.execute("GRANT INSERT, UPDATE ON public.hike_logs TO authenticated")
    op.execute("DROP INDEX IF EXISTS public.hike_logs_user_hiked_idx")
    for name in ("verified", "nights", "match_score"):
        op.execute(f"ALTER TABLE public.hike_logs DROP CONSTRAINT IF EXISTS hike_logs_{name}_check")
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS nights")
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS match_score")
    op.execute("ALTER TABLE public.hike_logs DROP COLUMN IF EXISTS verified")
    # Undated hikes need some date again; the day they were logged is the
    # closest the data has (nothing is deleted).
    op.execute("UPDATE public.hike_logs SET hiked_on = created_at::date WHERE hiked_on IS NULL")
    op.execute("ALTER TABLE public.hike_logs ALTER COLUMN hiked_on SET NOT NULL")
