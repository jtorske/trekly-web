"""mandatory usernames: reserved names, case-insensitive uniqueness, sign-up username

Every account now chooses a username (the app asks before anything else).
The database enforces the rules for every writer, including direct Supabase
access, which may update its own profile row:

- public.reserved_usernames: a copy of backend/config/reserved_usernames.txt
  (kept in step by scripts/sync_reserved_usernames.py). No client access.
- A trigger on profiles refuses a reserved username when one is set or
  changed (names already held are left alone), and refuses a client
  clearing their username once there is one.
- profiles_username_key becomes a unique index on lower(username).
- The new-user trigger takes `username` from the sign-up metadata when it's
  valid, not reserved and free; otherwise the profile starts without one
  and the app asks for it. It never fails a sign-up over the username.

Privacy settings are not touched.

Revision ID: 5d1c0e7a9b42
Revises: aa84e0d9e26b
Create Date: 2026-10-27 18:00:00.000000

"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5d1c0e7a9b42"
down_revision: Union[str, Sequence[str], None] = "aa84e0d9e26b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESERVED_FILE = Path(__file__).resolve().parents[2] / "config" / "reserved_usernames.txt"


def _reserved() -> list[str]:
    names = set()
    for line in RESERVED_FILE.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip().lower()
        if name:
            names.add(name)
    return sorted(names)


def _new_user_function(username_sql: str) -> str:
    # Same shape as e7f8a9b0c1d2: SECURITY DEFINER, empty search_path,
    # idempotent on the profile row.
    return f"""
        CREATE OR REPLACE FUNCTION public.handle_new_user_profile()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
            display text := NULLIF(left(btrim(COALESCE(
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'display_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'full_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'name'), '')
            )), 60), '');
            handle text := {username_sql};
        BEGIN
            IF handle IS NOT NULL AND (
                handle !~ '^[a-z0-9_]{{3,30}}$'
                OR EXISTS (SELECT 1 FROM public.reserved_usernames r WHERE r.name = handle)
                OR EXISTS (SELECT 1 FROM public.profiles p WHERE lower(p.username) = handle)
            ) THEN
                handle := NULL;
            END IF;
            BEGIN
                INSERT INTO public.profiles (id, display_name, username)
                VALUES (NEW.id, display, handle)
                ON CONFLICT (id) DO NOTHING;
            EXCEPTION WHEN unique_violation THEN
                -- Someone took the name a moment ago: start without one.
                INSERT INTO public.profiles (id, display_name)
                VALUES (NEW.id, display)
                ON CONFLICT (id) DO NOTHING;
            END;
            RETURN NEW;
        END;
        $$
        """


USERNAME_FROM_SIGNUP = "lower(NULLIF(btrim(NEW.raw_user_meta_data ->> 'username'), ''))"


def upgrade() -> None:
    op.execute("CREATE TABLE public.reserved_usernames (name text PRIMARY KEY CHECK (name = lower(name)))")
    op.execute("ALTER TABLE public.reserved_usernames ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.reserved_usernames FROM PUBLIC, anon, authenticated")
    op.get_bind().execute(
        sa.text("INSERT INTO public.reserved_usernames (name) VALUES (:name)"),
        [{"name": name} for name in _reserved()],
    )

    op.execute(
        """
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
               AND EXISTS (SELECT 1 FROM public.reserved_usernames r WHERE r.name = lower(NEW.username)) THEN
                RAISE EXCEPTION 'username_reserved: % is reserved', NEW.username
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.enforce_username_rules() FROM PUBLIC, anon, authenticated")
    op.execute(
        "CREATE TRIGGER profiles_username_rules BEFORE INSERT OR UPDATE OF username ON public.profiles "
        "FOR EACH ROW EXECUTE FUNCTION public.enforce_username_rules()"
    )

    op.execute("DROP INDEX public.profiles_username_key")
    op.execute("CREATE UNIQUE INDEX profiles_username_key ON public.profiles (lower(username))")

    op.execute(_new_user_function(USERNAME_FROM_SIGNUP))
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_profile() FROM PUBLIC, anon, authenticated")


def downgrade() -> None:
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
            VALUES (NEW.id, NULLIF(left(btrim(COALESCE(
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'display_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'full_name'), ''),
                NULLIF(btrim(NEW.raw_user_meta_data ->> 'name'), '')
            )), 60), ''))
            ON CONFLICT (id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.handle_new_user_profile() FROM PUBLIC, anon, authenticated")
    op.execute("DROP INDEX public.profiles_username_key")
    op.execute("CREATE UNIQUE INDEX profiles_username_key ON public.profiles (username)")
    op.execute("DROP TRIGGER IF EXISTS profiles_username_rules ON public.profiles")
    op.execute("DROP FUNCTION IF EXISTS public.enforce_username_rules()")
    op.execute("DROP TABLE IF EXISTS public.reserved_usernames")
