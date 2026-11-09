"""Activity feed row-level security, checked against the local Supabase stack.

Reads activity_posts and activity_reactions as a guest (anon) and as another
signed-in user, while the owner changes their settings, to check the same
rule the API applies (app/activity.py, migration a8c3f1d5e7b2). Every test
runs in a transaction that is rolled back.

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.test_profile_privacy_policies import (  # noqa: F401  (fixtures)
    DB_URL, act_as, as_admin, conn, engine, refused, rows,
)

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")
VISITORS = ("guest", "bob")


@pytest.fixture
def world(conn):  # noqa: F811
    """Alice (public, sharing) with a hike post, a milestone post and a rank post; Bob."""
    as_admin(conn)
    alice, bob = uuid.uuid4(), uuid.uuid4()
    for user in (alice, bob):
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email) VALUES (:id, 'authenticated', 'authenticated', :e)"),
            {"id": user, "e": f"{user}@policy-test.local"},
        )
    conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"),
                 {"u": f"alice_{alice.hex[:8]}", "id": alice})
    conn.execute(text("UPDATE public.profile_settings SET share_activity = true WHERE user_id = :id"), {"id": alice})
    trail = conn.execute(
        text("INSERT INTO public.trails (id, name, region, country_code, terrain_difficulty) "
             "VALUES (gen_random_uuid(), :n, 'Policy Test Park', 'CA', 'easy') RETURNING id"),
        {"n": f"Policy test trail {uuid.uuid4()}"},
    ).scalar_one()
    log = conn.execute(
        text("INSERT INTO public.hike_logs (user_id, trail_id, hiked_on) VALUES (:u, :t, '2026-07-01') RETURNING id"),
        {"u": alice, "t": trail},
    ).scalar_one()
    posts = {}
    for kind, extra in (("hike", {}), ("milestone", {"milestone": "first-hike"}), ("rank", {"rank_level": 2}),
                        ("seasonal", {"milestone": "canada-day", "reveals_date": True})):
        posts[kind] = conn.execute(
            text("INSERT INTO public.activity_posts (user_id, kind, hike_log_id, milestone, rank_level, reveals_date) "
                 "VALUES (:u, :k, :h, :m, :r, :d) RETURNING id"),
            {"u": alice, "k": "milestone" if kind == "seasonal" else kind, "h": log, "m": extra.get("milestone"),
             "r": extra.get("rank_level"), "d": extra.get("reveals_date", False)},
        ).scalar_one()
    conn.execute(text("INSERT INTO public.activity_reactions (post_id, user_id) VALUES (:p, :u)"),
                 {"p": posts["hike"], "u": bob})
    return {"alice": alice, "bob": bob, "log": log, "posts": posts}


def visitor(conn, world, who):  # noqa: F811
    act_as(conn, None if who == "guest" else world["bob"])


def seen(conn, world, who):  # noqa: F811
    """The kinds of Alice's posts a visitor can read (seasonal told apart)."""
    visitor(conn, world, who)
    ids = {row.id for row in rows(conn, "SELECT id FROM public.activity_posts WHERE user_id = :u", {"u": world["alice"]})}
    as_admin(conn)
    return {name for name, post_id in world["posts"].items() if post_id in ids}


def settings(conn, world, **changes):  # noqa: F811
    as_admin(conn)
    assignments = ", ".join(f"{key} = :{key}" for key in changes)
    conn.execute(text(f"UPDATE public.profile_settings SET {assignments} WHERE user_id = :id"),
                 {**changes, "id": world["alice"]})


@pytest.mark.parametrize("who", VISITORS)
def test_a_sharing_public_profiles_posts_are_readable(conn, world, who):  # noqa: F811
    assert seen(conn, world, who) == {"hike", "milestone", "rank", "seasonal"}


def test_sharing_is_off_for_new_users(conn, world):  # noqa: F811
    as_admin(conn)
    assert conn.execute(text("SELECT share_activity FROM public.profile_settings WHERE user_id = :id"),
                        {"id": world["bob"]}).scalar_one() is False


@pytest.mark.parametrize("who", VISITORS)
@pytest.mark.parametrize(
    "change, left",
    [
        ({"share_activity": False}, set()),
        ({"is_private": True}, set()),
        ({"show_journal": False}, {"rank"}),
        ({"show_rank": False}, {"hike", "milestone", "seasonal"}),
        ({"hide_hike_dates": True}, {"hike", "milestone", "rank"}),
    ],
    ids=["share-off", "private", "journal-hidden", "rank-hidden", "dates-hidden"],
)
def test_each_setting_applies_immediately(conn, world, who, change, left):  # noqa: F811
    settings(conn, world, **change)
    assert seen(conn, world, who) == left


