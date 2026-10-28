"""Avatar Storage policies, checked against the local Supabase stack.

Supabase Storage writes to storage.objects as the requesting user, so its
access rules are the RLS policies on that table. These tests act as each
user (SET ROLE authenticated + their JWT claims) and try what the Storage
API would do: upload (INSERT), overwrite (UPDATE, i.e. upsert) and delete.
Every test runs in a transaction that is rolled back.

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
        pytest.fail(f"Refusing to run storage policy tests against non-local host {host!r}")
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def users(conn):
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user in (alice, bob):
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :email)"),
            {"id": user, "email": f"{user}@policy-test.local"},
        )
    return alice, bob


def act_as(conn, user):
    """Switch the rest of the transaction to `user` (None = anon), like a Storage API request."""
    conn.execute(text("RESET ROLE"))
    if user is None:
        conn.execute(text("SET LOCAL ROLE anon"))
        claims = {"role": "anon"}
    else:
        conn.execute(text("SET LOCAL ROLE authenticated"))
        claims = {"sub": str(user), "role": "authenticated"}
    conn.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": json.dumps(claims)})


def delete(conn, name):
    """DELETE as the Storage API does it (it sets this flag to pass storage.protect_delete)."""
    conn.execute(text("SELECT set_config('storage.allow_delete_query', 'true', true)"))
    return conn.execute(text("DELETE FROM storage.objects WHERE bucket_id = 'avatars' AND name = :name"), {"name": name})


def upload(conn, name):
    conn.execute(text("INSERT INTO storage.objects (bucket_id, name) VALUES ('avatars', :name)"), {"name": name})


def rejected(conn, statement, params):
    """Run `statement` in a savepoint; True if RLS refused it."""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params)
    except DBAPIError as error:
        savepoint.rollback()
        assert "row-level security" in str(error.orig)
        return True
    savepoint.rollback()
    return False


def avatar_name(user, extension="webp"):
    return f"{user}/{uuid.uuid4()}.{extension}"


def test_bucket_is_public_small_and_processed_formats_only(conn):
    public, limit, types = conn.execute(
        text("SELECT public, file_size_limit, allowed_mime_types FROM storage.buckets WHERE id = 'avatars'")
    ).one()
    assert public is True
    assert limit == 1024 * 1024
    assert sorted(types) == ["image/jpeg", "image/webp"]


def test_user_can_upload_and_delete_own_avatar(conn, users):
    alice, _ = users
    name = avatar_name(alice)
    act_as(conn, alice)
    upload(conn, name)
    deleted = delete(conn, name)
    assert deleted.rowcount == 1


def test_user_cannot_upload_into_another_users_folder(conn, users):
    alice, bob = users
    act_as(conn, bob)
    assert rejected(conn, "INSERT INTO storage.objects (bucket_id, name) VALUES ('avatars', :name)", {"name": avatar_name(alice)})


@pytest.mark.parametrize("name", ["avatar.png", "{uuid}.png", "{uuid}.webp.exe", "nested/{uuid}.webp"])
def test_only_processed_avatar_names_are_accepted(conn, users, name):
    alice, _ = users
    act_as(conn, alice)
    full = f"{alice}/{name.format(uuid=uuid.uuid4())}"
    assert rejected(conn, "INSERT INTO storage.objects (bucket_id, name) VALUES ('avatars', :name)", {"name": full})


def test_user_cannot_overwrite_or_delete_another_users_avatar(conn, users):
    alice, bob = users
    name = avatar_name(alice)
    act_as(conn, alice)
    upload(conn, name)

    act_as(conn, bob)
    # Overwrite = upsert = UPDATE; with no UPDATE policy nothing matches.
    updated = conn.execute(
        text("UPDATE storage.objects SET metadata = '{\"hacked\": true}'::jsonb WHERE bucket_id = 'avatars' AND name = :name"),
        {"name": name},
    )
    deleted = delete(conn, name)
    assert updated.rowcount == 0 and deleted.rowcount == 0
    # Re-uploading the same path to replace it fails too.
    assert rejected(conn, "INSERT INTO storage.objects (bucket_id, name) VALUES ('avatars', :name) ON CONFLICT DO NOTHING", {"name": name})

    conn.execute(text("RESET ROLE"))
    metadata = conn.execute(text("SELECT metadata FROM storage.objects WHERE name = :name"), {"name": name}).scalar_one()
    assert not (metadata or {}).get("hacked")


def exists(conn, name):
    conn.execute(text("RESET ROLE"))
    return conn.execute(
        text("SELECT count(*) FROM storage.objects WHERE bucket_id = 'avatars' AND name = :name"), {"name": name}
    ).scalar_one() == 1


def test_changing_photo_leaves_only_the_new_file(conn, users):
    """The client's replace (lib/avatarChange.ts): upload the new photo, then delete the old one."""
    alice, _ = users
    old, new = avatar_name(alice), avatar_name(alice, "jpg")
    act_as(conn, alice)
    upload(conn, old)
    upload(conn, new)
    assert delete(conn, old).rowcount == 1
    assert not exists(conn, old) and exists(conn, new)


def test_removing_photo_really_deletes_it_and_only_the_owner_can(conn, users):
    """A refused delete matches no rows, which Storage reports as an empty list; the client treats that as a failure."""
    alice, bob = users
    name = avatar_name(alice)
    act_as(conn, alice)
    upload(conn, name)

    act_as(conn, bob)
    assert delete(conn, name).rowcount == 0
    assert exists(conn, name)

    act_as(conn, alice)
    assert delete(conn, name).rowcount == 1
    assert not exists(conn, name)


def test_owner_cannot_overwrite_in_place_either(conn, users):
    """Every change is a new file, which is what makes the URL cache-safe."""
    alice, _ = users
    name = avatar_name(alice)
    act_as(conn, alice)
    upload(conn, name)
    updated = conn.execute(
        text("UPDATE storage.objects SET metadata = '{}'::jsonb WHERE bucket_id = 'avatars' AND name = :name"), {"name": name}
    )
    assert updated.rowcount == 0


def test_folders_cannot_be_listed_by_others(conn, users):
    alice, bob = users
    act_as(conn, alice)
    upload(conn, avatar_name(alice))
    for viewer in (bob, None):
        act_as(conn, viewer)
        listed = conn.execute(
            text("SELECT count(*) FROM storage.objects WHERE bucket_id = 'avatars' AND name LIKE :prefix"),
            {"prefix": f"{alice}/%"},
        ).scalar_one()
        assert listed == 0
