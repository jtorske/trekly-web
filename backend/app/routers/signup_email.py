"""The sign-up email helper: POST /api/auth/signup-email.

Supabase answers a sign-up with an address that already has an account the
same way as a new one (so nobody can test which addresses are registered),
but it sends nothing unless the account is unconfirmed. The person sees
"Check your inbox" and waits for an email that never comes.

The sign-up form calls this after every email sign-up (reason "signup"),
and the "Resend confirmation email" button calls it too (reason "resend").
It looks the address up and sends whichever email helps:

- an unconfirmed account: Supabase's own confirmation email again;
- a confirmed account with a password: "You already have a Trekly account",
  with a "Sign in" button and a "Reset your password" link;
- an account that only signs in with Google: "You signed up with Google",
  with a "Set a password" link (a one-time reset link made with the
  service-role key, or the "Forgot password" page without one);
- no account: nothing.

"Has a password" is the account's password hash, not an "email" identity:
a Google account that sets a password through a reset link keeps only its
Google identity. The Trekly emails come from RESEND_ACCOUNT_FROM_EMAIL.

The answer never says which of those happened. Every accepted request gets
the same 202 and body, and the lookup is the only work done before
answering: emails go out in a background task after the response, so the
response time doesn't depend on the outcome either. A sign-up of a new (or
unconfirmed) address has just had its confirmation sent by Supabase, so a
"signup" request skips the resend when that was under two minutes ago.

Rate limit: 3 accepted requests per address and 10 per client IP in any
hour (a shared IP, such as a campus or office, gets more room). The form
calls this once per sign-up whether or not the address is registered, so a
limit reached sooner for registered addresses can't give them away. A
refused request answers 429, the same for every address, and doesn't count.
Keys are SHA-256 digests; the address and IP themselves aren't stored.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.account_emails import already_registered_email, google_account_email
from app.database import get_db
from app.models.admin import AUTH_IDENTITIES, AUTH_USERS
from app.models.signup_email import SignupEmailRequest
from app.notify import EmailSender, get_account_email_sender
from app.supabase_admin import SupabaseAdmin, SupabaseAdminError, supabase_admin_from_env

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

WINDOW = timedelta(hours=1)
KEEP_FOR = timedelta(days=1)
PER_EMAIL = 3
PER_IP = 10
# Supabase sends the confirmation itself on sign-up; don't send a second.
JUST_SENT = timedelta(minutes=2)
DEFAULT_NEXT = "/profile"  # the frontend's DEFAULT_AFTER_LOGIN

ACCEPTED = {"detail": "If that address needs an email from us, it's on its way."}
TOO_MANY = "We've sent several emails already. Wait an hour, then try again."

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Same rules as safeNextPath in frontend/lib/authLogic.ts.
NEXT_PATTERN = re.compile(r"^/(?![/\\])[^\x00-\x20]*$")
AUTH_PAGES = re.compile(r"^/(login|signup|auth/callback|welcome)(/|\?|$)")


class SignupEmailIn(BaseModel):
    email: str = Field(max_length=254)
    next: str | None = Field(default=None, max_length=500)
    reason: Literal["signup", "resend"] = "resend"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.match(value):
            raise ValueError("Enter a valid email address.")
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def get_client_ip(request: Request) -> str:
    """The caller's address. On Render, uvicorn's --proxy-headers has already
    put the client from X-Forwarded-For here. Overridden in tests."""
    return request.client.host if request.client else "unknown"


def get_signup_supabase_admin() -> SupabaseAdmin | None:
    """Overridden in tests. None without SUPABASE_SERVICE_ROLE_KEY."""
    return supabase_admin_from_env()


def _key(kind: str, value: str) -> str:
    return hashlib.sha256(f"trekly-signup-email:{kind}:{value}".encode()).hexdigest()


def _safe_next(value: str | None) -> str:
    if value and NEXT_PATTERN.match(value) and not AUTH_PAGES.match(value):
        return value
    return DEFAULT_NEXT


def _app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def _links(next_path: str) -> dict[str, str]:
    app_url, carry = _app_url(), f"?next={quote(next_path, safe='')}"
    return {
        "sign_in": f"{app_url}/login{carry}",
        "reset": f"{app_url}/forgot-password{carry}",
        # Where the confirmation link lands, as the form's callbackUrl().
        "confirm": f"{app_url}/auth/callback{carry}",
    }


def _set_password_url(token_hash: str) -> str:
    """A reset link the same shape as the recovery template's: /auth/confirm
    verifies it and sends them to /reset-password."""
    return f"{_app_url()}/auth/confirm?token_hash={quote(token_hash, safe='')}&type=recovery"


def _google_email(email: str, links: dict[str, str], supabase: SupabaseAdmin | None):
    """Built when it's sent: the reset token is made then, not before."""
    if supabase is not None:
        try:
            url, one_time = _set_password_url(supabase.recovery_token_hash(email)), True
        except SupabaseAdminError:
            logger.warning("signup email: no reset link for a Google account; linking Forgot password")
            url, one_time = links["reset"], False
    else:
        url, one_time = links["reset"], False
    return google_account_email(email, sign_in_url=links["sign_in"], set_password_url=url, one_time_link=one_time)


