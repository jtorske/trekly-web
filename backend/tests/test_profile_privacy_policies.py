"""Public-profile row-level security, checked against the local Supabase stack.

Acts as a guest (anon) and as another signed-in user (SET ROLE + JWT
claims, as PostgREST does) and reads every table a profile draws on, plus
the photo buckets, while the owner changes their settings. See migration
214aa07bf743. Every test runs in a transaction that is rolled back.

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
VISITORS = ("guest", "bob")

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture(scope="module")
def engine():
    host = urlparse(DB_URL).hostname
    if host not in LOCAL_HOSTS:
        pytest.fail(f"Refusing to run profile privacy policy tests against non-local host {host!r}")
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def as_admin(conn):
    conn.execute(text("RESET ROLE"))


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


def refused(conn, statement, params=None, reason="permission denied"):
    """Run `statement` in a savepoint; True if Postgres refused it for `reason`."""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params or {})
    except DBAPIError as error:
        savepoint.rollback()
        assert reason in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


def rows(conn, statement, params=None):
    return conn.execute(text(statement), params or {}).all()


@pytest.fixture
def world(conn):
    """Alice (public, with something in every section), Bob, and Alice's photos."""
    as_admin(conn)
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user in (alice, bob):
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :email)"),
            {"id": user, "email": f"{user}@policy-test.local"},
        )
    conn.execute(
        text("UPDATE public.profiles SET username = :u, display_name = 'Alice', bio = 'Hiker', home_region = 'Secret Valley' WHERE id = :id"),
        {"u": f"alice_{alice.hex[:8]}", "id": alice},
    )
    # Opted in to community features, so her hike logs are readable through
    # REST at all (migration 9d4f2a6c8e13); the community tests turn it off.
    conn.execute(text("UPDATE public.profile_settings SET show_in_community = true WHERE user_id = :id"), {"id": alice})
    trail = conn.execute(
        text(
            "INSERT INTO public.trails (id, name, region, country_code, terrain_difficulty) "
            "VALUES (gen_random_uuid(), :name, 'Policy Test Park', 'CA', 'easy') RETURNING id"
        ),
        {"name": f"Policy test trail {uuid.uuid4()}"},
    ).scalar_one()
    hike_photo = f"{alice}/{uuid.uuid4()}.webp"
    gear_photo = f"{alice}/{uuid.uuid4()}.webp"
    stray_photo = f"{alice}/{uuid.uuid4()}.webp"
    conn.execute(
        text("INSERT INTO public.hike_logs (user_id, trail_id, hiked_on, note, photo_path) VALUES (:u, :t, '2026-08-14', 'Nice', :p)"),
        {"u": alice, "t": trail, "p": hike_photo},
    )
    category = conn.execute(text("SELECT id FROM public.catalog_categories LIMIT 1")).scalar_one()
    item = conn.execute(
        text("INSERT INTO public.user_gear_items (user_id, category_id, custom_name, notes, image_path) "
             "VALUES (:u, :c, 'Stove', 'serial 1234', :p) RETURNING id"),
        {"u": alice, "c": category, "p": gear_photo},
    ).scalar_one()
    setup = conn.execute(text("INSERT INTO public.gear_setups (user_id, name) VALUES (:u, 'Kit') RETURNING id"), {"u": alice}).scalar_one()
    conn.execute(text("INSERT INTO public.gear_setup_items (setup_id, gear_item_id) VALUES (:s, :i)"), {"s": setup, "i": item})
    conn.execute(text("INSERT INTO public.saved_trails (user_id, trail_id) VALUES (:u, :t)"), {"u": alice, "t": trail})
    plan = conn.execute(
        text("INSERT INTO public.trip_plans (id, user_id, trail_id, title, start_date, nights, party_size, notes) "
             "VALUES (gen_random_uuid(), :u, :t, 'Fall trip', '2027-07-01', 2, 3, 'gate code 4321') RETURNING id"),
        {"u": alice, "t": trail},
    ).scalar_one()
    conn.execute(text("INSERT INTO public.trip_plan_nights (trip_plan_id, night_index, choice) VALUES (:p, 0, 'undecided')"), {"p": plan})
    site = conn.execute(text("SELECT id FROM public.backcountry_sites LIMIT 1")).scalar()
    if site is not None:
        conn.execute(
            text("INSERT INTO public.availability_alerts (user_id, email, site_id, start_date, nights, party_size) "
                 "VALUES (:u, 'alice-alerts@example.com', :s, '2027-07-01', 1, 1)"),
            {"u": alice, "s": site},
        )
    for bucket, name in (("hike-photos", hike_photo), ("gear-photos", gear_photo), ("gear-photos", stray_photo)):
        conn.execute(text("INSERT INTO storage.objects (bucket_id, name, owner) VALUES (:b, :n, :o)"), {"b": bucket, "n": name, "o": alice})
    return {"alice": alice, "bob": bob, "trail": trail, "plan": plan, "item": item, "setup": setup,
            "hike_photo": hike_photo, "gear_photo": gear_photo, "stray_photo": stray_photo, "has_alert": site is not None}


