"""The campground alert emails: "We're watching" (alert set), "A site opened
up" (the whole stay is available) and "Your alert has ended" (the dates
passed without an opening).

Each has a plain-text and a simple HTML version. The HTML uses inline styles
and no images, web fonts or tracking: nothing loads from a server when it's
opened. Every email ends with a link to manage alerts.
"""

from __future__ import annotations

import os
from datetime import timedelta
from html import escape
from urllib.parse import urlencode

from app.backcountry.availability import RESULTS_URL, group_of
from app.models.availability import AvailabilityAlert
from app.notify import Email

APP_URL = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
# How often the poller looks (.github/workflows/alert-poller.yml).
CHECK_EVERY = "about every 30 minutes"

INK = "#283618"
MUTED = "#5b6450"
CREAM = "#fefae0"
OLIVE = "#606c38"
BUTTON = "#a25d20"  # the site's rust fill; white text on it passes 4.5:1


def booking_url_for(alert: AvailabilityAlert) -> str | None:
    """Parks Canada's booking form for the campground's park and booking type,
    opened on the alert's dates (startDate/endDate fill in the arrival and
    nights; no parameter sets party size)."""
    group = group_of(alert.site)
    if group is None:
        return None
    return RESULTS_URL + "?" + urlencode({
        "resourceLocationId": group.location_id,
        "mapId": group.map_id,
        "bookingCategoryId": group.booking_category_id,
        "startDate": alert.start_date.isoformat(),
        "endDate": (alert.start_date + timedelta(days=alert.nights)).isoformat(),
    })


def manage_url() -> str:
    return f"{APP_URL}/alerts"


def _day(value) -> str:
    return f"{value:%a %b} {value.day}"


def _place(alert: AvailabilityAlert) -> str:
    site = alert.site
    return site.name + (f" ({site.site_code})" if site.site_code and site.site_code != site.name else "")


def _stay(alert: AvailabilityAlert) -> str:
    leave = alert.start_date + timedelta(days=alert.nights)
    nights = f"{alert.nights} night{'s' if alert.nights != 1 else ''}"
    return f"{_day(alert.start_date)} to {_day(leave)} ({nights}), party of {alert.party_size}"


def _trail_url(alert: AvailabilityAlert) -> str | None:
    if not alert.trail_id:
        return None
    return f"{APP_URL}/trails?" + urlencode({
        "id": str(alert.trail_id), "start": alert.start_date.isoformat(),
        "nights": alert.nights, "party": alert.party_size,
    })


def _text(paragraphs: list[str], footer: str) -> str:
    return "\n\n".join(paragraphs + ["--", footer, f"Manage your alerts: {manage_url()}"]) + "\n"


