"""add profiles, saved trails and avatar storage

- profiles: one row per auth user, created by a trigger on auth.users
  (idempotent: ON CONFLICT DO NOTHING) and backfilled for existing users.
- saved_trails: a user's bookmarked trails (not trips or completed hikes).
- avatars: private Storage bucket; users can only touch their own folder.
- RLS on both tables: the owner can select/insert/update/delete only their
  own rows. Deleting an auth user cascades to all of their rows.

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-10-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_FOLDER = "(storage.foldername(name))[1] = (select auth.uid())::text"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.profiles (
            id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
            display_name text CHECK (display_name IS NULL OR length(display_name) BETWEEN 1 AND 60),
            username text CHECK (username IS NULL OR username ~ '^[a-z0-9_]{3,30}$'),
            bio text CHECK (bio IS NULL OR length(bio) <= 280),
            home_region text CHECK (home_region IS NULL OR length(home_region) <= 80),
            avatar_path text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX profiles_username_key ON public.profiles (username)")

    op.execute(
        """
        CREATE TABLE public.saved_trails (
            user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
            trail_id uuid NOT NULL REFERENCES public.trails (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, trail_id)
        )
        """
    )
    op.execute("CREATE INDEX saved_trails_user_created_idx ON public.saved_trails (user_id, created_at DESC)")

    # Profile row for every new auth user. SECURITY DEFINER so it can write
    # public.profiles from the auth schema's insert; empty search_path so it
    # can't be hijacked by objects in other schemas.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.handle_new_user_profile()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        BEGIN
            INSERT INTO public.profiles (id, display_name)
            VALUES (
                NEW.id,
                NULLIF(left(btrim(NEW.raw_user_meta_data ->> 'display_name'), 60), '')
            )
            ON CONFLICT (id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_profile() FROM PUBLIC, anon, authenticated")
    op.execute(
        "CREATE TRIGGER on_auth_user_created_profile AFTER INSERT ON auth.users "
        "FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_profile()"
    )
    op.execute("INSERT INTO public.profiles (id) SELECT id FROM auth.users ON CONFLICT (id) DO NOTHING")

    for table in ("profiles", "saved_trails"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    own_profile = "id = (select auth.uid())"
    own_saved = "user_id = (select auth.uid())"
    policies = [
        ("profiles", "select", f"USING ({own_profile})"),
        ("profiles", "insert", f"WITH CHECK ({own_profile})"),
        ("profiles", "update", f"USING ({own_profile}) WITH CHECK ({own_profile})"),
        ("saved_trails", "select", f"USING ({own_saved})"),
        ("saved_trails", "insert", f"WITH CHECK ({own_saved})"),
        ("saved_trails", "delete", f"USING ({own_saved})"),
    ]
    for table, action, clause in policies:
        op.execute(
            f'CREATE POLICY "{table}_{action}_own" ON public.{table} '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated")
    op.execute("GRANT SELECT, INSERT, DELETE ON public.saved_trails TO authenticated")

    op.execute(
        "INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        "VALUES ('avatars', 'avatars', false, 2097152, ARRAY['image/jpeg','image/png','image/webp']) "
        "ON CONFLICT (id) DO NOTHING"
    )
    for action, clause in (("select", "USING"), ("insert", "WITH CHECK"), ("delete", "USING")):
        op.execute(
            f'CREATE POLICY "avatars_{action}_own" ON storage.objects '
            f"FOR {action.upper()} TO authenticated {clause} "
            f"(bucket_id = 'avatars' AND {OWN_FOLDER})"
        )


def downgrade() -> None:
    for action in ("select", "insert", "delete"):
        op.execute(f'DROP POLICY IF EXISTS "avatars_{action}_own" ON storage.objects')
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created_profile ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user_profile()")
    op.execute("DROP TABLE IF EXISTS public.saved_trails")
    op.execute("DROP TABLE IF EXISTS public.profiles")
