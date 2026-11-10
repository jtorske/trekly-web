"""Notifications row-level security, checked against the local Supabase stack.

Only the API reads and writes notifications and notification preferences
(migration c6e1a4d8b2f5): clients hold no grants on either table, so not
even a recipient can read, mark or forge one through the REST API.

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
def note(conn, world):  # noqa: F811
    as_admin(conn)
    return conn.execute(
        text("INSERT INTO public.notifications (user_id, actor_id, kind) VALUES (:a, :b, 'new_follower') RETURNING id"),
        {"a": world["alice"], "b": world["bob"]},
    ).scalar_one()


@pytest.mark.parametrize("who", ["guest", "recipient", "actor"])
def test_clients_cant_read_or_write_notifications(conn, world, note, who):  # noqa: F811
    act_as(conn, {"guest": None, "recipient": world["alice"], "actor": world["bob"]}[who])
    assert refused(conn, "SELECT id FROM public.notifications")
    assert refused(conn, "UPDATE public.notifications SET read_at = now()")
    assert refused(conn, "DELETE FROM public.notifications")
    assert refused(conn, "INSERT INTO public.notifications (user_id, actor_id, kind) VALUES (:a, :b, 'new_follower')",
                   {"a": world["alice"], "b": world["bob"]})


@pytest.mark.parametrize("who", ["guest", "owner"])
def test_clients_cant_touch_notification_preferences(conn, world, who):  # noqa: F811
    as_admin(conn)
    conn.execute(text("INSERT INTO public.notification_preferences (user_id) VALUES (:a)"), {"a": world["alice"]})
    act_as(conn, None if who == "guest" else world["alice"])
    assert refused(conn, "SELECT user_id FROM public.notification_preferences")
    assert refused(conn, "UPDATE public.notification_preferences SET high_five = false")


def test_notifications_go_with_the_post(conn, world, note):  # noqa: F811
    as_admin(conn)
    trail = conn.execute(text("SELECT trail_id FROM public.hike_logs WHERE user_id = :a"), {"a": world["alice"]}).scalar_one()
    log = conn.execute(text("SELECT id FROM public.hike_logs WHERE user_id = :a"), {"a": world["alice"]}).scalar_one()
    post = conn.execute(text("INSERT INTO public.activity_posts (user_id, kind, hike_log_id) VALUES (:a, 'hike', :h) RETURNING id"),
                        {"a": world["alice"], "h": log}).scalar_one()
    conn.execute(text("INSERT INTO public.notifications (user_id, actor_id, kind, post_id) VALUES (:a, :b, 'high_five', :p)"),
                 {"a": world["alice"], "b": world["bob"], "p": post})
    conn.execute(text("DELETE FROM public.hike_logs WHERE id = :h"), {"h": log})
    left = conn.execute(text("SELECT kind FROM public.notifications WHERE user_id = :a"), {"a": world["alice"]}).scalars().all()
    assert left == ["new_follower"] and trail
