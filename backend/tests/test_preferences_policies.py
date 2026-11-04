"""Row-level security for profile_preferences (migration 6d1a8f3b2c57),
checked against the local Supabase stack.

Preferences are private to their owner: a guest gets no access at all,
another signed-in user sees no rows, and nobody writes through REST (the
app writes through the API). The public-profile helper views never expose
them either. Every test runs in a transaction that is rolled back.

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

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture(scope="module")
def engine():
    host = urlparse(DB_URL).hostname
    if host not in LOCAL_HOSTS:
        pytest.fail(f"Refusing to run preference policy tests against non-local host {host!r}")
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def act_as(conn, user):
    conn.execute(text("RESET ROLE"))
    if user is None:
        conn.execute(text("SET LOCAL ROLE anon"))
        claims = {"role": "anon"}
    else:
        conn.execute(text("SET LOCAL ROLE authenticated"))
        claims = {"sub": str(user), "role": "authenticated"}
    conn.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": json.dumps(claims)})


def refused(conn, statement, params=None):
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params or {})
    except DBAPIError as error:
        savepoint.rollback()
        assert "permission denied" in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


@pytest.fixture
def world(conn):
    """Alice (public profile, every question answered) and Bob."""
    conn.execute(text("RESET ROLE"))
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user in (alice, bob):
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :email)"),
            {"id": user, "email": f"{user}@policy-test.local"},
        )
    conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"), {"u": f"alice_{alice.hex[:8]}", "id": alice})
    conn.execute(
        text(
            "INSERT INTO public.profile_preferences (user_id, hiking_style, experience, interests, favourite_regions, onboarding_step) "
            "VALUES (:id, 'overnight', 'seasoned', '[\"solitude\"]', '[\"kluane\"]', 'regions')"
        ),
        {"id": alice},
    )
    return {"alice": alice, "bob": bob}


def test_rls_is_on(conn):
    assert conn.execute(
        text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.profile_preferences'::regclass")
    ).scalar_one() is True


def test_guests_have_no_access(conn, world):
    act_as(conn, None)
    assert refused(conn, "SELECT * FROM public.profile_preferences")
    assert refused(conn, "SELECT hiking_style FROM public.profile_preferences")


def test_other_users_see_no_rows(conn, world):
    act_as(conn, world["bob"])
    assert conn.execute(text("SELECT count(*) FROM public.profile_preferences")).scalar_one() == 0
    assert conn.execute(
        text("SELECT count(*) FROM public.profile_preferences WHERE user_id = :id"), {"id": world["alice"]}
    ).scalar_one() == 0


def test_the_owner_reads_only_their_own_row(conn, world):
    act_as(conn, world["alice"])
    assert conn.execute(text("SELECT user_id, hiking_style FROM public.profile_preferences")).all() == [
        (world["alice"], "overnight")
    ]


@pytest.mark.parametrize("who", ["alice", "bob", None])
def test_nobody_writes_through_rest(conn, world, who):
    act_as(conn, world[who] if who else None)
    target = world["alice"]
    assert refused(conn, "UPDATE public.profile_preferences SET hiking_style = 'day' WHERE user_id = :id", {"id": target})
    assert refused(conn, "UPDATE public.profile_preferences SET onboarding_status = 'completed' WHERE user_id = :id", {"id": target})
    assert refused(conn, "DELETE FROM public.profile_preferences WHERE user_id = :id", {"id": target})
    assert refused(conn, "INSERT INTO public.profile_preferences (user_id) VALUES (:id)", {"id": world["bob"]})
    assert refused(conn, "TRUNCATE public.profile_preferences")


def test_values_are_checked(conn, world):
    conn.execute(text("RESET ROLE"))
    for column, value in (("hiking_style", "'running'"), ("experience", "'guru'"), ("onboarding_step", "'bonus'"),
                          ("onboarding_status", "'abandoned'"), ("interests", "'{}'::jsonb")):
        savepoint = conn.begin_nested()
        with pytest.raises(DBAPIError, match="check"):
            conn.execute(text(f"UPDATE public.profile_preferences SET {column} = {value} WHERE user_id = :id"),
                         {"id": world["alice"]})
        savepoint.rollback()


def test_deleting_the_user_deletes_the_row(conn, world):
    conn.execute(text("RESET ROLE"))
    conn.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": world["alice"]})
    assert conn.execute(text("SELECT count(*) FROM public.profile_preferences")).scalar_one() == 0
