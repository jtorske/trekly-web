"""public profiles with per-section privacy, moderation and reports

Profiles become viewable at /u/{username}, but only the sections the owner
has made public. The rules live here, in row-level security, so they hold
for direct Supabase access as well as for the API (which checks the same
settings itself; see app/routers/public_profiles.py).

- profile_settings: one row per user. New users get the public defaults
  (profile, journal, rank, gear and saved trails public; trip plans
  private; dates shown; no search indexing). Users who existed before this
  migration are backfilled fully private, with a one-time notice.
- profile_moderation: admin-hidden profiles. No client access at all, so an
  owner can't unhide themselves.
- profile_reports: "Report profile" submissions, kept for rate limiting.
  No client access.
- private.section_visible(owner, section): the single visibility rule. A
  section is visible to others when the owner has a username, isn't hidden
  by an admin, isn't private and has that section switched on. Missing
  settings count as private. Lives in the unexposed `private` schema so
  PostgREST doesn't publish it as an RPC.
- New SELECT policies for anon and authenticated on profiles, hike_logs,
  user_gear_items, gear_setups, gear_setup_items, saved_trails and
  trip_plans, all through section_visible. Owner-only policies stay as they
  were; policies are permissive, so either one grants a row.
- Column grants: clients can only ever read the columns a public profile
  shows. Hike dates and timestamps, gear notes, plan notes, party size and
  home region are never readable through the REST API, by anyone (the app
  reads its own data through the API, as postgres). Hike dates are
  hideable, so they can't be exposed per row; the API applies that setting.
- Storage: gear and journal photos become readable (signed URLs) when the
  owning section is public and a row of that section references the
  object. Availability alerts and trip plan nights stay owner-only.
- gear-photos now only takes processed images, like avatars and
  hike-photos: 1 MB, WebP/JPEG, `{uid}/{uuid}.webp|jpg`. The client
  re-encodes through a canvas, which strips EXIF and GPS.

Revision ID: 214aa07bf743
Revises: c4e1a9d27b30
Create Date: 2026-10-26 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "214aa07bf743"
down_revision: Union[str, Sequence[str], None] = "c4e1a9d27b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
OWN_FOLDER = "(storage.foldername(name))[1] = (select auth.uid())::text"
PHOTO_NAME = r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.(webp|jpg)$"

# Columns a client may read; everything else is API-only.
PUBLIC_COLUMNS = {
    "profiles": "id, username, display_name, bio, avatar_path",
    "hike_logs": "id, user_id, trail_id, note, photo_path",
    "user_gear_items": (
        "id, user_id, product_id, variant_id, category_id, custom_name, custom_brand, "
        "custom_model, quantity, weight_override_g, weight_override_unit, "
        "capacity_override_ml, custom_specs, condition, image_path"
    ),
    "trip_plans": "id, user_id, trail_id, title, start_date, nights",
}
# Column lists for restoring the table-wide grants on downgrade.
OWNER_SELECT_BEFORE = {
    "profiles": "authenticated",
    "hike_logs": "authenticated",
    "user_gear_items": "authenticated",
    "trip_plans": "authenticated",
}

# (table, owner column, section)
PUBLIC_READ = [
    ("profiles", "id", "profile"),
    ("hike_logs", "user_id", "journal"),
    ("user_gear_items", "user_id", "gear"),
    ("gear_setups", "user_id", "gear"),
    ("saved_trails", "user_id", "saved_trails"),
    ("trip_plans", "user_id", "trip_plans"),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.profile_settings (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            is_private boolean NOT NULL DEFAULT false,
            show_journal boolean NOT NULL DEFAULT true,
            show_rank boolean NOT NULL DEFAULT true,
            show_gear boolean NOT NULL DEFAULT true,
            show_saved_trails boolean NOT NULL DEFAULT true,
            show_trip_plans boolean NOT NULL DEFAULT false,
            hide_hike_dates boolean NOT NULL DEFAULT false,
            allow_search_indexing boolean NOT NULL DEFAULT false,
            -- The "profiles can be public now" banner, for users from before this.
            public_notice_pending boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Everyone who already has an account: private, every section off.
    op.execute(
        "INSERT INTO public.profile_settings (user_id, is_private, show_journal, show_rank, show_gear, "
        "show_saved_trails, show_trip_plans, public_notice_pending) "
        "SELECT id, true, false, false, false, false, false, true FROM auth.users "
        "ON CONFLICT (user_id) DO NOTHING"
    )
    # New users get the column defaults. Same shape as handle_new_user_profile.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.handle_new_user_settings()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
            INSERT INTO public.profile_settings (user_id) VALUES (NEW.id)
            ON CONFLICT (user_id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_settings() FROM PUBLIC, anon, authenticated")
    op.execute(
        "CREATE TRIGGER on_auth_user_created_settings AFTER INSERT ON auth.users "
        "FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_settings()"
    )

    op.execute(
        """
        CREATE TABLE public.profile_moderation (
            user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            hidden_at timestamptz NOT NULL DEFAULT now(),
            hidden_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
            reason text CHECK (reason IS NULL OR length(reason) <= 500)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.profile_reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            reporter_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            profile_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 40),
            details text CHECK (details IS NULL OR length(details) <= 1000),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX profile_reports_reporter_created_idx ON public.profile_reports (reporter_id, created_at DESC)")

    for table in ("profile_settings", "profile_moderation", "profile_reports"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM {CLIENTS}")
    # Owners read and change their own settings; rows come only from the trigger.
    own = "user_id = (select auth.uid())"
    op.execute(f'CREATE POLICY "profile_settings_select_own" ON public.profile_settings FOR SELECT TO authenticated USING ({own})')
    op.execute(
        f'CREATE POLICY "profile_settings_update_own" ON public.profile_settings '
        f"FOR UPDATE TO authenticated USING ({own}) WITH CHECK ({own})"
    )
    op.execute("GRANT SELECT ON public.profile_settings TO authenticated")
    op.execute(
        "GRANT UPDATE (is_private, show_journal, show_rank, show_gear, show_saved_trails, show_trip_plans, "
        "hide_hike_dates, allow_search_indexing, public_notice_pending) ON public.profile_settings TO authenticated"
    )

    # ---------------------------------------------------------------- the rule
    op.execute("CREATE SCHEMA IF NOT EXISTS private")
    op.execute("REVOKE ALL ON SCHEMA private FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA private TO {CLIENTS}")
    # SECURITY DEFINER so it can read settings and moderation, which clients
    # can't; empty search_path so it can't be hijacked.
    op.execute(
        """
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
                        WHEN 'trip_plans' THEN s.show_trip_plans
                        ELSE false
                      END
            )
        $$
        """
    )
    # A gear or journal photo is visible when its section is public and a
    # row of that section, owned by the folder's user, points at it (so
    # nobody can publish someone else's photo by referencing its path).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION private.photo_visible(bucket text, object_name text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT CASE bucket
                WHEN 'gear-photos' THEN EXISTS (
                    SELECT 1 FROM public.user_gear_items g
                    WHERE g.image_path = object_name
                      AND g.user_id::text = split_part(object_name, '/', 1)
                      AND private.section_visible(g.user_id, 'gear'))
                WHEN 'hike-photos' THEN EXISTS (
                    SELECT 1 FROM public.hike_logs h
                    WHERE h.photo_path = object_name
                      AND h.user_id::text = split_part(object_name, '/', 1)
                      AND private.section_visible(h.user_id, 'journal'))
                ELSE false
            END
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION private.setup_visible(setup uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.gear_setups g
                WHERE g.id = setup AND private.section_visible(g.user_id, 'gear'))
        $$
        """
    )
    for function in ("section_visible(uuid, text)", "photo_visible(text, text)", "setup_visible(uuid)"):
        op.execute(f"REVOKE ALL ON FUNCTION private.{function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION private.{function} TO {CLIENTS}")
    op.execute("CREATE INDEX IF NOT EXISTS user_gear_items_image_path_idx ON public.user_gear_items (image_path) WHERE image_path IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS hike_logs_photo_path_idx ON public.hike_logs (photo_path) WHERE photo_path IS NOT NULL")

    # ------------------------------------------------------- public policies
    for table, owner, section in PUBLIC_READ:
        op.execute(
            f'CREATE POLICY "{table}_select_public" ON public.{table} '
            f"FOR SELECT TO {CLIENTS} USING (private.section_visible({owner}, '{section}'))"
        )
    op.execute(
        'CREATE POLICY "gear_setup_items_select_public" ON public.gear_setup_items '
        f"FOR SELECT TO {CLIENTS} USING (private.setup_visible(setup_id))"
    )

    # Table-wide SELECT becomes a column list; anon gets the same list.
    for table, columns in PUBLIC_COLUMNS.items():
        op.execute(f"REVOKE SELECT ON public.{table} FROM {CLIENTS}")
        op.execute(f"GRANT SELECT ({columns}) ON public.{table} TO {CLIENTS}")
    # profiles: anon also held Supabase's default write grants (RLS stopped
    # them, but they don't belong there).
    op.execute("REVOKE INSERT, UPDATE, DELETE ON public.profiles FROM anon")
    for table in ("gear_setups", "gear_setup_items", "saved_trails"):
        op.execute(f"REVOKE ALL ON public.{table} FROM anon")
        op.execute(f"GRANT SELECT ON public.{table} TO anon")

    # --------------------------------------------------------------- storage
    for bucket, policy in (("gear-photos", "gear_photos"), ("hike-photos", "hike_photos")):
        op.execute(
            f'CREATE POLICY "{policy}_select_public" ON storage.objects '
            f"FOR SELECT TO {CLIENTS} USING (bucket_id = '{bucket}' AND private.photo_visible(bucket_id, name))"
        )
    op.execute(
        "UPDATE storage.buckets SET file_size_limit = 1048576, "
        "allowed_mime_types = ARRAY['image/webp','image/jpeg'] WHERE id = 'gear-photos'"
    )
    op.execute('DROP POLICY IF EXISTS "gear_photos_insert_own" ON storage.objects')
    op.execute(
        'CREATE POLICY "gear_photos_insert_own" ON storage.objects '
        "FOR INSERT TO authenticated WITH CHECK "
        f"(bucket_id = 'gear-photos' AND {OWN_FOLDER} AND name ~ '{PHOTO_NAME}')"
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "gear_photos_insert_own" ON storage.objects')
    op.execute(
        'CREATE POLICY "gear_photos_insert_own" ON storage.objects '
        f"FOR INSERT TO authenticated WITH CHECK (bucket_id = 'gear-photos' AND {OWN_FOLDER})"
    )
    op.execute(
        "UPDATE storage.buckets SET file_size_limit = 5242880, "
        "allowed_mime_types = ARRAY['image/jpeg','image/png','image/webp'] WHERE id = 'gear-photos'"
    )
    for policy in ("gear_photos", "hike_photos"):
        op.execute(f'DROP POLICY IF EXISTS "{policy}_select_public" ON storage.objects')

    for table in ("gear_setups", "gear_setup_items", "saved_trails"):
        op.execute(f"REVOKE SELECT ON public.{table} FROM anon")
    for table, columns in PUBLIC_COLUMNS.items():
        op.execute(f"REVOKE SELECT ({columns}) ON public.{table} FROM {CLIENTS}")
        op.execute(f"GRANT SELECT ON public.{table} TO {OWNER_SELECT_BEFORE[table]}")
    op.execute('DROP POLICY IF EXISTS "gear_setup_items_select_public" ON public.gear_setup_items')
    for table, _, _ in PUBLIC_READ:
        op.execute(f'DROP POLICY IF EXISTS "{table}_select_public" ON public.{table}')

    op.execute("DROP INDEX IF EXISTS public.hike_logs_photo_path_idx")
    op.execute("DROP INDEX IF EXISTS public.user_gear_items_image_path_idx")
    op.execute("DROP SCHEMA IF EXISTS private CASCADE")
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created_settings ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user_settings()")
    for table in ("profile_reports", "profile_moderation", "profile_settings"):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
