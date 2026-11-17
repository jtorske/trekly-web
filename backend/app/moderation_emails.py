"""Moderation emails, all plain text:

- digest_email: to the admin, what's new in the moderation queue (held,
  reported, unscreened). At most one per hour (app/moderation.py).
- child_safety_email: to the admin at once, never batched: a possible
  child sexual abuse image or text, what Trekly already did, and how to
  report it to Cybertip.ca. It never contains or links the content itself.
- hidden_email / warning_email / suspension_email: to the author, with the
  reason and the appeal address.

Emails to authors never name who reported them.
"""

from __future__ import annotations

import os
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import moderation_config as config
from app.models.account import Profile
from app.models.admin import AUTH_USERS
from app.models.hike_log import HikeLog
from app.models.moderation import ModerationItem
from app.notify import Email

KIND_LABELS = {
    "post": "Activity post",
    "hike_note": "Hike note",
    "hike_photo": "Hike photo",
    "bio": "Bio",
    "avatar": "Profile photo",
    "profile": "Profile",
    "comment": "Comment",
}
# What the author is told their content was, in "Your ... was hidden".
AUTHOR_LABELS = {
    "post": "Activity post",
    "hike_note": "note on a hike",
    "hike_photo": "photo on a hike",
    "bio": "profile bio",
    "avatar": "profile photo",
    "profile": "profile bio and photo",
    "comment": "comment",
}
REASON_LABELS = {
    "flagged": "Held: flagged by the automated check",
    "unscreened": "Published unscreened (the check was down)",
    "reported": "Reported",
    "child_safety": "CHILD SAFETY: held, account locked",
    "edited_after_hide": "Held: edited after being hidden",
}


def admin_email() -> str:
    return os.getenv("PROFILE_REPORTS_EMAIL", config.ADMIN_EMAIL)


def _app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def _username(db: Session, user_id) -> str:
    profile = db.get(Profile, user_id)
    return f"@{profile.username}" if profile and profile.username else f"user {user_id}"


def _where(db: Session, item: ModerationItem) -> str | None:
    if item.kind in ("hike_note", "hike_photo"):
        hike = db.get(HikeLog, item.target_id)
        return f"on {hike.trail.name}" if hike and hike.trail else None
    return None


def digest_email(db: Session, items: list[ModerationItem]) -> Email:
    shown = items[: config.DIGEST_MAX_ITEMS]
    held = sum(1 for item in items if item.state == "held")
    reported = sum(1 for item in items if item.open_reports)
    lines = [
        f"{len(items)} new in the Trekly moderation queue: {held} held, {reported} reported.",
        "",
    ]
    if any(item.child_safety for item in items):
        lines += ["!! At least one is a CHILD SAFETY item. See the separate urgent email.", ""]
    for item in shown:
        where = _where(db, item)
        lines.append(f"- {KIND_LABELS.get(item.kind, item.kind)} by {_username(db, item.author_id)}"
                     f"{f' {where}' if where else ''}")
        lines.append(f"  {REASON_LABELS.get(item.queue_reason or '', item.queue_reason or 'In the queue')}"
                     f"{f', {item.open_reports} report(s)' if item.open_reports else ''}"
                     f"{f', flagged: ' + ', '.join(item.flagged_categories) if item.flagged_categories else ''}")
        if item.text and not item.child_safety:
            excerpt = " ".join(item.text.split())
            lines.append(f"  \"{excerpt[:160]}{'…' if len(excerpt) > 160 else ''}\"")
    if len(items) > len(shown):
        lines.append(f"…and {len(items) - len(shown)} more.")
    lines += [
        "",
        f"Review them: {_app_url()}/admin/moderation",
        "",
        "You get at most one of these an hour; anything newer comes in the next one.",
    ]
    subject = f"Trekly moderation: {len(items)} new ({held} held, {reported} reported)"
    return Email(to=admin_email(), subject=subject, text="\n".join(lines) + "\n")


