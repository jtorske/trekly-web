"""The admin area (/api/admin/...): access, reads, and audited actions.

- Every admin route answers 403 to a signed-in non-admin and 401 to a guest,
  found by sweeping the app's routes, so a new route can't slip past.
- Every action writes exactly one admin_audit_log row (who, what, when, on
  whom); a refused or failed action writes none.
- Supabase admin calls never put the service-role key in a response, even
  when the server echoes the request back.
"""

import io
import logging
import re
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from app.main import app
from app.models.account import Profile
from app.models.admin import AUTH_USERS, AdminAuditLog
from app.models.availability import AvailabilityAlert, JobLock
from app.models.catalog import CatalogCategory
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileReport, ProfileSettings
from app.models.user_gear import UserGearItem
from app.routers.admin import get_supabase_admin
from app.supabase_admin import SupabaseAdmin, SupabaseAdminError, supabase_admin_from_env
from tests.test_availability import world  # noqa: F401  (fixture)

ADMIN = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
OTHER_ADMIN = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002")
SECRET = f"service-role-{uuid.uuid4().hex}"
NOW = datetime.now(timezone.utc)


class FakeSupabase:
    """Records calls; `fail` makes the next call fail like a 500."""

    def __init__(self):
        self.calls = []
        self.fail = False

    def _do(self, *call):
        if self.fail:
            raise SupabaseAdminError("Supabase didn't accept that (HTTP 500).")
        self.calls.append(call)

    def ban(self, user_id):
        self._do("ban", user_id)

    def unban(self, user_id):
        self._do("unban", user_id)

    def send_password_reset(self, email, redirect_to):
        self._do("reset", email, redirect_to)


@pytest.fixture
def supabase():
    fake = FakeSupabase()
    app.dependency_overrides[get_supabase_admin] = lambda: fake
    return fake


@pytest.fixture
def admin(monkeypatch, auth_headers):
    monkeypatch.setenv("ADMIN_USER_IDS", f"{ADMIN}, {OTHER_ADMIN}")
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    return auth_headers(ADMIN)


def add_user(db, *, email, username=None, display_name=None, created_at=NOW, providers=("email",),
             last_sign_in_at=None, banned_until=None, private=False, user_id=None):
    user_id = user_id or uuid.uuid4()
    db.execute(insert(AUTH_USERS).values(
        id=user_id, email=email, created_at=created_at, last_sign_in_at=last_sign_in_at,
        banned_until=banned_until, raw_app_meta_data={"provider": providers[0], "providers": list(providers)},
    ))
    db.add(Profile(id=user_id, username=username, display_name=display_name))
    db.add(ProfileSettings(user_id=user_id, is_private=private))
    db.commit()
    return user_id


@pytest.fixture
def users(session_factory, world):  # noqa: F811
    db = session_factory()
    ids = {
        "admin": add_user(db, email="admin@example.com", username="jordan", display_name="Jordan",
                          user_id=ADMIN, created_at=NOW - timedelta(days=120)),
        "alice": add_user(db, email="alice@example.com", username="alice", display_name="Alice Abbott",
                          providers=("email", "google"), created_at=NOW - timedelta(days=10),
                          last_sign_in_at=NOW - timedelta(hours=2)),
        "bob": add_user(db, email="bob@example.com", username="bob_b", display_name="Bob", private=True,
                        created_at=NOW - timedelta(days=3)),
        "carol": add_user(db, email="carol@example.com", created_at=NOW - timedelta(days=1)),
    }
    category = db.scalar(select(CatalogCategory.id).limit(1))
    db.add_all([
        HikeLog(user_id=ids["alice"], trail_id=world["trail"], hiked_on=date(2026, 8, 14), note="Larches!"),
        UserGearItem(user_id=ids["alice"], custom_name="Tent", category_id=category),
        UserGearItem(user_id=ids["alice"], custom_name="Stove", category_id=category),
        UserGearItem(user_id=ids["bob"], custom_name="Pack", category_id=category),
        AvailabilityAlert(user_id=ids["alice"], email="alice@example.com", site_id=world["evelyn"],
                          trail_id=world["trail"], start_date=date(2026, 10, 20), nights=1, party_size=2),
        JobLock(name="alert_poller", last_started_at=NOW - timedelta(minutes=12),
                last_finished_at=NOW - timedelta(minutes=11), last_result="checked 1, notified 0"),
    ])
    db.commit()
    db.close()
    return ids