def visitor(conn, world, who):
    act_as(conn, None if who == "guest" else world["bob"])


def settings(conn, world, **changes):
    """Alice changes her own settings, through RLS, as the REST API would."""
    act_as(conn, world["alice"])
    assignments = ", ".join(f"{key} = :{key}" for key in changes)
    updated = conn.execute(
        text(f"UPDATE public.profile_settings SET {assignments} WHERE user_id = :id"), {**changes, "id": world["alice"]}
    )
    assert updated.rowcount == 1


# Each section: a query that sees Alice's rows in it.
SECTION_QUERIES = {
    "journal": "SELECT id, note, photo_path FROM public.hike_logs WHERE user_id = :alice",
    "gear": "SELECT id, custom_name FROM public.user_gear_items WHERE user_id = :alice",
    "saved_trails": "SELECT trail_id FROM public.saved_trails WHERE user_id = :alice",
    "trip_plans": "SELECT id, title, start_date FROM public.trip_plans WHERE user_id = :alice",
}
SECTION_SETTINGS = {"journal": "show_journal", "gear": "show_gear", "saved_trails": "show_saved_trails", "trip_plans": "show_trip_plans"}


def visible(conn, world, who, section):
    visitor(conn, world, who)
    return len(rows(conn, SECTION_QUERIES[section], {"alice": world["alice"]})) > 0


def test_new_users_get_public_defaults(conn, world):
    as_admin(conn)
    row = rows(conn, "SELECT is_private, show_journal, show_rank, show_gear, show_saved_trails, show_trip_plans, "
                     "hide_hike_dates, allow_search_indexing, public_notice_pending FROM public.profile_settings WHERE user_id = :id",
               {"id": world["bob"]})
    assert row == [(False, True, True, True, True, False, False, False, False)]


def test_every_user_has_settings(conn, world):
    as_admin(conn)
    missing = conn.execute(text(
        "SELECT count(*) FROM auth.users u LEFT JOIN public.profile_settings s ON s.user_id = u.id WHERE s.user_id IS NULL"
    )).scalar_one()
    assert missing == 0


@pytest.mark.parametrize("who", VISITORS)
def test_visitors_see_the_default_public_sections(conn, world, who):
    for section in ("journal", "gear", "saved_trails"):
        assert visible(conn, world, who, section), section
    assert not visible(conn, world, who, "trip_plans")
    visitor(conn, world, who)
    assert rows(conn, "SELECT username, display_name, bio FROM public.profiles WHERE id = :id", {"id": world["alice"]})[0][2] == "Hiker"
    assert len(rows(conn, "SELECT setup_id FROM public.gear_setup_items WHERE setup_id = :s", {"s": world["setup"]})) == 1
    assert len(rows(conn, "SELECT name FROM public.gear_setups WHERE id = :s", {"s": world["setup"]})) == 1


@pytest.mark.parametrize("who", VISITORS)
@pytest.mark.parametrize("section", list(SECTION_QUERIES))
def test_each_section_follows_its_setting_immediately(conn, world, who, section):
    settings(conn, world, **{SECTION_SETTINGS[section]: True})
    assert visible(conn, world, who, section)
    settings(conn, world, **{SECTION_SETTINGS[section]: False})
    assert not visible(conn, world, who, section)
    if section == "gear":
        visitor(conn, world, who)
        assert rows(conn, "SELECT setup_id FROM public.gear_setup_items WHERE setup_id = :s", {"s": world["setup"]}) == []


@pytest.mark.parametrize("who", VISITORS)
def test_private_profile_hides_everything(conn, world, who):
    settings(conn, world, is_private=True, show_trip_plans=True)
    visitor(conn, world, who)
    assert rows(conn, "SELECT id FROM public.profiles WHERE id = :id", {"id": world["alice"]}) == []
    for section in SECTION_QUERIES:
        assert not visible(conn, world, who, section), section


@pytest.mark.parametrize("who", VISITORS)
def test_no_username_means_no_public_profile(conn, world, who):
    as_admin(conn)
    conn.execute(text("UPDATE public.profiles SET username = NULL WHERE id = :id"), {"id": world["alice"]})
    for section in ("journal", "gear", "saved_trails"):
        assert not visible(conn, world, who, section)


