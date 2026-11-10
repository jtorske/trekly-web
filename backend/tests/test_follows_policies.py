"""Follows row-level security, checked against the local Supabase stack.

- An approved follower of a private profile reads the sections its owner
  switched on, through the same policies as a public profile's visitors;
  a pending request, a guest or anyone else reads nothing.
- Community features ("Hiked by" hike_logs rows) stay public-only.
- The follows table is read-only for clients, and each user sees only the
  rows they're part of, so hidden lists can't be read around the API.

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.test_profile_privacy_policies import (  # noqa: F401  (fixtures)
    DB_URL, act_as, as_admin, conn, engine, refused, rows, world,
)

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture
def cam(conn):  # noqa: F811
    as_admin(conn)
    user = uuid.uuid4()
    conn.execute(
        text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :e)"),
        {"id": user, "e": f"{user}@policy-test.local"},
    )
    return user


def private(conn, world, **switches):  # noqa: F811
    as_admin(conn)
    sets = ", ".join(["is_private = true", *(f"{key} = :{key}" for key in switches)])
    conn.execute(text(f"UPDATE public.profile_settings SET {sets} WHERE user_id = :id"), {**switches, "id": world["alice"]})


def follow(conn, follower, followee, status="accepted"):  # noqa: F811
    as_admin(conn)
    conn.execute(
        text("INSERT INTO public.follows (follower_id, followee_id, status) VALUES (:a, :b, :s) "
             "ON CONFLICT (follower_id, followee_id) DO UPDATE SET status = excluded.status"),
        {"a": follower, "b": followee, "s": status},
    )


def reads(conn, who, statement, params):  # noqa: F811
    act_as(conn, who)
    found = rows(conn, statement, params)
    as_admin(conn)
    return found


PROFILE = "SELECT bio FROM public.profiles WHERE id = :alice"
GEAR = "SELECT id FROM public.user_gear_items WHERE user_id = :alice"
SAVED = "SELECT trail_id FROM public.saved_trails WHERE user_id = :alice"
PLANS = "SELECT id FROM public.trip_plans WHERE user_id = :alice"
HIKES = "SELECT id FROM public.hike_logs WHERE user_id = :alice"
HIKE_PHOTO = "SELECT name FROM storage.objects WHERE bucket_id = 'hike-photos' AND name = :name"


def test_an_approved_follower_reads_a_private_profiles_shown_sections(conn, world):  # noqa: F811
    private(conn, world, show_gear=False)
    follow(conn, world["bob"], world["alice"])
    params = {"alice": world["alice"]}
    assert reads(conn, world["bob"], PROFILE, params) == [("Hiker",)]
    assert reads(conn, world["bob"], SAVED, params) != []
    assert reads(conn, world["bob"], HIKE_PHOTO, {"name": world["hike_photo"]}) != []
    # Switched off, or private by default: still nothing.
    assert reads(conn, world["bob"], GEAR, params) == []
    assert reads(conn, world["bob"], PLANS, params) == []


def test_community_rows_stay_public_only(conn, world):  # noqa: F811
    """hike_logs rows are readable only through "Hiked by", which needs a public profile."""
    params = {"alice": world["alice"]}
    assert reads(conn, None, HIKES, params) != []
    private(conn, world)
    follow(conn, world["bob"], world["alice"])
    assert reads(conn, world["bob"], HIKES, params) == []


@pytest.mark.parametrize("status", ["pending", None])
def test_requests_guests_and_others_read_nothing_private(conn, world, cam, status):  # noqa: F811
    private(conn, world)
    if status:
        follow(conn, world["bob"], world["alice"], status)
    follow(conn, cam, world["bob"])  # following someone else gives nothing
    params = {"alice": world["alice"]}
    for who in (None, world["bob"], cam):
        assert reads(conn, who, PROFILE, params) == []
        assert reads(conn, who, SAVED, params) == []
        assert reads(conn, who, HIKE_PHOTO, {"name": world["hike_photo"]}) == []


def test_admin_hidden_beats_an_approved_follow(conn, world):  # noqa: F811
    private(conn, world)
    follow(conn, world["bob"], world["alice"])
    conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:u)"), {"u": world["alice"]})
    assert reads(conn, world["bob"], PROFILE, {"alice": world["alice"]}) == []


def test_follows_rows_are_only_for_the_two_people_in_them(conn, world, cam):  # noqa: F811
    follow(conn, world["bob"], world["alice"])
    statement = "SELECT follower_id, followee_id, status FROM public.follows WHERE followee_id = :alice"
    params = {"alice": world["alice"]}
    assert reads(conn, world["bob"], statement, params) == [(world["bob"], world["alice"], "accepted")]
    assert len(reads(conn, world["alice"], statement, params)) == 1
    assert reads(conn, cam, statement, params) == []
    act_as(conn, None)
    assert refused(conn, "SELECT follower_id FROM public.follows")


def test_clients_cant_write_follows(conn, world, cam):  # noqa: F811
    private(conn, world)
    follow(conn, world["bob"], world["alice"], "pending")
    act_as(conn, world["bob"])
    # Bob can't approve himself, or follow anyone directly.
    assert refused(conn, "UPDATE public.follows SET status = 'accepted' WHERE follower_id = :b", {"b": world["bob"]})
    assert refused(conn, "INSERT INTO public.follows (follower_id, followee_id, status) VALUES (:b, :c, 'accepted')",
                   {"b": world["bob"], "c": cam})
    act_as(conn, world["alice"])
    assert refused(conn, "DELETE FROM public.follows WHERE followee_id = :a", {"a": world["alice"]})
    # created_at would date the follow; it isn't granted.
    assert refused(conn, "SELECT created_at FROM public.follows")


def test_owners_can_hide_their_lists_through_rls(conn, world):  # noqa: F811
    act_as(conn, world["alice"])
    updated = conn.execute(text("UPDATE public.profile_settings SET hide_follow_lists = true WHERE user_id = :id"),
                           {"id": world["alice"]})
    assert updated.rowcount == 1
