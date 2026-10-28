"""Trail Journal row-level security, checked against the local Supabase stack.

Acts as each user (SET ROLE authenticated + their JWT claims, as PostgREST
does) and tries direct reads and writes on public.hike_logs and the
hike-photos bucket. Every test runs in a transaction that is rolled back.

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

INSERT_LOG = "INSERT INTO public.hike_logs (user_id, trail_id, hiked_on, note, photo_path) VALUES (:user, :trail, '2026-08-14', :note, :photo)"


@pytest.fixture(scope="module")
def engine():
    host = urlparse(DB_URL).hostname
    if host not in LOCAL_HOSTS:
        pytest.fail(f"Refusing to run hike log policy tests against non-local host {host!r}")
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


@pytest.fixture
def trail(conn):
    return conn.execute(
        text(
            "INSERT INTO public.trails (id, name, region, country_code, terrain_difficulty) "
            "VALUES (gen_random_uuid(), :name, 'Policy Test Park', 'CA', 'easy') RETURNING id"
        ),
        {"name": f"Policy test trail {uuid.uuid4()}"},
    ).scalar_one()


def act_as(conn, user):
    """Switch the rest of the transaction to `user` (None = anon), like a PostgREST request."""
    conn.execute(text("RESET ROLE"))
    if user is None:
        conn.execute(text("SET LOCAL ROLE anon"))
        claims = {"role": "anon"}
    else:
        conn.execute(text("SET LOCAL ROLE authenticated"))
        claims = {"sub": str(user), "role": "authenticated"}
    conn.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"), {"claims": json.dumps(claims)})


def refused(conn, statement, params, reason="row-level security"):
    """Run `statement` in a savepoint; True if Postgres refused it for `reason`."""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params)
    except DBAPIError as error:
        savepoint.rollback()
        assert reason in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


def add_log(conn, user, trail, note="Lovely day", photo=None):
    conn.execute(text(INSERT_LOG), {"user": user, "trail": trail, "note": note, "photo": photo})


def photo_name(user):
    return f"{user}/{uuid.uuid4()}.webp"


def test_owner_can_create_read_update_and_delete_own_entry(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    # Scoped to this test's trail: other users' public journals are readable too.
    assert conn.execute(text("SELECT note FROM public.hike_logs WHERE trail_id = :trail"), {"trail": trail}).scalars().all() == ["Lovely day"]
    updated = conn.execute(text("UPDATE public.hike_logs SET note = 'Edited' WHERE trail_id = :trail"), {"trail": trail})
    assert updated.rowcount == 1
    deleted = conn.execute(text("DELETE FROM public.hike_logs WHERE trail_id = :trail"), {"trail": trail})
    assert deleted.rowcount == 1


def test_user_id_defaults_to_the_caller(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    conn.execute(text("INSERT INTO public.hike_logs (trail_id, hiked_on) VALUES (:trail, '2026-08-14')"), {"trail": trail})
    assert conn.execute(text("SELECT user_id FROM public.hike_logs WHERE trail_id = :trail"), {"trail": trail}).scalar_one() == alice


def test_entries_are_private_to_their_owner(conn, users, trail):
    """Without a public profile (these users have no username), nobody else
    sees the entries; and nobody else can ever change them. Public journals
    are covered in test_profile_privacy_policies.py."""
    alice, bob = users
    act_as(conn, alice)
    add_log(conn, alice, trail)

    act_as(conn, bob)
    assert conn.execute(text("SELECT count(*) FROM public.hike_logs WHERE user_id = :a"), {"a": alice}).scalar_one() == 0
    updated = conn.execute(text("UPDATE public.hike_logs SET note = 'Hacked'"))
    deleted = conn.execute(text("DELETE FROM public.hike_logs"))
    assert updated.rowcount == 0 and deleted.rowcount == 0

    conn.execute(text("RESET ROLE"))
    assert conn.execute(text("SELECT note FROM public.hike_logs WHERE user_id = :u"), {"u": alice}).scalar_one() == "Lovely day"


def test_user_cannot_create_an_entry_for_someone_else(conn, users, trail):
    alice, bob = users
    act_as(conn, bob)
    assert refused(conn, INSERT_LOG, {"user": alice, "trail": trail, "note": None, "photo": None})


def test_user_cannot_hand_an_entry_to_someone_else(conn, users, trail):
    alice, bob = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    assert refused(conn, "UPDATE public.hike_logs SET user_id = :bob", {"bob": bob})


def test_anon_has_no_access(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    act_as(conn, None)
    assert refused(conn, "SELECT * FROM public.hike_logs", {}, reason="permission denied")
    assert refused(conn, INSERT_LOG, {"user": alice, "trail": trail, "note": None, "photo": None}, reason="permission denied")


def test_one_entry_per_trail(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    assert refused(conn, INSERT_LOG, {"user": alice, "trail": trail, "note": None, "photo": None}, reason="hike_logs_user_trail_key")


def test_entry_photo_must_be_in_the_owners_folder(conn, users, trail):
    alice, bob = users
    act_as(conn, alice)
    assert refused(conn, INSERT_LOG, {"user": alice, "trail": trail, "note": None, "photo": photo_name(bob)}, reason="hike_logs_photo_owner_check")
    assert refused(conn, INSERT_LOG, {"user": alice, "trail": trail, "note": None, "photo": f"{alice}/photo.png"}, reason="check constraint")
    add_log(conn, alice, trail, photo=photo_name(alice))


def test_trails_with_entries_cannot_be_deleted(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    conn.execute(text("RESET ROLE"))
    assert refused(conn, "DELETE FROM public.trails WHERE id = :trail", {"trail": trail}, reason="foreign key")


def test_deleting_a_user_removes_their_entries(conn, users, trail):
    alice, _ = users
    act_as(conn, alice)
    add_log(conn, alice, trail)
    conn.execute(text("RESET ROLE"))
    conn.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": alice})
    assert conn.execute(text("SELECT count(*) FROM public.hike_logs WHERE user_id = :id"), {"id": alice}).scalar_one() == 0


# ------------------------------------------------------------- hike-photos


def upload(conn, name):
    conn.execute(text("INSERT INTO storage.objects (bucket_id, name) VALUES ('hike-photos', :name)"), {"name": name})


def delete_object(conn, name):
    """DELETE as the Storage API does it (it sets this flag to pass storage.protect_delete)."""
    conn.execute(text("SELECT set_config('storage.allow_delete_query', 'true', true)"))
    return conn.execute(text("DELETE FROM storage.objects WHERE bucket_id = 'hike-photos' AND name = :name"), {"name": name})


def test_photo_bucket_is_private_small_and_processed_formats_only(conn):
    public, limit, types = conn.execute(
        text("SELECT public, file_size_limit, allowed_mime_types FROM storage.buckets WHERE id = 'hike-photos'")
    ).one()
    assert public is False
    assert limit == 1024 * 1024
    assert sorted(types) == ["image/jpeg", "image/webp"]


def test_owner_can_upload_read_and_delete_own_photo(conn, users):
    alice, _ = users
    name = photo_name(alice)
    act_as(conn, alice)
    upload(conn, name)
    # Scoped to this photo: other users' public journal photos are readable too.
    count = "SELECT count(*) FROM storage.objects WHERE bucket_id = 'hike-photos' AND name = :name"
    assert conn.execute(text(count), {"name": name}).scalar_one() == 1
    assert delete_object(conn, name).rowcount == 1


def test_others_cannot_upload_read_or_delete_a_users_photos(conn, users):
    alice, bob = users
    name = photo_name(alice)
    act_as(conn, alice)
    upload(conn, name)

    act_as(conn, bob)
    insert = "INSERT INTO storage.objects (bucket_id, name) VALUES ('hike-photos', :name)"
    assert refused(conn, insert, {"name": photo_name(alice)})
    count = "SELECT count(*) FROM storage.objects WHERE bucket_id = 'hike-photos' AND name = :name"
    assert conn.execute(text(count), {"name": name}).scalar_one() == 0
    updated = conn.execute(
        text("UPDATE storage.objects SET metadata = '{\"hacked\": true}'::jsonb WHERE bucket_id = 'hike-photos' AND name = :name"),
        {"name": name},
    )
    assert updated.rowcount == 0
    assert delete_object(conn, name).rowcount == 0

    act_as(conn, None)
    count = "SELECT count(*) FROM storage.objects WHERE bucket_id = 'hike-photos' AND name = :name"
    assert conn.execute(text(count), {"name": name}).scalar_one() == 0


@pytest.mark.parametrize("name", ["photo.jpg", "{uuid}.png", "{uuid}.webp.exe", "nested/{uuid}.webp"])
def test_only_processed_photo_names_are_accepted(conn, users, name):
    alice, _ = users
    act_as(conn, alice)
    full = f"{alice}/{name.format(uuid=uuid.uuid4())}"
    assert refused(conn, "INSERT INTO storage.objects (bucket_id, name) VALUES ('hike-photos', :name)", {"name": full})
