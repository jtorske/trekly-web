"""Official and demo account rules in the database (migration f4a9c2e7b1d3),
checked against the local Supabase stack. Every test is rolled back.

Opt-in and local-only like the other policy tests: set LOCAL_SUPABASE_DB_URL.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_profile_privacy_policies import (  # noqa: F401  (fixtures)
    DB_URL, act_as, as_admin, conn, engine, refused, rows,
)

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


def _user(conn, name):  # noqa: F811
    user = uuid.uuid4()
    conn.execute(
        text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :e)"),
        {"id": user, "e": f"{user}@policy-test.local"},
    )
    conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"),
                 {"u": f"{name}_{user.hex[:8]}", "id": user})
    conn.execute(text("UPDATE public.profile_settings SET share_activity = true WHERE user_id = :id"), {"id": user})
    return user


@pytest.fixture
def world(conn):  # noqa: F811
    as_admin(conn)
    # Another official account may already exist locally; stand it aside for the test.
    conn.execute(text("DELETE FROM public.account_labels WHERE label = 'official'"))
    official, alice = _user(conn, "off"), _user(conn, "alice")
    conn.execute(text("INSERT INTO public.account_labels (user_id, label) VALUES (:u, 'official')"), {"u": official})
    posts = {}
    for name, user in (("official", official), ("alice", alice)):
        posts[name] = conn.execute(
            text("INSERT INTO public.activity_posts (user_id, kind, body) VALUES (:u, 'announcement', 'Hi') RETURNING id"),
            {"u": user},
        ).scalar_one()
    return {"official": official, "alice": alice, "posts": posts}


@pytest.mark.parametrize("who", ("guest", "alice"))
def test_only_the_official_accounts_announcements_are_readable(conn, world, who):  # noqa: F811
    act_as(conn, None if who == "guest" else world["alice"])
    ids = {row.id for row in rows(conn, "SELECT id FROM public.activity_posts WHERE kind = 'announcement'")}
    assert world["posts"]["official"] in ids
    if who == "guest":
        assert world["posts"]["alice"] not in ids


@pytest.mark.parametrize("who", ("guest", "alice"))
def test_clients_cannot_read_or_write_labels(conn, world, who):  # noqa: F811
    act_as(conn, None if who == "guest" else world["alice"])
    assert refused(conn, "SELECT * FROM public.account_labels")
    assert refused(conn, "INSERT INTO public.account_labels (user_id, label) VALUES (:u, 'official')",
                   {"u": world["alice"]})


def test_only_the_official_account_may_hold_a_reserved_name(conn, world):  # noqa: F811
    as_admin(conn)
    conn.execute(text("UPDATE public.profiles SET username = 'trekly_team' WHERE id = :id"), {"id": world["official"]})
    with pytest.raises(DBAPIError, match="username_reserved"), conn.begin_nested():
        conn.execute(text("UPDATE public.profiles SET username = 'support' WHERE id = :id"),
                     {"id": world["alice"]})


def test_there_is_one_official_account(conn, world):  # noqa: F811
    as_admin(conn)
    with pytest.raises(DBAPIError, match="account_labels_one_official"), conn.begin_nested():
        conn.execute(text("INSERT INTO public.account_labels (user_id, label) VALUES (:u, 'official')"),
                     {"u": world["alice"]})