@pytest.mark.parametrize("who", VISITORS)
def test_admin_hidden_profiles_are_invisible(conn, world, who):
    as_admin(conn)
    conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:id)"), {"id": world["alice"]})
    visitor(conn, world, who)
    assert rows(conn, "SELECT id FROM public.profiles WHERE id = :id", {"id": world["alice"]}) == []
    for section in ("journal", "gear", "saved_trails"):
        assert not visible(conn, world, who, section)


def test_owner_cant_unhide_or_see_moderation_or_reports(conn, world):
    as_admin(conn)
    conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:id)"), {"id": world["alice"]})
    act_as(conn, world["alice"])
    assert refused(conn, "DELETE FROM public.profile_moderation WHERE user_id = :id", {"id": world["alice"]})
    assert refused(conn, "SELECT * FROM public.profile_moderation")
    assert refused(conn, "SELECT * FROM public.profile_reports")
    assert refused(conn, "INSERT INTO public.profile_reports (reporter_id, profile_id, reason) VALUES (:a, :a, 'spam')",
                   {"a": world["alice"]})


@pytest.mark.parametrize("who", VISITORS)
def test_columns_outside_a_public_profile_are_never_readable(conn, world, who):
    visitor(conn, world, who)
    for statement in (
        "SELECT home_region FROM public.profiles",
        "SELECT created_at FROM public.profiles",
        "SELECT hiked_on FROM public.hike_logs",
        "SELECT created_at FROM public.hike_logs",
        "SELECT * FROM public.hike_logs",
        "SELECT notes FROM public.user_gear_items",
        "SELECT notes FROM public.trip_plans",
        "SELECT party_size FROM public.trip_plans",
        "SELECT id FROM public.hike_logs WHERE hiked_on > '2000-01-01'",  # no probing by filter either
    ):
        assert refused(conn, statement), statement


def test_the_owner_still_has_their_own_rows_when_private(conn, world):
    settings(conn, world, is_private=True)
    act_as(conn, world["alice"])
    for section, query in SECTION_QUERIES.items():
        assert rows(conn, query, {"alice": world["alice"]}), section
    assert rows(conn, "SELECT night_index FROM public.trip_plan_nights") == [(0,)]


@pytest.mark.parametrize("who", VISITORS)
def test_alerts_plan_nights_settings_and_emails_stay_private(conn, world, who):
    settings(conn, world, show_trip_plans=True)
    visitor(conn, world, who)
    if who == "guest":
        assert refused(conn, "SELECT id FROM public.availability_alerts")
        assert refused(conn, "SELECT night_index FROM public.trip_plan_nights")
        assert refused(conn, "SELECT user_id FROM public.profile_settings")
    else:
        assert rows(conn, "SELECT id FROM public.availability_alerts WHERE user_id = :a", {"a": world["alice"]}) == []
        assert rows(conn, "SELECT night_index FROM public.trip_plan_nights WHERE trip_plan_id = :p", {"p": world["plan"]}) == []
        assert rows(conn, "SELECT user_id FROM public.profile_settings WHERE user_id = :a", {"a": world["alice"]}) == []
        updated = conn.execute(text("UPDATE public.profile_settings SET is_private = false WHERE user_id = :a"), {"a": world["alice"]})
        assert updated.rowcount == 0
    assert refused(conn, "SELECT email FROM auth.users")


def test_owner_cant_create_extra_settings_rows(conn, world):
    act_as(conn, world["alice"])
    assert refused(conn, "INSERT INTO public.profile_settings (user_id) VALUES (:id)", {"id": world["bob"]})


# ---------------------------------------------------------------- photos


def objects(conn, bucket, name):
    return rows(conn, "SELECT name FROM storage.objects WHERE bucket_id = :b AND name = :n", {"b": bucket, "n": name})


@pytest.mark.parametrize("who", VISITORS)
def test_photos_follow_their_section(conn, world, who):
    visitor(conn, world, who)
    assert objects(conn, "hike-photos", world["hike_photo"])

    settings(conn, world, show_journal=False)
    visitor(conn, world, who)
    assert not objects(conn, "hike-photos", world["hike_photo"])


@pytest.mark.parametrize("who", VISITORS)
def test_gear_photos_are_owner_only_even_in_public_gear(conn, world, who):
    """Migration 6e2f4b8d1a37: visitors get the catalogue photo or icon instead."""
    visitor(conn, world, who)
    assert visible(conn, world, who, "gear")
    assert not objects(conn, "gear-photos", world["gear_photo"])
    assert not objects(conn, "gear-photos", world["stray_photo"])
    assert refused(conn, "SELECT image_path FROM public.user_gear_items")

    act_as(conn, world["alice"])
    assert objects(conn, "gear-photos", world["gear_photo"])
    assert objects(conn, "gear-photos", world["stray_photo"])