@pytest.fixture
def report(session_factory, users, world):  # noqa: F811
    db = session_factory()
    row = ProfileReport(reporter_id=users["bob"], profile_id=users["alice"], reason="spam",
                        details="Selling things", trail_id=world["trail"], created_at=NOW)
    db.add(row)
    db.commit()
    report_id = row.id
    db.close()
    return report_id


def audit_rows(session_factory):
    db = session_factory()
    rows = db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at)).all()
    db.close()
    return rows


# ----------------------------------------------------------------- access


def admin_requests():
    """(method, path) for every admin route, path parameters filled in."""
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/admin"):
            path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route.path)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, path


def test_the_sweep_covers_the_admin_area():
    paths = [path for _, path in admin_requests()]
    assert len(paths) >= 20
    for prefix in ("/api/admin/overview", "/api/admin/users", "/api/admin/reports", "/api/admin/audit",
                   "/api/admin/trail-photos", "/api/admin/profiles"):
        assert any(p.startswith(prefix) for p in paths), prefix


def test_non_admins_get_403_on_every_admin_endpoint(client, auth_headers, monkeypatch, users, supabase):
    monkeypatch.setenv("ADMIN_USER_IDS", str(ADMIN))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    signed_in = auth_headers(users["alice"])
    for method, path in admin_requests():
        response = client.request(method, path, headers=signed_in, json={})
        assert response.status_code == 403, f"{method} {path} gave {response.status_code}"
        guest = client.request(method, path, json={})
        assert guest.status_code == 401, f"{method} {path} gave {guest.status_code} to a guest"
    assert supabase.calls == []


def test_an_empty_admin_list_lets_nobody_in(client, auth_headers, monkeypatch, users):
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS", raising=False)
    assert client.get("/api/admin/me", headers=auth_headers(ADMIN)).status_code == 403


def test_photo_admins_are_admins_and_admins_can_review_photos(client, auth_headers, monkeypatch):
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.setenv("PHOTO_ADMIN_USER_IDS", str(ADMIN))
    assert client.get("/api/admin/me", headers=auth_headers(ADMIN)).status_code == 200
    monkeypatch.setenv("ADMIN_USER_IDS", str(OTHER_ADMIN))
    monkeypatch.delenv("PHOTO_ADMIN_USER_IDS")
    assert client.get("/api/admin/trail-photos/me", headers=auth_headers(OTHER_ADMIN)).status_code == 200
    assert client.get("/api/admin/trail-photos/me", headers=auth_headers(ADMIN)).status_code == 403


def test_the_profile_says_whether_you_are_an_admin(client, admin, auth_headers, users):
    assert client.get("/api/me/profile", headers=admin).json()["is_admin"] is True
    assert client.get("/api/me/profile", headers=auth_headers(users["alice"])).json()["is_admin"] is False


# ----------------------------------------------------------------- reads


def test_overview(client, admin, users, report):
    body = client.get("/api/admin/overview", headers=admin).json()
    assert body["users_total"] == 4
    assert body["hikes_total"] == 1
    assert body["active_alerts"] == 1
    assert body["open_reports"] == 1
    assert len(body["signups_by_week"]) == 12
    assert sum(week["count"] for week in body["signups_by_week"]) == 3  # the admin joined before the 12 weeks
    assert body["poller"]["last_result"] == "checked 1, notified 0"
    assert body["poller"]["running"] is False


def test_users_table(client, admin, users):
    page = client.get("/api/admin/users", headers=admin).json()
    assert page["total"] == 4
    assert [u["email"] for u in page["items"]] == [
        "carol@example.com", "bob@example.com", "alice@example.com", "admin@example.com"
    ]
    alice = next(u for u in page["items"] if u["username"] == "alice")
    assert alice["providers"] == ["email", "google"]
    assert (alice["hikes"], alice["gear"], alice["alerts"]) == (1, 2, 1)
    assert alice["visibility"] == "public" and alice["banned"] is False
    by_name = {u["email"]: u for u in page["items"]}
    assert by_name["bob@example.com"]["visibility"] == "private"
    assert by_name["carol@example.com"]["visibility"] == "no_username"
    assert by_name["admin@example.com"]["is_admin"] is True


