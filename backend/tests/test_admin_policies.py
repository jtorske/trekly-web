"""The admin area against the local Supabase stack (migration e2a7c4f9b1d6).

- Clients (anon, authenticated) can't read or write admin_audit_log, or the
  new report columns.
- The admin router's queries run on real Postgres: auth.users, JSONB
  providers, NULLS LAST sorting and the visibility CASE.
- Only the server can clear a username (the 5d1c0e7a9b42 trigger).

Opt-in and local-only, like test_profile_privacy_policies.py: set
LOCAL_SUPABASE_DB_URL. Every test runs in a transaction that is rolled back.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.routers import admin as admin_router
from tests.test_profile_privacy_policies import DB_URL, act_as, as_admin, conn, engine, refused  # noqa: F401

pytestmark = pytest.mark.skipif(not DB_URL, reason="LOCAL_SUPABASE_DB_URL not set (local Supabase stack only)")


@pytest.fixture
def people(conn):  # noqa: F811
    as_admin(conn)
    ids = {"alice": uuid.uuid4(), "bob": uuid.uuid4()}
    for name, user in ids.items():
        conn.execute(
            text("INSERT INTO auth.users (id, aud, role, email, raw_app_meta_data, created_at) "
                 "VALUES (:id, 'authenticated', 'authenticated', :email, "
                 "'{\"provider\": \"email\", \"providers\": [\"email\", \"google\"]}'::jsonb, now())"),
            {"id": user, "email": f"{name}-{user.hex[:6]}@policy-test.local"},
        )
        conn.execute(text("UPDATE public.profiles SET username = :u WHERE id = :id"),
                     {"u": f"{name}_{user.hex[:8]}", "id": user})
    return ids


def test_clients_cannot_touch_the_audit_log(conn, people):  # noqa: F811
    as_admin(conn)
    conn.execute(text("INSERT INTO public.admin_audit_log (admin_id, action, target_user_id) "
                      "VALUES (:a, 'ban_user', :b)"), {"a": people["alice"], "b": people["bob"]})
    for who in (None, people["alice"]):
        act_as(conn, who)
        assert refused(conn, "SELECT * FROM public.admin_audit_log")
        assert refused(conn, "INSERT INTO public.admin_audit_log (admin_id, action) VALUES (:a, 'ban_user')",
                       {"a": people["alice"]})
        assert refused(conn, "DELETE FROM public.admin_audit_log")
        assert refused(conn, "UPDATE public.profile_reports SET status = 'resolved'")


def test_audit_actions_are_checked(conn, people):  # noqa: F811
    as_admin(conn)
    assert refused(conn, "INSERT INTO public.admin_audit_log (admin_id, action) VALUES (:a, 'delete_user')",
                   {"a": people["alice"]}, reason="admin_audit_log_action_check")


def test_only_the_server_clears_a_username(conn, people):  # noqa: F811
    act_as(conn, people["bob"])
    assert refused(conn, "UPDATE public.profiles SET username = NULL WHERE id = :id", {"id": people["bob"]},
                   reason="username_required")
    as_admin(conn)  # the backend's own connection: no request claims at all
    conn.execute(text("SELECT set_config('request.jwt.claims', '', true)"))
    conn.execute(text("UPDATE public.profiles SET username = NULL WHERE id = :id"), {"id": people["bob"]})
    assert conn.execute(text("SELECT username FROM public.profiles WHERE id = :id"),
                        {"id": people["bob"]}).scalar() is None


def test_admin_queries_run_on_postgres(conn, people):  # noqa: F811
    as_admin(conn)
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    alice = people["alice"]
    page = admin_router.list_users(db=db, q=str(alice), sort="hikes", direction="desc", filter="all",
                                   page=1, per_page=25)
    [row] = page.items
    assert row.providers == ["email", "google"] and row.visibility in ("public", "private")
    for sort in admin_router.SORTS:
        admin_router.list_users(db=db, q="", sort=sort, direction="asc", filter="public", page=1, per_page=5)
    admin_router.list_users(db=db, q="", sort="joined", direction="desc", filter="banned", page=1, per_page=5)
    overview = admin_router.overview(db=db)
    assert overview.users_total >= 2 and len(overview.signups_by_week) == admin_router.SIGNUP_WEEKS
    detail = admin_router.user_detail(alice, db=db)
    assert detail.id == alice and detail.joined_at.tzinfo is not None
    me = CurrentUser(id=people["bob"], email=None)
    admin_router.clear_username(alice, admin_router.ReasonIn(reason="test"), admin=me, db=db)
    assert db.execute(text("SELECT action, details->>'reason' FROM public.admin_audit_log WHERE target_user_id = :id"),
                      {"id": alice}).one() == ("clear_username", "test")
    admin_router.list_reports(db=db, status_filter="all", page=1, per_page=5)
    admin_router.list_audit(db=db, page=1, per_page=5)
    db.close()