def child_safety_email(db: Session, item: ModerationItem) -> Email:
    """Says what happened and what to do; never the content or a link to it."""
    info = db.execute(select(AUTH_USERS.c.email, AUTH_USERS.c.created_at)
                      .where(AUTH_USERS.c.id == item.author_id)).first()
    flagged_at = item.screened_at or item.created_at
    lines = [
        "URGENT: Trekly's automated check flagged possible child sexual abuse material.",
        "",
        "What Trekly has already done:",
        f"- The {KIND_LABELS.get(item.kind, item.kind).lower()} is hidden from everyone else. If the author",
        "  could still sign in, they'd see it marked \"being reviewed\", like any held post, so",
        "  they aren't tipped off.",
        "- It has NOT been deleted. " + (
            f"The photo was copied to the private moderation-quarantine bucket ({item.quarantine_path}) "
            "and removed from where the author could reach it."
            if item.quarantine_path
            else "It's kept in Trekly's database." + (
                " The photo couldn't be copied to quarantine, so it's still at its original path: "
                f"{item.photo_path}. Don't delete it." if item.photo_path else ""
            )
        ),
        "- The account is locked: it can't post, its profile is hidden, and sign-in is blocked.",
        "- The author has NOT been told.",
        "",
        "Details for the report (no content is attached to this email):",
        f"- Item id: {item.id} ({item.kind})",
        f"- Account: {_username(db, item.author_id)}, user id {item.author_id}",
        f"- Account email: {info.email if info and info.email else '(unknown)'}",
        f"- Account created: {info.created_at.isoformat() if info and info.created_at else '(unknown)'}",
        f"- Flagged at: {flagged_at.isoformat() if flagged_at else '(unknown)'} (UTC)",
        f"- Flagged categories: {', '.join(item.flagged_categories or []) or '(none recorded)'}",
        "",
        "What to do now:",
        "1. Report it to Cybertip.ca, Canada's tipline for online child sexual exploitation:",
        "   https://www.cybertip.ca/en/report/  (or call 1-866-658-9022).",
        "   Under Canada's mandatory reporting law for internet services, a provider must report",
        "   a site address where such material may be available to the public, and notify police",
        "   if it believes an offence has been committed with its service.",
        "2. If a child may be in immediate danger, call 911 or the local police first.",
        "3. Keep everything. The law requires preserving computer data related to a police",
        "   notification for 21 days; keep it longer while anything is open. Don't delete the",
        "   item, the photo, the quarantine copy or the account.",
        "4. Don't open, download, copy or forward the image yourself beyond what Cybertip.ca or",
        "   police ask for, and don't contact the account holder.",
        "5. Record what you reported, when, and any reference number, then resolve the item in",
        f"   the admin area: {_app_url()}/admin/moderation",
        "",
        "Automated checks make mistakes. If this is clearly a false positive (for example a",
        "landscape photo), you can approve it from the queue; the lock stays until you lift it.",
    ]
    return Email(to=admin_email(), subject="URGENT: possible child sexual abuse material on Trekly",
                 text="\n".join(lines) + "\n")


def _author_email(to: str, subject: str, paragraphs: list[str]) -> Email:
    footer = [
        "--",
        f"Community Guidelines: {_app_url()}/guidelines",
        "This email is about your Trekly account. Replies to this address aren't read.",
    ]
    return Email(to=to, subject=subject, text="\n\n".join(paragraphs) + "\n\n" + "\n".join(footer) + "\n")


def _appeal() -> str:
    return (f"If you think this was a mistake, email {config.APPEAL_EMAIL} within 30 days. "
            "Tell us your username and why, and we'll take another look.")


def hidden_email(to: str, item: ModerationItem, reason: str) -> Email:
    what = AUTHOR_LABELS.get(item.kind, "post")
    return _author_email(to, f"Your {what} on Trekly was hidden", [
        f"Hi, a Trekly moderator hid your {what}. It's no longer visible to other hikers.",
        f"Reason: {reason}",
        "Your journal and the rest of your account are unaffected. Please read the Community "
        "Guidelines before posting again.",
        _appeal(),
    ])


def warning_email(to: str, reason: str) -> Email:
    return _author_email(to, "A warning about your Trekly account", [
        "Hi, a Trekly moderator reviewed activity on your account and is sending you a warning.",
        f"Reason: {reason}",
        "Nothing on your account has changed because of this warning, but repeated problems can "
        "lead to a suspension. Please read the Community Guidelines.",
        _appeal(),
    ])


def suspension_email(to: str, reason: str, until_label: str) -> Email:
    return _author_email(to, "Your Trekly account is suspended", [
        f"Hi, a Trekly moderator suspended your account until {until_label}. You can't sign in "
        "or post until then.",
        f"Reason: {reason}",
        _appeal(),
    ])
