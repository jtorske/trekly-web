"""The sign-up email helper (POST /api/auth/signup-email).

- Each kind of existing account gets the email that helps it, and only that
  one: a password account gets "You already have a Trekly account", an
  unconfirmed one gets Supabase's confirmation again, a Google-only one gets
  "You signed up with Google", and an unknown address gets nothing.
- The response is byte-for-byte the same in every case (status, headers,
  body), it never repeats the address, and a refused request is the same
  429 for registered and unregistered addresses alike.
- The rate limit: 3 per address and 10 per IP in an hour; refusals don't
  count; old rows are cleared; only digests are stored.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.main import app
from app.models.admin import AUTH_IDENTITIES, AUTH_USERS
from app.models.signup_email import SignupEmailRequest
from app.notify import get_email_sender
from app.routers import signup_email
from app.routers.signup_email import ACCEPTED, TOO_MANY, get_client_ip, get_signup_supabase_admin
from app.supabase_admin import SupabaseAdminError
from tests.test_public_profiles import Outbox

NOW = datetime.now(timezone.utc)
URL = "/api/auth/signup-email"

CONFIRMED = "confirmed@example.com"
UNCONFIRMED = "unconfirmed@example.com"
GOOGLE = "google.only@example.com"
BOTH = "both@example.com"
NOBODY = "nobody@example.com"
ALL_CASES = (CONFIRMED, UNCONFIRMED, GOOGLE, NOBODY)


class FakeSupabase:
    def __init__(self):
        self.resent: list[tuple[str, str]] = []
        self.fail = False

    def resend_signup_confirmation(self, email, redirect_to):
        if self.fail:
            raise SupabaseAdminError("Supabase didn't accept that (HTTP 500).")
        self.resent.append((email, redirect_to))


class Caller:
    """Which IP the request appears to come from."""

    ip = "203.0.113.7"


@pytest.fixture
def outbox():
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def supabase():
    fake = FakeSupabase()
    app.dependency_overrides[get_signup_supabase_admin] = lambda: fake
    return fake


@pytest.fixture
def caller():
    current = Caller()
    app.dependency_overrides[get_client_ip] = lambda: current.ip
    return current


@pytest.fixture(autouse=True)
def app_url(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://trekly.example")


def add_account(db, email, *, providers=("email",), confirmed=True, confirmation_sent_at=None, deleted=False):
    user_id = uuid.uuid4()
    db.execute(insert(AUTH_USERS).values(
        id=user_id, email=email, created_at=NOW - timedelta(days=30),
        email_confirmed_at=NOW - timedelta(days=30) if confirmed else None,
        confirmation_sent_at=confirmation_sent_at,
        deleted_at=NOW if deleted else None,
    ))
    for provider in providers:
        db.execute(insert(AUTH_IDENTITIES).values(id=uuid.uuid4(), user_id=user_id, provider=provider))
    db.commit()
    return user_id


@pytest.fixture
def accounts(session_factory):
    db = session_factory()
    add_account(db, CONFIRMED)
    # Confirmation sent yesterday, never clicked.
    add_account(db, UNCONFIRMED, confirmed=False, confirmation_sent_at=NOW - timedelta(days=1))
    add_account(db, GOOGLE, providers=("google",))
    add_account(db, BOTH, providers=("email", "google"))
    db.close()


@pytest.fixture
def ready(client, accounts, outbox, supabase, caller):
    return client


def ask(client, email, **extra):
    return client.post(URL, json={"email": email, **extra})


def fingerprint(response):
    headers = tuple(sorted((k, v) for k, v in response.headers.items() if k.lower() != "date"))
    return response.status_code, headers, response.content


# ----------------------------------------------------------------- the three cases


def test_a_confirmed_password_account_gets_the_already_registered_email(ready, outbox, supabase):
    response = ask(ready, CONFIRMED, next="/trails?id=7")
    assert response.status_code == 202
    assert supabase.resent == []
    [email] = outbox.sent
    assert email.to == CONFIRMED
    assert email.subject == "You already have a Trekly account"
    sign_in = "https://trekly.example/login?next=%2Ftrails%3Fid%3D7"
    reset = "https://trekly.example/forgot-password?next=%2Ftrails%3Fid%3D7"
    for body in (email.text, email.html):
        assert "Sign in" in body and sign_in in body.replace("&amp;", "&")
        assert reset in body.replace("&amp;", "&")
    assert "Reset your password" in email.html
    assert f'href="{sign_in}"' in email.html


def test_an_unconfirmed_account_gets_supabases_confirmation_again(ready, outbox, supabase):
    assert ask(ready, UNCONFIRMED, next="/gear").status_code == 202
    assert outbox.sent == []
    assert supabase.resent == [(UNCONFIRMED, "https://trekly.example/auth/callback?next=%2Fgear")]


def test_a_google_only_account_is_told_to_continue_with_google(ready, outbox, supabase):
    assert ask(ready, GOOGLE).status_code == 202
    assert supabase.resent == []
    [email] = outbox.sent
    assert email.to == GOOGLE
    for body in (email.text, email.html):
        assert "You signed up with Google" in body
    assert "Use 'Continue with Google' to sign in" in email.text
    assert "<strong>Continue with Google</strong> to sign in" in email.html
    assert "https://trekly.example/login?next=%2Fprofile" in email.text


def test_an_account_with_a_password_and_google_is_a_password_account(ready, outbox):
    ask(ready, BOTH)
    assert [e.subject for e in outbox.sent] == ["You already have a Trekly account"]


def test_an_unknown_address_gets_nothing(ready, outbox, supabase):
    assert ask(ready, NOBODY).status_code == 202
    assert outbox.sent == [] and supabase.resent == []


def test_a_deleted_account_counts_as_no_account(ready, session_factory, outbox):
    db = session_factory()
    add_account(db, "gone@example.com", deleted=True)
    db.close()
    ask(ready, "gone@example.com")
    assert outbox.sent == []


def test_the_address_is_matched_without_case_or_spaces(ready, outbox):
    ask(ready, "  Confirmed@Example.COM ")
    assert [e.to for e in outbox.sent] == [CONFIRMED]


def test_right_after_sign_up_supabases_own_confirmation_isnt_doubled(ready, session_factory, supabase):
    db = session_factory()
    add_account(db, "fresh@example.com", confirmed=False, confirmation_sent_at=NOW - timedelta(seconds=20))
    db.close()
    ask(ready, "fresh@example.com", reason="signup")
    assert supabase.resent == []
    # The button asks on purpose, so it always resends.
    ask(ready, "fresh@example.com", reason="resend")
    assert [email for email, _ in supabase.resent] == ["fresh@example.com"]


def test_sign_up_with_an_old_unconfirmed_account_resends(ready, supabase):
    ask(ready, UNCONFIRMED, reason="signup")
    assert [email for email, _ in supabase.resent] == [UNCONFIRMED]


def test_an_unsafe_next_falls_back_to_the_profile(ready, outbox, session_factory):
    for bad in ("//evil.example", "https://evil.example", "/\\evil", "/login", "/auth/callback?next=/x"):
        outbox.sent.clear()
        ask(ready, CONFIRMED, next=bad)
        assert "login?next=%2Fprofile" in outbox.sent[0].text, bad
        db = session_factory()  # stay under the per-address limit
        db.query(SignupEmailRequest).delete()
        db.commit()
        db.close()


# ----------------------------------------------------------------- nothing gives an account away


def test_every_case_gets_the_identical_response(ready):
    responses = [fingerprint(ask(ready, email)) for email in ALL_CASES]
    assert responses[0][0] == 202
    assert responses[0][2] == b'{"detail":"If that address needs an email from us, it\'s on its way."}'
    assert all(r == responses[0] for r in responses)


def test_the_response_is_the_same_for_both_reasons_too(ready):
    responses = {fingerprint(ask(ready, email, reason=reason)) for email in ALL_CASES for reason in ("signup", "resend")}
    assert len(responses) == 1


def test_a_failed_send_doesnt_change_the_response(ready, outbox, supabase, caplog):
    healthy = fingerprint(ask(ready, NOBODY))
    outbox.fail = supabase.fail = True
    with caplog.at_level(logging.WARNING):
        assert fingerprint(ask(ready, CONFIRMED)) == healthy
        assert fingerprint(ask(ready, UNCONFIRMED)) == healthy
    # Logged without the address.
    assert "sending already_registered failed" in caplog.text
    assert CONFIRMED not in caplog.text and UNCONFIRMED not in caplog.text


def test_without_a_service_role_key_the_response_is_still_the_same(ready, supabase):
    healthy = fingerprint(ask(ready, NOBODY))
    app.dependency_overrides[get_signup_supabase_admin] = lambda: None
    assert fingerprint(ask(ready, UNCONFIRMED)) == healthy


def test_no_response_mentions_the_address_or_the_account(ready, caller):
    bodies = []
    for email in ALL_CASES:
        for _ in range(4):  # three accepted, then the 429
            bodies.append(ask(ready, email).text.lower())
        caller.ip = f"198.51.100.{len(bodies)}"
    for body in bodies:
        assert "@" not in body
        for word in ("exist", "registered", "google", "confirm", "account", "found", "unknown", "password"):
            assert word not in body, (word, body)


def test_the_email_goes_out_after_the_response(ready, outbox, monkeypatch):
    """Sending is a background task, so it can't slow the answer down for
    registered addresses."""
    from fastapi import BackgroundTasks

    scheduled = []
    real_add = BackgroundTasks.add_task

    def spy(self, func, *args, **kwargs):
        scheduled.append(func)
        return real_add(self, func, *args, **kwargs)

    monkeypatch.setattr(BackgroundTasks, "add_task", spy)
    ask(ready, CONFIRMED)
    assert scheduled == [signup_email._deliver]
    assert len(outbox.sent) == 1


def test_bad_input_is_refused_the_same_way_for_everyone(ready):
    for bad in ("not-an-email", "a@b", "x" * 250 + "@example.com"):
        assert ask(ready, bad).status_code == 422
    assert ready.post(URL, json={"email": CONFIRMED, "reason": "other"}).status_code == 422


# ----------------------------------------------------------------- the rate limit


def test_three_per_address_per_hour_then_429(ready, outbox, caller):
    for i in range(3):
        caller.ip = f"192.0.2.{i}"
        assert ask(ready, CONFIRMED).status_code == 202
    caller.ip = "192.0.2.99"
    refused = ask(ready, CONFIRMED)
    assert refused.status_code == 429
    assert refused.json() == {"detail": TOO_MANY}
    assert 3500 <= int(refused.headers["Retry-After"]) <= 3601
    assert len(outbox.sent) == 3


def test_the_limit_is_per_address_case_insensitively(ready, caller):
    for i, email in enumerate((CONFIRMED, CONFIRMED.upper(), f" {CONFIRMED}")):
        caller.ip = f"192.0.2.{i}"
        assert ask(ready, email).status_code == 202
    assert ask(ready, "Confirmed@example.com").status_code == 429


def test_ten_per_ip_per_hour_then_429(ready, outbox, caller):
    for i in range(10):
        assert ask(ready, f"someone{i}@example.com").status_code == 202
    assert ask(ready, CONFIRMED).status_code == 429
    assert outbox.sent == []
    caller.ip = "198.51.100.1"
    assert ask(ready, CONFIRMED).status_code == 202
    assert len(outbox.sent) == 1


def test_the_429_is_identical_for_registered_and_unknown_addresses(ready, caller):
    refusals = []
    for n, email in enumerate(ALL_CASES):
        caller.ip = f"198.51.100.{n}"
        for _ in range(3):
            ask(ready, email)
        refusals.append(ask(ready, email))
    assert all(r.status_code == 429 for r in refusals)
    shapes = {(r.status_code, r.content) for r in refusals}
    assert len(shapes) == 1


def test_refused_requests_dont_count_or_send(ready, outbox, session_factory, caller):
    for _ in range(3):
        ask(ready, CONFIRMED)
    for _ in range(5):
        assert ask(ready, CONFIRMED).status_code == 429
    assert len(outbox.sent) == 3
    db = session_factory()
    assert db.query(SignupEmailRequest).count() == 3
    db.close()


def test_the_limit_resets_after_an_hour(ready, session_factory, outbox):
    for _ in range(3):
        ask(ready, CONFIRMED)
    db = session_factory()
    for row in db.scalars(select(SignupEmailRequest)):
        row.created_at = NOW - timedelta(minutes=61)
    db.commit()
    db.close()
    assert ask(ready, CONFIRMED).status_code == 202
    assert len(outbox.sent) == 4


def test_rows_older_than_a_day_are_cleared(ready, session_factory):
    db = session_factory()
    db.add(SignupEmailRequest(email_key="old", ip_key="old", created_at=NOW - timedelta(days=2)))
    db.commit()
    db.close()
    ask(ready, NOBODY)
    db = session_factory()
    assert [r.email_key for r in db.scalars(select(SignupEmailRequest))] != ["old"]
    assert db.query(SignupEmailRequest).filter_by(email_key="old").count() == 0
    db.close()


def test_only_digests_are_stored(ready, session_factory, caller):
    ask(ready, CONFIRMED)
    db = session_factory()
    [row] = db.scalars(select(SignupEmailRequest)).all()
    db.close()
    for value in (row.email_key, row.ip_key):
        assert len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    assert "confirmed" not in row.email_key and caller.ip not in row.ip_key
