"""Comments row-level security, checked against the local Supabase stack.

Only the API reads and writes activity_comments (migration f2c8a4e6b1d9):
RLS is on and clients hold no grants, so nobody (a guest, the commenter, the
post's author) can read, forge, edit or delete a comment through the REST
API, and every rule in app/comments.py holds. Comments go with their post,
their parent comment, and their author's account.

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL to the CLI stack's Postgres.
"""

import pytest
from sqlalchemy import text

from tests.test_profile_privacy_policies import (  # noqa: F401  (fixtures)
    DB_URL, act_as, as_admin, conn, engine, refused, world,
)

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture
def post(conn, world):  # noqa: F811
    as_admin(conn)
    log = conn.execute(text("SELECT id FROM public.hike_logs WHERE user_id = :a"), {"a": world["alice"]}).scalar_one()
    return conn.execute(
        text("INSERT INTO public.activity_posts (user_id, kind, hike_log_id) VALUES (:a, 'hike', :h) RETURNING id"),
        {"a": world["alice"], "h": log},
    ).scalar_one()


@pytest.fixture
def comment(conn, world, post):  # noqa: F811
    as_admin(conn)
    return conn.execute(
        text("INSERT INTO public.activity_comments (post_id, user_id, body) VALUES (:p, :b, 'Nice') RETURNING id"),
        {"p": post, "b": world["bob"]},
    ).scalar_one()


@pytest.mark.parametrize("who", ["guest", "commenter", "post_author"])
def test_clients_cant_read_or_write_comments(conn, world, post, comment, who):  # noqa: F811
    act_as(conn, {"guest": None, "commenter": world["bob"], "post_author": world["alice"]}[who])
    assert refused(conn, "SELECT id FROM public.activity_comments")
    assert refused(conn, "UPDATE public.activity_comments SET body = 'Changed'")
    assert refused(conn, "DELETE FROM public.activity_comments")
    assert refused(conn, "INSERT INTO public.activity_comments (post_id, user_id, body) VALUES (:p, :b, 'Forged')",
                   {"p": post, "b": world["bob"]})


def test_clients_cant_turn_comments_off(conn, world, post):  # noqa: F811
    act_as(conn, world["alice"])
    assert refused(conn, "UPDATE public.activity_posts SET comments_off = true")


def test_comments_go_with_the_post_and_their_parent(conn, world, post, comment):  # noqa: F811
    as_admin(conn)
    reply = conn.execute(
        text("INSERT INTO public.activity_comments (post_id, user_id, parent_id, body) "
             "VALUES (:p, :a, :c, 'Thanks') RETURNING id"),
        {"p": post, "a": world["alice"], "c": comment},
    ).scalar_one()
    conn.execute(text("INSERT INTO public.notifications (user_id, actor_id, kind, post_id, comment_id) "
                      "VALUES (:b, :a, 'comment_reply', :p, :r)"),
                 {"a": world["alice"], "b": world["bob"], "p": post, "r": reply})
    conn.execute(text("DELETE FROM public.activity_comments WHERE id = :c"), {"c": comment})
    assert conn.execute(text("SELECT count(*) FROM public.activity_comments WHERE post_id = :p"), {"p": post}).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM public.notifications WHERE comment_id = :r"), {"r": reply}).scalar_one() == 0
    conn.execute(text("INSERT INTO public.activity_comments (post_id, user_id, body) VALUES (:p, :b, 'Again')"),
                 {"p": post, "b": world["bob"]})
    conn.execute(text("DELETE FROM public.activity_posts WHERE id = :p"), {"p": post})
    assert conn.execute(text("SELECT count(*) FROM public.activity_comments WHERE post_id = :p"), {"p": post}).scalar_one() == 0


def test_comments_go_with_the_account(conn, world, post, comment):  # noqa: F811
    as_admin(conn)
    conn.execute(text("DELETE FROM auth.users WHERE id = :b"), {"b": world["bob"]})
    assert conn.execute(text("SELECT count(*) FROM public.activity_comments WHERE id = :c"), {"c": comment}).scalar_one() == 0


def test_comment_text_is_bounded_by_the_database_too(conn, world, post):  # noqa: F811
    as_admin(conn)
    assert refused(conn, "INSERT INTO public.activity_comments (post_id, user_id, body) VALUES (:p, :b, :t)",
                   {"p": post, "b": world["bob"], "t": "x" * 501}, reason="activity_comments_body_length_check")
