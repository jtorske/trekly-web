"""Emails about someone's own Trekly account, sent by the sign-up email
helper (app/routers/signup_email.py) when someone signs up with an address
that already has an account:

- already_registered_email: the account has a password. A "Sign in" button
  and a "Reset your password" link.
- google_account_email: the account only signs in with Google. A "Go to
  sign in" button and a "Set a password" link (a one-time reset link).

Same look as Supabase's auth emails (supabase/templates/build.mjs): the
logo and wordmark header, a white card, the rust button, inline styles, and
the support address in the footer. The only thing loaded from a server is
the logo, from our own site.

Sent from RESEND_ACCOUNT_FROM_EMAIL (app/notify.py), not the alerts address.
"""

from __future__ import annotations

import os
from html import escape

from app.alert_emails import BUTTON, CREAM, INK, MUTED, OLIVE
from app.notify import Email

BORDER = "#e3e0c8"
SERIF = "Georgia,'Times New Roman',serif"
SUPPORT = "treklyusersupport@gmail.com"  # as in supabase/templates/build.mjs

FOOTER = (
    "You're getting this because someone tried to create a Trekly account with this address. "
    "If that wasn't you, you can ignore this email: nothing has changed."
)
EXPIRY = "This link works once and expires in an hour."


def _app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def _header() -> str:
    """The logo and wordmark, linked to the site, as in the auth templates."""
    site = escape(_app_url())
    return f"""<tr><td style="padding:0 0 18px">
<a href="{site}" style="text-decoration:none;color:{INK}">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding:0 10px 0 0;vertical-align:middle"><img src="{site}/email/trekly-mark.png" width="32" height="32" alt="Trekly logo" style="display:block;border:0;border-radius:7px"></td>
<td style="vertical-align:middle;font-family:{SERIF};font-size:22px;font-weight:700;color:{INK}">Trekly</td>
</tr></table>
</a>
</td></tr>"""


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
{_header()}
<tr><td style="background:#ffffff;border:1px solid {BORDER};border-radius:16px;padding:26px 24px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="font-family:{SERIF};font-size:24px;line-height:1.25;font-weight:600;color:{INK};padding:0 0 12px">{escape(heading)}</td></tr>
{body}
<tr><td style="padding:4px 0 4px">
<a href="{escape(url)}" style="display:inline-block;background:{BUTTON};color:#ffffff;font-weight:600;font-size:15px;text-decoration:none;padding:12px 22px;border-radius:999px">{escape(label)}</a>
</td></tr>
{after_html}
</table>
</td></tr>
<tr><td style="padding:18px 8px 0;color:{MUTED};font-size:12px;line-height:1.5">
{escape(FOOTER)}<br>
Questions? Email <a href="mailto:{SUPPORT}" style="color:{OLIVE}">{SUPPORT}</a>.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def _text(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraphs + ["--", FOOTER, f"Questions? Email {SUPPORT}."]) + "\n"


INTRO = (
    "Someone (hopefully you) just tried to create a Trekly account with this email address, "
    "but you already have one."
)


def already_registered_email(to: str, *, sign_in_url: str, reset_url: str) -> Email:
    heading = "You already have a Trekly account"
    text = _text([
        INTRO,
        f"Sign in: {sign_in_url}",
        f"Forgotten your password? Reset your password: {reset_url}",
    ])
    html = _html(
        preheader="Sign in instead, or reset your password if you've forgotten it.",
        heading=heading,
        paragraphs=[f"{INTRO} Sign in to pick up where you left off."],
        button=("Sign in", sign_in_url),
        after=[
            f'Forgotten your password? <a href="{escape(reset_url)}" style="color:{OLIVE}">'
            "Reset your password</a>"
        ],
    )
    return Email(to=to, subject=heading, text=text, html=html)


def google_account_email(to: str, *, sign_in_url: str, set_password_url: str, one_time_link: bool) -> Email:
    """`set_password_url` is a one-time reset link when `one_time_link`, else
    the "Forgot password" page (no service-role key to make a link with)."""
    heading = "You signed up with Google"
    expiry = f" {EXPIRY}" if one_time_link else ""
    text = _text([
        INTRO,
        "You signed up with Google. Use 'Continue with Google' to sign in:",
        f"  {sign_in_url}",
        f"Prefer email and password? Set a password: {set_password_url}{expiry}",
    ])
    after = (
        f'Prefer email and password? <a href="{escape(set_password_url)}" style="color:{OLIVE}">'
        "Set a password</a>"
    )
    if one_time_link:
        after += f'<br><span style="color:{MUTED};font-size:13px">{EXPIRY}</span>'
    html = _html(
        preheader="Use 'Continue with Google' to sign in.",
        heading=heading,
        paragraphs=[INTRO, "You signed up with Google. Use <strong>Continue with Google</strong> to sign in."],
        button=("Go to sign in", sign_in_url),
        after=[after],
    )
    return Email(to=to, subject="Sign in to Trekly with Google", text=text, html=html)
