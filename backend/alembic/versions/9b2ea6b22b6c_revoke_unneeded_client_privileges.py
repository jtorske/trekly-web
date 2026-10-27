"""revoke privileges the API roles never need, now and for future tables

Supabase's default grants give anon and authenticated every privilege on
public tables. Row-level security guards SELECT/INSERT/UPDATE/DELETE, but
not these:

- TRUNCATE bypasses RLS entirely (b8c9d0e1f2a3 removed it from trails only).
- TRIGGER and REFERENCES let a role attach triggers or foreign keys to a
  table. Clients never run DDL; only migrations (as postgres) do.
- MAINTAIN (Postgres 17+) allows VACUUM, ANALYZE, REINDEX, CLUSTER and
  LOCK TABLE; a client holding a table lock could stall the app.

alembic_version had no RLS at all, so the public anon key could read,
change or delete it through the REST API. Clients have no use for it:
revoke everything and enable RLS with no policies (deny by default).

Future tables: postgres's default privileges in public stop granting these
to anon and authenticated. supabase_admin's defaults can only be changed by
supabase_admin; that's skipped with a notice where we lack the right.

Revision ID: 9b2ea6b22b6c
Revises: 739722285c4e
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9b2ea6b22b6c"
down_revision: Union[str, Sequence[str], None] = "739722285c4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = "anon, authenticated"


def _unneeded() -> str:
    """MAINTAIN only exists from Postgres 17 (local and hosted are both 17)."""
    version = int(op.get_bind().exec_driver_sql("SHOW server_version_num").scalar())
    return "TRUNCATE, TRIGGER, REFERENCES" + (", MAINTAIN" if version >= 170000 else "")


def _default_privileges(action: str) -> None:
    UNNEEDED = _unneeded()
    preposition = "FROM" if action == "REVOKE" else "TO"
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        f"{action} {UNNEEDED} ON TABLES {preposition} {ROLES}"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
                {action} {UNNEEDED} ON TABLES {preposition} {ROLES};
        EXCEPTION WHEN insufficient_privilege OR undefined_object THEN
            RAISE NOTICE 'supabase_admin default privileges left unchanged';
        END
        $$
        """
    )


def upgrade() -> None:
    UNNEEDED = _unneeded()
    op.execute(f"REVOKE {UNNEEDED} ON ALL TABLES IN SCHEMA public FROM {ROLES}")
    op.execute(f"REVOKE ALL ON public.alembic_version FROM {ROLES}")
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    _default_privileges("REVOKE")


def downgrade() -> None:
    # Back to Supabase's defaults: tables that still carry the role's default
    # INSERT grant get TRUNCATE/TRIGGER/REFERENCES/MAINTAIN again. Tables whose own
    # migrations narrowed the grants (hike_logs for anon, read-only tables)
    # stay narrowed, and trails keeps TRUNCATE revoked (b8c9d0e1f2a3).
    UNNEEDED = _unneeded()
    _default_privileges("GRANT")
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
    op.execute(f"GRANT ALL ON public.alembic_version TO {ROLES}")
    op.execute(
        f"""
        DO $$
        DECLARE grant_row record;
        BEGIN
            FOR grant_row IN
                SELECT table_name, grantee FROM information_schema.role_table_grants
                WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated')
                  AND privilege_type = 'INSERT' AND table_name <> 'alembic_version'
            LOOP
                EXECUTE format('GRANT {UNNEEDED} ON public.%I TO %I', grant_row.table_name, grant_row.grantee);
            END LOOP;
        END
        $$
        """
    )
    op.execute(f"REVOKE TRUNCATE ON public.trails FROM {ROLES}")
