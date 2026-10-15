"""Outgoing email.

EMAIL_BACKEND picks the transport:
    sendgrid  production: SendGrid v3 API (SENDGRID_API_KEY, SENDGRID_FROM_EMAIL)
    mailpit   local: the Supabase stack's mail catcher over its HTTP send API
              (MAILPIT_URL, default http://127.0.0.1:44324), so nothing leaves
              the machine and no SMTP port has to be exposed
    console   print instead of sending (the default when unset)
"""

import json
import os
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


class SendGridSender:
    URL = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email

    def send(self, email: Email) -> None:
        content = [{"type": "text/plain", "value": email.text}]
        if email.html:
            content.append({"type": "text/html", "value": email.html})
        _post_json(
            self.URL,
            {
                "personalizations": [{"to": [{"email": email.to}]}],
                "from": {"email": self.from_email, "name": FROM_NAME},
                "subject": email.subject,
                "content": content,
            },
            {"Authorization": f"Bearer {self.api_key}"},
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
    from_email = os.getenv("SENDGRID_FROM_EMAIL") or "alerts@trekly.local"
    if backend == "sendgrid":
        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            raise RuntimeError("EMAIL_BACKEND=sendgrid needs SENDGRID_API_KEY")
        return SendGridSender(api_key, from_email)
    if backend == "mailpit":
        return MailpitSender(os.getenv("MAILPIT_URL", "http://127.0.0.1:44324"), from_email)
    if backend == "console":
        return ConsoleSender()
    raise RuntimeError(f"unknown EMAIL_BACKEND {backend!r}")