def test_users_search_sort_filter_and_pages(client, admin, users):
    def emails(**params):
        return [u["email"] for u in client.get("/api/admin/users", params=params, headers=admin).json()["items"]]

    assert emails(q="ALICE") == ["alice@example.com"]
    assert emails(q="@bob_b") == ["bob@example.com"]
    assert emails(q="abbott") == ["alice@example.com"]
    assert emails(q=str(users["carol"])) == ["carol@example.com"]
    assert emails(q="%") == []  # LIKE wildcards are matched literally
    assert emails(sort="gear", dir="desc")[:2] == ["alice@example.com", "bob@example.com"]
    assert emails(sort="email", dir="asc")[0] == "admin@example.com"
    assert emails(sort="last_sign_in", dir="desc")[0] == "alice@example.com"  # never-signed-in last
    assert emails(filter="private") == ["bob@example.com"]
    first = client.get("/api/admin/users", params={"per_page": 3, "page": 1}, headers=admin).json()
    second = client.get("/api/admin/users", params={"per_page": 3, "page": 2}, headers=admin).json()
    assert first["total"] == second["total"] == 4
    assert len(first["items"]) == 3 and len(second["items"]) == 1
    assert client.get("/api/admin/users", params={"sort": "password"}, headers=admin).status_code == 422
    assert client.get("/api/admin/users", params={"per_page": 1000}, headers=admin).status_code == 422


def test_user_detail(client, admin, users, report, world):  # noqa: F811
    body = client.get(f"/api/admin/users/{users['alice']}", headers=admin).json()
    assert body["email"] == "alice@example.com"
    assert [h["trail"]["name"] for h in body["hikes_list"]] == ["Skyline Trail"]
    assert body["alerts_list"][0]["site_name"] == "Evelyn Creek"
    assert body["alerts_list"][0]["status"] == "active"
    [about] = body["reports_about"]
    assert about["kind"] == "trip_note" and about["note"] == "Larches!"
    assert about["reporter"]["username"] == "bob_b"
    assert client.get(f"/api/admin/users/{users['bob']}", headers=admin).json()["reports_filed"] == 1
    assert client.get(f"/api/admin/users/{uuid.uuid4()}", headers=admin).status_code == 404


def test_reports_list_and_filter(client, admin, users, report):
    [item] = client.get("/api/admin/reports", headers=admin).json()["items"]
    assert item["id"] == str(report)
    assert item["kind"] == "trip_note" and item["trail"]["name"] == "Skyline Trail"
    assert item["reported"]["username"] == "alice" and item["status"] == "open"
    assert client.get("/api/admin/reports", params={"status": "resolved"}, headers=admin).json()["total"] == 0
    assert client.get("/api/admin/reports", params={"status": "all"}, headers=admin).json()["total"] == 1


# ----------------------------------------------------------------- actions are audited


def test_hide_and_unhide_are_audited(client, admin, users, session_factory):
    alice = users["alice"]
    assert client.post(f"/api/admin/users/{alice}/hide", json={"reason": " Spam "}, headers=admin).status_code == 200
    assert client.post(f"/api/admin/users/{alice}/hide", json={}, headers=admin).status_code == 409
    assert client.get("/api/profiles/alice").status_code == 404
    row = client.get(f"/api/admin/users/{alice}", headers=admin).json()
    assert row["visibility"] == "hidden" and row["hidden_reason"] == "Spam"
    assert client.post(f"/api/admin/users/{alice}/unhide", headers=admin).status_code == 200
    assert client.post(f"/api/admin/users/{alice}/unhide", headers=admin).status_code == 409

    rows = audit_rows(session_factory)
    assert [(r.action, r.admin_id, r.target_user_id) for r in rows] == [
        ("hide_profile", ADMIN, alice), ("unhide_profile", ADMIN, alice)
    ]
    assert rows[0].details == {"reason": "Spam", "username": "alice"}
    assert rows[0].created_at is not None


