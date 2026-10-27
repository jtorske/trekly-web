"""API-role privileges, checked against the local Supabase stack.

anon and authenticated (the roles behind the public anon key and signed-in
users) must never hold TRUNCATE, TRIGGER, REFERENCES or MAINTAIN on public tables,
now or for tables created later, and must not reach alembic_version at all.
See migration 9b2ea6b22b6c. Each test runs in a rolled-back transaction.

Opt-in and local-only: set LOCAL_SUPABASE_DB_URL to the CLI stack's
Postgres (supabase/config.toml, [db] port 44322). Any non-local host is
refused so this can never run against the hosted project.
"""

import json
import os
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

DB_URL = os.getenv("LOCAL_SUPABASE_DB_URL")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ROLES = ("anon", "authenticated")
UNNEEDED = ("TRUNCATE", "TRIGGER", "REFERENCES", "MAINTAIN")

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture(scope="module")
def engine():
    host = urlparse(DB_URL).hostname
    if host not in LOCAL_HOSTS:
        pytest.fail(f"Refusing to run privilege tests against non-local host {host!r}")
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def act_as(conn, role):
    conn.execute(text("RESET ROLE"))
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    claims = {"role": role} if role == "anon" else {"sub": str(uuid.uuid4()), "role": role}
    conn.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": json.dumps(claims)})


def refused(conn, statement):
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement))
    except DBAPIError as error:
        savepoint.rollback()
        assert "permission denied" in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


def test_no_public_table_grants_truncate_trigger_or_references(conn):
    leftover = conn.execute(
        text(
            "SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema = 'public' AND grantee = ANY(:roles) AND privilege_type = ANY(:privileges) "
            "ORDER BY 1, 2, 3"
        ),
        {"roles": list(ROLES), "privileges": list(UNNEEDED)},
    ).all()
    assert leftover == []


def test_alembic_version_is_out_of_reach(conn):
    grants = conn.execute(
        text(
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE table_schema = 'public' AND table_name = 'alembic_version' AND grantee = ANY(:roles)"
        ),
        {"roles": list(ROLES)},
    ).scalar_one()
    assert grants == 0
    assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.alembic_version'::regclass")).scalar_one()
    for role in ROLES:
        act_as(conn, role)
        assert refused(conn, "SELECT * FROM public.alembic_version")
        assert refused(conn, "DELETE FROM public.alembic_version")


@pytest.mark.parametrize("role", ROLES)
def test_api_roles_cannot_truncate_user_tables(conn, role):
    act_as(conn, role)
    for table in ("hike_logs", "saved_trails", "profiles", "user_gear_items", "trails"):
        assert refused(conn, f"TRUNCATE public.{table}"), table


def test_no_public_table_grants_maintain(conn):
    # information_schema doesn't list MAINTAIN; ask Postgres directly.
    tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
    for role in ROLES:
        held = [t for t in tables if conn.execute(
            text("SELECT has_table_privilege(:role, :table, 'MAINTAIN')"), {"role": role, "table": f"public.{t}"}
        ).scalar_one()]
        assert held == [], role


def test_tables_created_later_do_not_get_them_either(conn):
    # Created as postgres, like every migration.
    conn.execute(text("CREATE TABLE public.privilege_probe (id int)"))
    granted = conn.execute(
        text(
            "SELECT grantee || ':' || privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema = 'public' AND table_name = 'privilege_probe' AND grantee = ANY(:roles)"
        ),
        {"roles": list(ROLES)},
    ).scalars().all()
    assert not [g for g in granted if g.split(":")[1] in UNNEEDED]
    for role in ROLES:
        assert not conn.execute(text("SELECT has_table_privilege(:role, 'public.privilege_probe', 'MAINTAIN')"), {"role": role}).scalar_one()
    # Supabase's normal data grants (guarded by RLS) are unchanged.
    assert "authenticated:SELECT" in granted


def test_data_grants_that_rls_guards_are_unchanged(conn):
    # The REST API still works for the tables clients use directly.
    for table, privilege in (("trails", "SELECT"), ("saved_trails", "INSERT"), ("hike_logs", "DELETE"), ("profiles", "UPDATE")):
        assert conn.execute(
            text("SELECT has_table_privilege('authenticated', :table, :privilege)"),
            {"table": f"public.{table}", "privilege": privilege},
        ).scalar_one(), (table, privilege)
