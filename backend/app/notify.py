"""Outgoing email.

EMAIL_BACKEND picks the transport:
    resend    production: Resend's email API (RESEND_API_KEY, RESEND_FROM_EMAIL)
    mailpit   local: the Supabase stack's mail catcher over its HTTP send API
              (MAILPIT_URL, default http://127.0.0.1:44324), so nothing leaves
              the machine and no SMTP port has to be exposed
    console   print instead of sending (the default when unset)
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

FROM_NAME = "Trekly"


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: float = 15.0) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as error:
        # The provider says why in the body ("domain is not verified", ...).
        detail = error.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error


def _from_header(from_email: str) -> str:
    """'Trekly <alerts@example.com>' unless the setting already names a sender."""
    return from_email if "<" in from_email else f"{FROM_NAME} <{from_email}>"


class ResendSender:
    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email

    def send(self, email: Email) -> None:
        payload = {
            "from": _from_header(self.from_email),
            "to": [email.to],
            "subject": email.subject,
            "text": email.text,
        }
        if email.html:
            payload["html"] = email.html
        _post_json(
            self.URL,
            payload,
            # Resend's edge refuses urllib's default User-Agent.
            {"Authorization": f"Bearer {self.api_key}", "User-Agent": "trekly-api/1.0"},
        )


class MailpitSender:
    def __init__(self, base_url: str, from_email: str):
        self.base_url = base_url.rstrip("/")
        self.from_email = from_email

    def send(self, email: Email) -> None:
        payload = {
            "From": {"Email": self.from_email, "Name": FROM_NAME},
            "To": [{"Email": email.to}],
            "Subject": email.subject,
            "Text": email.text,
        }
        if email.html:
            payload["HTML"] = email.html
        _post_json(f"{self.base_url}/api/v1/send", payload)


class ConsoleSender:
    def send(self, email: Email) -> None:
        print(f"--- email to {email.to}: {email.subject}\n{email.text}\n---")


def email_sender_from_env() -> EmailSender:
    backend = (os.getenv("EMAIL_BACKEND") or "console").lower()
    from_email = os.getenv("RESEND_FROM_EMAIL") or "alerts@trekly.local"
    if backend == "resend":
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key or not os.getenv("RESEND_FROM_EMAIL"):
            raise RuntimeError("EMAIL_BACKEND=resend needs RESEND_API_KEY and RESEND_FROM_EMAIL")
        return ResendSender(api_key, from_email)
    if backend == "mailpit":
        return MailpitSender(os.getenv("MAILPIT_URL", "http://127.0.0.1:44324"), from_email)
    if backend == "console":
        return ConsoleSender()
    raise RuntimeError(f"unknown EMAIL_BACKEND {backend!r}")


class UnconfiguredSender:
    """Stands in when the email settings are wrong, so every send fails
    loudly (and nothing is marked as emailed) instead of the API crashing."""

    def __init__(self, problem: str):
        self.problem = problem

    def send(self, email: Email) -> None:
        raise RuntimeError(self.problem)


def get_email_sender() -> EmailSender:
    """FastAPI dependency for the API's own emails; overridden in tests."""
    try:
        return email_sender_from_env()
    except RuntimeError as error:
        return UnconfiguredSender(str(error))