def _refused_until(db: Session, column, key: str, limit: int, since: datetime) -> datetime | None:
    """When this key may ask again, or None if it's under the limit now."""
    times = db.scalars(
        select(SignupEmailRequest.created_at)
        .where(column == key, SignupEmailRequest.created_at > since)
        .order_by(SignupEmailRequest.created_at.desc())
        .limit(limit)
    ).all()
    if len(times) < limit:
        return None
    return _aware(times[-1]) + WINDOW


def _plan(db: Session, payload: SignupEmailIn, now: datetime, sender: EmailSender,
          supabase: SupabaseAdmin | None) -> tuple[str, Callable[[], None]] | None:
    """What to send for this address, as (kind, send), or None."""
    has_password = and_(AUTH_USERS.c.encrypted_password.is_not(None), AUTH_USERS.c.encrypted_password != "")
    user = db.execute(
        select(
            AUTH_USERS.c.id,
            AUTH_USERS.c.email_confirmed_at,
            AUTH_USERS.c.confirmation_sent_at,
            has_password.label("has_password"),
        )
        .where(func.lower(AUTH_USERS.c.email) == payload.email, AUTH_USERS.c.deleted_at.is_(None))
        .limit(1)
    ).first()
    if user is None:
        return None
    providers = set(db.scalars(select(AUTH_IDENTITIES.c.provider).where(AUTH_IDENTITIES.c.user_id == user.id)))
    links = _links(_safe_next(payload.next))

    if user.email_confirmed_at is None:
        if "email" not in providers:
            return None
        sent_at = _aware(user.confirmation_sent_at)
        if payload.reason == "signup" and sent_at and now - sent_at < JUST_SENT:
            return None
        if supabase is None:
            logger.warning("signup email: can't resend a confirmation without SUPABASE_SERVICE_ROLE_KEY")
            return None
        return "confirmation", lambda: supabase.resend_signup_confirmation(payload.email, links["confirm"])

    if user.has_password:
        message = already_registered_email(payload.email, sign_in_url=links["sign_in"], reset_url=links["reset"])
        return "already_registered", lambda: sender.send(message)

    if "google" in providers:
        return "google", lambda: sender.send(_google_email(payload.email, links, supabase))
    return None  # no password and no provider we offer: nothing useful to say


def _deliver(kind: str, send: Callable[[], None]) -> None:
    try:
        send()
    except Exception as error:  # noqa: BLE001  (runs after the response; nothing to tell the caller)
        # The type only: a provider's error text can repeat the address.
        logger.warning("signup email: sending %s failed (%s)", kind, type(error).__name__)


@router.post("/signup-email", status_code=status.HTTP_202_ACCEPTED)
def signup_email(
    payload: SignupEmailIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    client_ip: str = Depends(get_client_ip),
    sender: EmailSender = Depends(get_account_email_sender),
    supabase: SupabaseAdmin | None = Depends(get_signup_supabase_admin),
):
    """Email whoever owns this address whatever helps them sign in. The
    answer is the same whether or not the address has an account."""
    now = _now()
    email_key, ip_key = _key("email", payload.email), _key("ip", client_ip)

    db.execute(delete(SignupEmailRequest).where(SignupEmailRequest.created_at < now - KEEP_FOR))
    since = now - WINDOW
    waits = [
        until for until in (
            _refused_until(db, SignupEmailRequest.email_key, email_key, PER_EMAIL, since),
            _refused_until(db, SignupEmailRequest.ip_key, ip_key, PER_IP, since),
        ) if until
    ]
    if waits:
        db.commit()
        retry_after = max(1, int((max(waits) - now).total_seconds()) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=TOO_MANY,
            headers={"Retry-After": str(retry_after)},
        )
    db.add(SignupEmailRequest(email_key=email_key, ip_key=ip_key, created_at=now))
    db.commit()

    plan = _plan(db, payload, now, sender, supabase)
    if plan:
        background.add_task(_deliver, *plan)
    return ACCEPTED
