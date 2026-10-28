"""Featured badge RLS (migration 8b3e5f1c2d40), checked against the local Supabase stack.

Only the owner writes their featured badges; anyone reads them while the
owner's Trail Journal is public. A trail badge needs the owner's own hike
log and goes when it does. Every test runs in a transaction that is rolled
back.

Opt-in and local-only: set LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres
(supabase/config.toml, [db] port 44322). Non-local hosts are refused.
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
        pytest.fail(f"Refusing to run featured badge policy tests against non-local host {host!r}")
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
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(statement), params)
    except DBAPIError as error:
        savepoint.rollback()
        assert reason in str(error.orig), error.orig
        return True
    savepoint.rollback()
    return False


@pytest.fixture
def world(conn):
    """Alice (public profile, Trail Journal on) has hiked `hiked`; nobody has hiked `other`."""
    conn.execute(text("RESET ROLE"))
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user in (alice, bob):
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :email)"),
            {"id": user, "email": f"{user}@policy-test.local"},
        )
    conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"), {"u": f"alice_{alice.hex[:8]}", "id": alice})
    conn.execute(
        text("UPDATE public.profile_settings SET is_private = false, show_journal = true WHERE user_id = :id"), {"id": alice}
    )
    trails = []
    for _ in range(2):
        trails.append(
            conn.execute(
                text(
                    "INSERT INTO public.trails (id, name, region, country_code, terrain_difficulty) "
                    "VALUES (gen_random_uuid(), :name, 'Policy Test Park', 'CA', 'easy') RETURNING id"
                ),
                {"name": f"Policy test trail {uuid.uuid4()}"},
            ).scalar_one()
        )
    hiked, other = trails
    conn.execute(
        text("INSERT INTO public.hike_logs (user_id, trail_id, hiked_on) VALUES (:u, :t, '2026-08-14')"), {"u": alice, "t": hiked}
    )
    return {"alice": alice, "bob": bob, "hiked": hiked, "other": other}


INSERT = "INSERT INTO public.featured_badges (user_id, position, trail_id, milestone) VALUES (:user, :position, :trail, :milestone)"


def feature(conn, user, position=0, trail=None, milestone=None):
    conn.execute(text(INSERT), {"user": user, "position": position, "trail": trail, "milestone": milestone})


def count(conn, user):
    return conn.execute(text("SELECT count(*) FROM public.featured_badges WHERE user_id = :u"), {"u": user}).scalar_one()


def test_owner_can_feature_edit_and_clear_their_badges(conn, world):
    alice = world["alice"]
    act_as(conn, alice)
    feature(conn, alice, 0, trail=world["hiked"])
    feature(conn, alice, 1, milestone="first-hike")
    assert count(conn, alice) == 2
    moved = conn.execute(text("UPDATE public.featured_badges SET position = 2 WHERE milestone = 'first-hike' AND user_id = :u"), {"u": alice})
    assert moved.rowcount == 1
    assert conn.execute(text("DELETE FROM public.featured_badges WHERE user_id = :u"), {"u": alice}).rowcount == 2


def test_nobody_else_can_write_your_featured_badges(conn, world):
    alice, bob = world["alice"], world["bob"]
    act_as(conn, alice)
    feature(conn, alice, 0, trail=world["hiked"])

    act_as(conn, bob)
    assert refused(conn, INSERT, {"user": alice, "position": 1, "trail": None, "milestone": "first-hike"})
    updated = conn.execute(text("UPDATE public.featured_badges SET position = 2 WHERE user_id = :u"), {"u": alice})
    deleted = conn.execute(text("DELETE FROM public.featured_badges WHERE user_id = :u"), {"u": alice})
    assert updated.rowcount == 0 and deleted.rowcount == 0
    act_as(conn, None)
    assert refused(conn, INSERT, {"user": alice, "position": 1, "trail": None, "milestone": "first-hike"}, reason="permission denied")
    conn.execute(text("RESET ROLE"))
    assert count(conn, alice) == 1


def test_only_a_trail_you_have_logged_can_be_featured(conn, world):
    """Unearned, or someone else's hike: the foreign key to your own hike log refuses it."""
    alice, bob = world["alice"], world["bob"]
    act_as(conn, alice)
    assert refused(conn, INSERT, {"user": alice, "position": 0, "trail": world["other"], "milestone": None}, reason="featured_badges_hike_fkey")
    act_as(conn, bob)
    assert refused(conn, INSERT, {"user": bob, "position": 0, "trail": world["hiked"], "milestone": None}, reason="featured_badges_hike_fkey")


@pytest.mark.parametrize(
    "rows, reason",
    [
        ([(0, "hiked", None), (1, "hiked", None)], "featured_badges_trail_key"),
        ([(0, None, "first-hike"), (1, None, "first-hike")], "featured_badges_milestone_key"),
        ([(0, None, "first-hike"), (0, None, "first-overnight")], "featured_badges_position_key"),
        ([(3, None, "first-hike")], "featured_badges_position_check"),
        ([(0, None, "summit-everest")], "featured_badges_milestone_check"),
        ([(0, "hiked", "first-hike")], "featured_badges_one_kind_check"),
        ([(0, None, None)], "featured_badges_one_kind_check"),
    ],
)
def test_duplicates_more_than_three_and_unknown_badges_are_refused(conn, world, rows, reason):
    alice = world["alice"]
    act_as(conn, alice)
    *first, last = rows
    for position, trail, milestone in first:
        feature(conn, alice, position, trail=world[trail] if trail else None, milestone=milestone)
    position, trail, milestone = last
    params = {"user": alice, "position": position, "trail": world[trail] if trail else None, "milestone": milestone}
    assert refused(conn, INSERT, params, reason=reason)


def test_deleting_the_hike_deletes_its_featured_badge(conn, world):
    alice = world["alice"]
    act_as(conn, alice)
    feature(conn, alice, 0, trail=world["hiked"])
    feature(conn, alice, 1, milestone="first-hike")
    conn.execute(text("DELETE FROM public.hike_logs WHERE user_id = :u AND trail_id = :t"), {"u": alice, "t": world["hiked"]})
    rows = conn.execute(text("SELECT milestone FROM public.featured_badges WHERE user_id = :u"), {"u": alice}).scalars().all()
    # The milestone row is the API's to prune (app/featured.py); the trail badge is gone at once.
    assert rows == ["first-hike"]


def test_visitors_read_featured_badges_only_while_the_journal_is_public(conn, world):
    alice, bob = world["alice"], world["bob"]
    act_as(conn, alice)
    feature(conn, alice, 0, milestone="first-hike")
    for viewer in (bob, None):
        act_as(conn, viewer)
        assert count(conn, alice) == 1

    for change in ("is_private = false, show_journal = false", "is_private = true, show_journal = true"):
        conn.execute(text("RESET ROLE"))
        conn.execute(text(f"UPDATE public.profile_settings SET {change} WHERE user_id = :id"), {"id": alice})
        for viewer in (bob, None):
            act_as(conn, viewer)
            assert count(conn, alice) == 0, change
        # The owner still sees their own.
        act_as(conn, alice)
        assert count(conn, alice) == 1