def test_referencing_someone_elses_photo_doesnt_publish_it(conn, world):
    """Bob points his own public gear at Alice's private photo."""
    settings(conn, world, show_gear=False)
    as_admin(conn)
    conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"), {"u": f"bob_{world['bob'].hex[:8]}", "id": world["bob"]})
    act_as(conn, world["bob"])
    category = conn.execute(text("SELECT id FROM public.catalog_categories LIMIT 1")).scalar_one()
    conn.execute(text("INSERT INTO public.user_gear_items (user_id, category_id, custom_name, image_path) VALUES (:u, :c, 'Mine', :p)"),
                 {"u": world["bob"], "c": category, "p": world["gear_photo"]})
    act_as(conn, None)
    assert not objects(conn, "gear-photos", world["gear_photo"])


def test_gear_photos_now_only_take_processed_images(conn, world):
    as_admin(conn)
    limit, types = conn.execute(text("SELECT file_size_limit, allowed_mime_types FROM storage.buckets WHERE id = 'gear-photos'")).one()
    assert limit == 1024 * 1024 and sorted(types) == ["image/jpeg", "image/webp"]
    act_as(conn, world["alice"])
    for name in ("photo.png", f"{uuid.uuid4()}.png", f"{uuid.uuid4()}.jpeg"):
        assert refused(conn, "INSERT INTO storage.objects (bucket_id, name) VALUES ('gear-photos', :n)",
                       {"n": f"{world['alice']}/{name}"}, reason="row-level security")
    conn.execute(text("INSERT INTO storage.objects (bucket_id, name) VALUES ('gear-photos', :n)"),
                 {"n": f"{world['alice']}/{uuid.uuid4()}.webp"})


# ------------------------------------------------------- community features
# "Hiked by" on trail pages (migration 9d4f2a6c8e13): a trail's hike logs
# show someone only while they've opted in and their journal is public.

HIKED_BY = "SELECT user_id, note, photo_path FROM public.hike_logs WHERE trail_id = :trail"


def hiked_by(conn, world, who):
    visitor(conn, world, who)
    return [row[0] for row in rows(conn, HIKED_BY, {"trail": world["trail"]})]


def test_community_is_off_for_new_and_existing_users(conn, world):
    as_admin(conn)
    assert rows(conn, "SELECT show_in_community FROM public.profile_settings WHERE user_id = :id", {"id": world["bob"]}) == [(False,)]
    # The migration added it NOT NULL DEFAULT false, so every existing row started off.
    default = conn.execute(text(
        "SELECT column_default, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'profile_settings' AND column_name = 'show_in_community'"
    )).one()
    assert default == ("false", "NO")


@pytest.mark.parametrize("who", VISITORS)
def test_hiked_by_lists_only_opted_in_hikers(conn, world, who):
    assert hiked_by(conn, world, who) == [world["alice"]]
    settings(conn, world, show_in_community=False)
    assert hiked_by(conn, world, who) == []
    # Her public journal photo is still visible on her profile.
    visitor(conn, world, who)
    assert objects(conn, "hike-photos", world["hike_photo"])


@pytest.mark.parametrize("who", VISITORS)
@pytest.mark.parametrize("change", [{"is_private": True}, {"show_journal": False}], ids=["private", "journal-hidden"])
def test_opting_in_needs_a_public_journal(conn, world, who, change):
    settings(conn, world, **change)
    assert hiked_by(conn, world, who) == []
    settings(conn, world, **{key: not value for key, value in change.items()})
    assert hiked_by(conn, world, who) == [world["alice"]]


@pytest.mark.parametrize("who", VISITORS)
def test_hiked_by_skips_admin_hidden_profiles(conn, world, who):
    as_admin(conn)
    conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:id)"), {"id": world["alice"]})
    assert hiked_by(conn, world, who) == []


def test_owners_change_only_their_own_community_setting(conn, world):
    settings(conn, world, show_in_community=False)
    act_as(conn, world["bob"])
    updated = conn.execute(text("UPDATE public.profile_settings SET show_in_community = true WHERE user_id = :a"),
                           {"a": world["alice"]})
    assert updated.rowcount == 0
    act_as(conn, world["alice"])
    assert len(rows(conn, HIKED_BY, {"trail": world["trail"]})) == 1  # her own rows, opted in or not
    act_as(conn, None)
    assert refused(conn, "UPDATE public.profile_settings SET show_in_community = true")
