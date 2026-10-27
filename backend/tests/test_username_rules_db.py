"""Username rules in the database itself (migration 5d1c0e7a9b42), so a
direct Supabase write can't get around the API: reserved names, case-
insensitive uniqueness, no removing a username, and the sign-up trigger.

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres. Every test runs in a
transaction that is rolled back.
"""

import json
import os
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.usernames import load_reserved

DB_URL = os.getenv("LOCAL_SUPABASE_DB_URL")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture(scope="module")
def engine():
    host = urlparse(DB_URL).hostname
    if host not in LOCAL_HOSTS:
        pytest.fail(f"Refusing to run username rule tests against non-local host {host!r}")
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def sign_up(conn, metadata=None):
    """Insert an auth user as Supabase does; the triggers create the profile."""
    conn.execute(text("RESET ROLE"))
    user = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO auth.users (id, aud, role, email, raw_user_meta_data) "
            "VALUES (:id, 'authenticated', 'authenticated', :email, CAST(:meta AS jsonb))"
        ),
        {"id": user, "email": f"{user}@username-test.local", "meta": json.dumps(metadata or {})},
    )
    return user


def username_of(conn, user):
    conn.execute(text("RESET ROLE"))
    return conn.execute(text("SELECT username FROM public.profiles WHERE id = :id"), {"id": user}).scalar()


def as_user(conn, user):
    conn.execute(text("RESET ROLE"))
    conn.execute(text("SET LOCAL ROLE authenticated"))
    claims = json.dumps({"sub": str(user), "role": "authenticated"})
    conn.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": claims})


def refused(conn, statement, params, reason):
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params)
    except DBAPIError as error:
        savepoint.rollback()
        assert reason in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


SET_OWN = "UPDATE public.profiles SET username = :name WHERE id = :id"


def test_database_copy_of_reserved_list_matches_the_config_file(conn):
    names = set(conn.execute(text("SELECT name FROM public.reserved_usernames")).scalars())
    assert names == load_reserved()


def test_clients_cannot_read_or_change_the_reserved_list(conn):
    user = sign_up(conn)
    as_user(conn, user)
    assert refused(conn, "SELECT * FROM public.reserved_usernames", {}, "permission denied")
    assert refused(conn, "DELETE FROM public.reserved_usernames", {}, "permission denied")


def test_sign_up_takes_the_username_from_metadata(conn):
    user = sign_up(conn, {"display_name": "Jo", "username": " Trail_Jo "})
    assert username_of(conn, user) == "trail_jo"


@pytest.mark.parametrize("metadata", [{}, {"username": "admin"}, {"username": "no"}, {"username": "bad name!"}])
def test_sign_up_without_a_usable_username_starts_without_one(conn, metadata):
    user = sign_up(conn, metadata)
    assert username_of(conn, user) is None


def test_sign_up_with_a_taken_username_still_succeeds_without_it(conn):
    sign_up(conn, {"username": "first_come"})
    second = sign_up(conn, {"username": "First_Come"})
    assert username_of(conn, second) is None


def test_reserved_names_are_refused_on_direct_writes(conn):
    user = sign_up(conn)
    as_user(conn, user)
    for name in ("admin", "settings", "trekly"):
        assert refused(conn, SET_OWN, {"name": name, "id": user}, "username_reserved")
    conn.execute(text(SET_OWN), {"name": "fine_name", "id": user})
    assert username_of(conn, user) == "fine_name"


def test_usernames_are_unique_ignoring_case(conn):
    owner, other = sign_up(conn, {"username": "unique_one"}), sign_up(conn)
    conn.execute(text("RESET ROLE"))
    # The format check keeps stored names lowercase; the index itself is on lower(username).
    index = conn.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'profiles_username_key'")).scalar()
    assert "lower(username)" in index
    as_user(conn, other)
    assert refused(conn, SET_OWN, {"name": "unique_one", "id": other}, "profiles_username_key")
    assert username_of(conn, owner) == "unique_one"


def test_a_username_cannot_be_removed_once_set(conn):
    user = sign_up(conn, {"username": "staying_put"})
    as_user(conn, user)
    assert refused(conn, SET_OWN, {"name": None, "id": user}, "username_required")
    assert username_of(conn, user) == "staying_put"


def test_names_already_held_are_left_alone(conn):
    user = sign_up(conn)
    conn.execute(text("RESET ROLE"))
    conn.execute(text("ALTER TABLE public.profiles DISABLE TRIGGER profiles_username_rules"))
    conn.execute(text(SET_OWN), {"name": "explore", "id": user})
    conn.execute(text("ALTER TABLE public.profiles ENABLE TRIGGER profiles_username_rules"))
    # Other edits, and re-saving the same name, still work.
    as_user(conn, user)
    conn.execute(text("UPDATE public.profiles SET bio = 'hi', username = 'explore' WHERE id = :id"), {"id": user})
    assert username_of(conn, user) == "explore"


def test_choosing_a_username_does_not_touch_privacy_settings(conn):
    user = sign_up(conn)
    conn.execute(text("RESET ROLE"))
    before = conn.execute(text("SELECT * FROM public.profile_settings WHERE user_id = :id"), {"id": user}).mappings().one()
    as_user(conn, user)
    conn.execute(text(SET_OWN), {"name": "new_handle", "id": user})
    conn.execute(text("RESET ROLE"))
    after = conn.execute(text("SELECT * FROM public.profile_settings WHERE user_id = :id"), {"id": user}).mappings().one()
    assert dict(after) == dict(before)