@pytest.mark.parametrize("who", VISITORS)
def test_no_username_admin_hide_or_post_hide_means_unreadable(conn, world, who):  # noqa: F811
    as_admin(conn)
    conn.execute(text("UPDATE public.activity_posts SET hidden_at = now() WHERE id = :p"), {"p": world["posts"]["rank"]})
    assert seen(conn, world, who) == {"hike", "milestone", "seasonal"}
    conn.execute(text("INSERT INTO public.profile_moderation (user_id) VALUES (:u)"), {"u": world["alice"]})
    assert seen(conn, world, who) == set()


@pytest.mark.parametrize("who", VISITORS)
def test_future_dated_hike_posts_are_unreadable(conn, world, who):  # noqa: F811
    as_admin(conn)
    conn.execute(text("UPDATE public.hike_logs SET hiked_on = current_date + 30 WHERE id = :h"), {"h": world["log"]})
    assert "hike" not in seen(conn, world, who)


@pytest.mark.parametrize("who", VISITORS)
def test_only_what_a_post_is_can_be_read(conn, world, who):  # noqa: F811
    visitor(conn, world, who)
    for column in ("created_at", "hike_log_id", "hidden_at", "hidden_by", "hidden_reason", "reveals_date"):
        assert refused(conn, f"SELECT {column} FROM public.activity_posts"), column
    assert refused(conn, "SELECT user_id FROM public.activity_reactions")
    assert refused(conn, "SELECT created_at FROM public.activity_reactions")
    count = conn.execute(text("SELECT count(*) FROM public.activity_reactions WHERE post_id = :p"),
                         {"p": world["posts"]["hike"]}).scalar_one()
    assert count == 1


@pytest.mark.parametrize("who", ("guest", "bob", "alice"))
def test_clients_cant_write_posts_or_reactions(conn, world, who):  # noqa: F811
    act_as(conn, {"guest": None, "bob": world["bob"], "alice": world["alice"]}[who])
    me = world["alice"] if who == "alice" else world["bob"]
    assert refused(conn, "INSERT INTO public.activity_posts (user_id, kind, rank_level) VALUES (:u, 'rank', 7)", {"u": me})
    assert refused(conn, "UPDATE public.activity_posts SET hidden_at = NULL")
    assert refused(conn, "DELETE FROM public.activity_posts")
    assert refused(conn, "INSERT INTO public.activity_reactions (post_id, user_id) VALUES (:p, :u)",
                   {"p": world["posts"]["milestone"], "u": me})
    assert refused(conn, "DELETE FROM public.activity_reactions")


def test_owners_still_read_their_own_posts_when_not_sharing(conn, world):  # noqa: F811
    settings(conn, world, share_activity=False)
    act_as(conn, world["alice"])
    own = rows(conn, "SELECT id FROM public.activity_posts WHERE user_id = :u", {"u": world["alice"]})
    assert len(own) == 4


def test_owners_change_only_their_own_sharing_switch(conn, world):  # noqa: F811
    act_as(conn, world["bob"])
    conn.execute(text("UPDATE public.profile_settings SET share_activity = true WHERE user_id = :u"), {"u": world["alice"]})
    conn.execute(text("UPDATE public.profile_settings SET share_activity = false WHERE user_id = :u"), {"u": world["alice"]})
    conn.execute(text("UPDATE public.profile_settings SET share_activity = true WHERE user_id = :u"), {"u": world["bob"]})
    as_admin(conn)
    values = dict(conn.execute(text("SELECT user_id, share_activity FROM public.profile_settings WHERE user_id IN (:a, :b)"),
                               {"a": world["alice"], "b": world["bob"]}).all())
    assert values == {world["alice"]: True, world["bob"]: True}


def test_deleting_the_hike_deletes_its_posts_and_reactions(conn, world):  # noqa: F811
    act_as(conn, world["alice"])
    conn.execute(text("DELETE FROM public.hike_logs WHERE id = :h"), {"h": world["log"]})
    as_admin(conn)
    assert rows(conn, "SELECT id FROM public.activity_posts WHERE user_id = :u", {"u": world["alice"]}) == []
    assert rows(conn, "SELECT post_id FROM public.activity_reactions WHERE user_id = :u", {"u": world["bob"]}) == []