def _html(*, preheader: str, heading: str, alert: AvailabilityAlert, intro: str,
          button: tuple[str, str] | None, after: list[str], footer: str) -> str:
    """One branded layout: wordmark, heading, the stay as a card, a button."""
    park = alert.site.park.name if alert.site.park else None
    card_meta = " · ".join(escape(part) for part in (park, alert.trail.name if alert.trail else None) if part)
    button_html = ""
    if button:
        label, url = button
        button_html = (
            f'<tr><td style="padding:8px 0 4px">'
            f'<a href="{escape(url)}" style="display:inline-block;background:{BUTTON};color:#ffffff;'
            f'font-weight:600;text-decoration:none;padding:12px 22px;border-radius:999px">{escape(label)}</a>'
            f"</td></tr>"
        )
    after_html = "".join(
        f'<tr><td style="padding:10px 0 0;color:{INK};font-size:15px;line-height:1.55">{line}</td></tr>'
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
<tr><td style="color:{INK};font-size:15px;line-height:1.55;padding:0 0 16px">{intro}</td></tr>
<tr><td style="padding:0 0 18px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};border-radius:12px">
<tr><td style="padding:14px 16px">
<div style="font-size:16px;font-weight:600;color:{INK}">{escape(_place(alert))}</div>
{f'<div style="font-size:13px;color:{MUTED};padding-top:2px">{card_meta}</div>' if card_meta else ""}
<div style="font-size:15px;color:{INK};padding-top:8px">{escape(_stay(alert))}</div>
</td></tr>
</table>
</td></tr>
{button_html}
{after_html}
</table>
</td></tr>
<tr><td style="padding:18px 8px 0;color:{MUTED};font-size:12px;line-height:1.5">
{escape(footer)}<br>
<a href="{escape(manage_url())}" style="color:{OLIVE}">Manage or cancel your alerts</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


FOOTER = "You're getting this because you set a campground alert on Trekly."


def watching_email(alert: AvailabilityAlert) -> Email:
    place = _place(alert)
    subject = f"We're watching {alert.site.name} for {_day(alert.start_date)}"
    text = _text([
        f"We're watching {place} for you.",
        f"  {_stay(alert)}",
        f"We check Parks Canada {CHECK_EVERY} and email you once, as soon as every night "
        "of your stay is available. Trekly doesn't book for you, so act quickly when it arrives.",
    ], FOOTER)
    html = _html(
        preheader="We'll email you as soon as every night opens up.",
        heading="We're watching",
        alert=alert,
        intro=f"We check Parks Canada {CHECK_EVERY} and email you once, as soon as every night of "
              "this stay is available.",
        button=None,
        after=["Trekly doesn't book for you, so act quickly when that email arrives."],
        footer=FOOTER,
    )
    return Email(to=alert.email, subject=subject, text=text, html=html)


def opened_email(alert: AvailabilityAlert) -> Email:
    booking_url = booking_url_for(alert) or "https://reservation.pc.gc.ca"
    trail_url = _trail_url(alert)
    subject = f"A site opened up: {alert.site.name}, {_day(alert.start_date)}"
    paragraphs = [
        f"Good news: {_place(alert)} is showing as available for your whole stay.",
        f"  {_stay(alert)}",
        "Spots go quickly and Trekly doesn't book for you, so book on Parks Canada soon:",
        f"  {booking_url}",
    ]
    if trail_url:
        paragraphs.append(f"Trail page: {trail_url}")
    paragraphs.append(
        "This alert won't email you again. If the spot is gone by the time you look, "
        "turn the alert back on from your alerts."
    )
    after = []
    if trail_url:
        after.append(f'<a href="{escape(trail_url)}" style="color:{OLIVE}">See it on the trail page</a>')
    after.append(
        f'<span style="color:{MUTED};font-size:14px">This alert won\'t email you again. If the spot is gone '
        "by the time you look, turn the alert back on from your alerts.</span>"
    )
    html = _html(
        preheader="Every night of your stay is available right now. Book on Parks Canada soon.",
        heading="A site opened up",
        alert=alert,
        intro="Every night of your stay is showing as available right now. Spots go quickly and "
              "Trekly doesn't book for you, so book on Parks Canada soon.",
        button=("Book on Parks Canada", booking_url),
        after=after,
        footer=FOOTER,
    )
    return Email(to=alert.email, subject=subject, text=_text(paragraphs, FOOTER), html=html)


def ended_email(alert: AvailabilityAlert) -> Email:
    subject = f"Your alert has ended: {alert.site.name}, {_day(alert.start_date)}"
    explore = f"{APP_URL}/trail-list"
    text = _text([
        f"Your alert for {_place(alert)} has ended. The first night of the stay has passed "
        "and no opening came up for every night, so we've stopped checking.",
        f"  {_stay(alert)}",
        f"Planning another trip? Set a new alert from any overnight trail: {explore}",
    ], FOOTER)
    html = _html(
        preheader="The dates passed without an opening, so we've stopped checking.",
        heading="Your alert has ended",
        alert=alert,
        intro="The first night of this stay has passed and no opening came up for every night, "
              "so we've stopped checking.",
        button=("Find another trip", explore),
        after=[],
        footer=FOOTER,
    )
    return Email(to=alert.email, subject=subject, text=text, html=html)