def test_clear_username_is_audited_and_asks_them_for_a_new_one(client, admin, users, session_factory, auth_headers):
    bob = users["bob"]
    response = client.post(f"/api/admin/users/{bob}/clear-username", json={"reason": "Offensive"}, headers=admin)
    assert response.status_code == 200
    db = session_factory()
    assert db.get(Profile, bob).username is None
    db.close()
    # The app's username gate shows when the profile has no username.
    assert client.get("/api/me/profile", headers=auth_headers(bob)).json()["username"] is None
    assert client.post(f"/api/admin/users/{bob}/clear-username", json={}, headers=admin).status_code == 409
    [row] = audit_rows(session_factory)
    assert (row.action, row.target_user_id, row.details) == (
        "clear_username", bob, {"username": "bob_b", "reason": "Offensive"}
    )


def test_ban_unban_and_password_reset_go_through_supabase_and_are_audited(
    client, admin, users, supabase, session_factory, monkeypatch
):
    monkeypatch.setenv("APP_URL", "https://trekly.example")
    alice = users["alice"]
    assert client.post(f"/api/admin/users/{alice}/ban", json={"reason": "Abuse"}, headers=admin).status_code == 200
    assert client.post(f"/api/admin/users/{alice}/unban", headers=admin).status_code == 200
    assert client.post(f"/api/admin/users/{alice}/password-reset", headers=admin).status_code == 200
    assert supabase.calls == [
        ("ban", alice), ("unban", alice),
        ("reset", "alice@example.com", "https://trekly.example/auth/callback?next=%2Freset-password"),
    ]
    assert [(r.action, r.target_user_id) for r in audit_rows(session_factory)] == [
        ("ban_user", alice), ("unban_user", alice), ("send_password_reset", alice)
    ]


def test_banned_users_show_as_banned(client, admin, session_factory, users):
    db = session_factory()
    add_user(db, email="dan@example.com", username="dan", banned_until=NOW + timedelta(days=36500))
    db.close()
    [dan] = client.get("/api/admin/users", params={"filter": "banned"}, headers=admin).json()["items"]
    assert dan["email"] == "dan@example.com" and dan["banned"] is True


def test_failed_or_refused_actions_write_no_audit_row(client, admin, users, supabase, session_factory):
    db = session_factory()
    add_user(db, email="sam@example.com", username="sam", user_id=OTHER_ADMIN)
    db.close()
    supabase.fail = True
    response = client.post(f"/api/admin/users/{users['alice']}/ban", json={}, headers=admin)
    assert response.status_code == 502
    supabase.fail = False
    assert client.post(f"/api/admin/users/{ADMIN}/ban", json={}, headers=admin).status_code == 422
    assert client.post(f"/api/admin/users/{OTHER_ADMIN}/ban", json={}, headers=admin).status_code == 422
    assert client.post(f"/api/admin/users/{uuid.uuid4()}/hide", json={}, headers=admin).status_code == 404
    assert supabase.calls == []
    assert audit_rows(session_factory) == []


def test_reports_resolve_and_reopen_are_audited(client, admin, users, report, session_factory):
    resolved = client.patch(f"/api/admin/reports/{report}", json={"status": "resolved"}, headers=admin).json()
    assert resolved["status"] == "resolved" and resolved["resolved_by"]["username"] == "jordan"
    # Setting the same status again changes nothing and isn't logged twice.
    client.patch(f"/api/admin/reports/{report}", json={"status": "resolved"}, headers=admin)
    reopened = client.patch(f"/api/admin/reports/{report}", json={"status": "open"}, headers=admin).json()
    assert reopened["status"] == "open" and reopened["resolved_at"] is None
    assert [(r.action, r.target_report_id, r.target_user_id) for r in audit_rows(session_factory)] == [
        ("resolve_report", report, users["alice"]), ("reopen_report", report, users["alice"])
    ]
    audit = client.get("/api/admin/audit", headers=admin).json()
    assert audit["total"] == 2 and audit["items"][0]["admin"]["username"] == "jordan"


