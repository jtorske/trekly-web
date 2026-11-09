"""Emails about someone's own Trekly account, sent by the sign-up email
helper (app/routers/signup_email.py) when someone signs up with an address
that already has an account:

- already_registered_email: the account has a password. A "Sign in" button
  and a "Reset your password" link.
- google_account_email: the account only signs in with Google.

Same look as the alert emails (app/alert_emails.py): wordmark, a white
card, the rust button, inline styles, and nothing loaded from a server.
"""

from __future__ import annotations

from html import escape

from app.alert_emails import BUTTON, CREAM, INK, MUTED, OLIVE
from app.notify import Email

FOOTER = (
    "You're getting this because someone tried to create a Trekly account with this address. "
    "If that wasn't you, you can ignore this email: nothing has changed."
)


def _html(*, preheader: str, heading: str, paragraphs: list[str], button: tuple[str, str],
          after: list[str]) -> str:
    """`paragraphs` and `after` are already-escaped HTML."""
    label, url = button
    body = "".join(
        f'<tr><td style="color:{INK};font-size:15px;line-height:1.55;padding:0 0 14px">{p}</td></tr>'
        for p in paragraphs
    )
    after_html = "".join(
        f'<tr><td style="padding:14px 0 0;color:{INK};font-size:15px;line-height:1.55">{line}</td></tr>'
        for line in after
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{CREAM};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{INK}">
<div style="display:none;max-height:0;overflow:hidden">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM}">
<tr><td align="center" style="padding:28px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">
<tr><td style="padding:0 0 18px;font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:700;color:{INK}">Trekly</td></tr>
<tr><td style="background:#ffffff;border:1px solid #e3e0c8;border-radius:16px;padding:26px 24px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="font-family:Georgia,'Times New Roman',serif;font-size:24px;line-height:1.25;font-weight:600;color:{INK};padding:0 0 12px">{escape(heading)}</td></tr>
{body}
<tr><td style="padding:4px 0 4px">
<a href="{escape(url)}" style="display:inline-block;background:{BUTTON};color:#ffffff;font-weight:600;text-decoration:none;padding:12px 22px;border-radius:999px">{escape(label)}</a>
</td></tr>
{after_html}
</table>
</td></tr>
<tr><td style="padding:18px 8px 0;color:{MUTED};font-size:12px;line-height:1.5">{escape(FOOTER)}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def _text(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraphs + ["--", FOOTER]) + "\n"


def already_registered_email(to: str, *, sign_in_url: str, reset_url: str) -> Email:
    heading = "You already have a Trekly account"
    text = _text([
        "Someone (hopefully you) just tried to create a Trekly account with this email address, "
        "but you already have one.",
        f"Sign in: {sign_in_url}",
        f"Forgotten your password? Reset it here: {reset_url}",
    ])
    html = _html(
        preheader="Sign in instead, or reset your password if you've forgotten it.",
        heading=heading,
        paragraphs=[
            "Someone (hopefully you) just tried to create a Trekly account with this email address, "
            "but you already have one. Sign in to pick up where you left off."
        ],
        button=("Sign in", sign_in_url),
        after=[
            f'Forgotten your password? <a href="{escape(reset_url)}" style="color:{OLIVE}">'
            "Reset your password</a>"
        ],
    )
    return Email(to=to, subject=heading, text=text, html=html)


def google_account_email(to: str, *, sign_in_url: str) -> Email:
    heading = "You signed up with Google"
    text = _text([
        "Someone (hopefully you) just tried to create a Trekly account with this email address, "
        "but you already have one.",
        "You signed up with Google. Use 'Continue with Google' to sign in:",
        f"  {sign_in_url}",
    ])
    html = _html(
        preheader="Use 'Continue with Google' to sign in.",
        heading=heading,
        paragraphs=[
            "Someone (hopefully you) just tried to create a Trekly account with this email address, "
            "but you already have one.",
            "You signed up with Google. Use <strong>Continue with Google</strong> to sign in.",
        ],
        button=("Go to sign in", sign_in_url),
        after=[],
    )
    return Email(to=to, subject="Sign in to Trekly with Google", text=text, html=html)