def test_the_older_profile_moderation_routes_are_audited_too(client, admin, users, session_factory):
    assert client.put("/api/admin/profiles/alice/hidden", json={"reason": "Spam"}, headers=admin).status_code == 200
    assert client.delete("/api/admin/profiles/alice/hidden", headers=admin).status_code == 204
    assert [r.action for r in audit_rows(session_factory)] == ["hide_profile", "unhide_profile"]


def test_a_trip_note_report_remembers_its_trail(client, users, world, session_factory, auth_headers):  # noqa: F811
    from tests.test_public_profiles import Outbox
    from app.routers.public_profiles import get_email_sender

    db = session_factory()
    settings = db.get(ProfileSettings, users["alice"])
    settings.show_in_community = True
    db.commit()
    db.close()
    app.dependency_overrides[get_email_sender] = lambda: Outbox()
    response = client.post("/api/profiles/alice/report", json={"reason": "spam", "trail_id": str(world["trail"])},
                           headers=auth_headers(users["bob"]))
    assert response.status_code == 202
    db = session_factory()
    report = db.scalar(select(ProfileReport))
    assert report.trail_id == world["trail"] and report.status == "open"
    db.close()


def test_the_moderation_table_is_untouched_by_reads(client, admin, users, session_factory):
    client.get("/api/admin/users", headers=admin)
    client.get(f"/api/admin/users/{users['alice']}", headers=admin)
    db = session_factory()
    assert db.scalars(select(ProfileModeration)).all() == []
    db.close()
    assert audit_rows(session_factory) == []


# ----------------------------------------------------------------- the service-role key


class EchoNetwork:
    """A Supabase that fails by repeating the request's headers (the key) back."""

    def __init__(self, mode):
        self.mode = mode
        self.calls = 0

    def urlopen(self, request, *args, **kwargs):
        self.calls += 1
        echoed = " ".join(f"{k}: {v}" for k, v in request.header_items())
        if self.mode == "http_error":
            raise urllib.error.HTTPError(request.full_url, 500, f"Internal error: {echoed}", {"X-Echo": echoed},
                                         io.BytesIO(echoed.encode()))
        if self.mode == "url_error":
            raise urllib.error.URLError(f"connection reset while sending {echoed}")
        return io.BytesIO(echoed.encode())


@pytest.mark.parametrize("mode", ["http_error", "url_error", "ok"])
def test_account_actions_never_leak_the_service_role_key(
    client, admin, users, monkeypatch, caplog, capsys, mode
):
    network = EchoNetwork(mode)
    monkeypatch.setattr(urllib.request, "urlopen", network.urlopen)
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    caplog.set_level(logging.DEBUG)
    alice = users["alice"]
    with TestClient(app, raise_server_exceptions=False) as raw:
        for path in ("ban", "unban", "password-reset"):
            response = raw.post(f"/api/admin/users/{alice}/{path}", json={} if path == "ban" else None, headers=admin)
            assert response.status_code == (200 if mode == "ok" else 502), path
            assert SECRET not in response.text and SECRET not in str(dict(response.headers))
        for method, path in admin_requests():
            response = raw.request(method, path, headers=admin, json={})
            assert SECRET not in response.text and SECRET not in str(dict(response.headers))
    assert network.calls == 3
    assert SECRET not in caplog.text
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_the_admin_client_never_shows_the_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    client = supabase_admin_from_env()
    assert isinstance(client, SupabaseAdmin)
    assert SECRET not in repr(client) and SECRET not in str(vars(client))
    monkeypatch.setattr(urllib.request, "urlopen", EchoNetwork("http_error").urlopen)
    with pytest.raises(SupabaseAdminError) as raised:
        client.ban(uuid.uuid4())
    assert SECRET not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_account_actions_are_unavailable_without_the_key(client, admin, users, monkeypatch, session_factory):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    response = client.post(f"/api/admin/users/{users['alice']}/ban", json={}, headers=admin)
    assert response.status_code == 503
    assert audit_rows(session_factory) == []
