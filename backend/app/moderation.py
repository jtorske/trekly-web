"""Moderation of user content: automated screening, reports, new-account
limits, account restrictions and the admin digest.

Screening (screen_content), on every create or edit of a hike note or
photo, a bio, a profile photo or a comment (app/comments.py):

- passed: published as usual. The scores are kept on the item.
- flagged: held. The content is withheld from its column (see
  app/models/moderation.py), only the author sees it, with "Your post is
  being reviewed", and it joins the admin queue. Nothing is deleted.
- unavailable (no key, timeout, error, or the photo couldn't be read):
  published, and queued for review afterwards. Users are never blocked by
  the moderation service being down.
- child safety (CHILD_SAFETY_CATEGORIES): held at once, any photo copied to
  the private quarantine bucket and removed from where the author could
  reach it, the account locked, and an urgent email to the admin with
  reporting instructions (app/moderation_emails.py). Nothing is deleted.

Content that replaces something an admin hid is held for review whatever
the screening says, so editing can't undo a decision.

Reports (record_report): every report puts its item in the queue. Once
REPORTS_TO_HIDE different accounts with a confirmed email and an account
older than REPORTER_MIN_ACCOUNT_AGE have reported it, it's held pending
review. A report from someone the reported person has blocked never counts.

Every threshold is in app/moderation_config.py.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import moderation_config as config
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.comment import ActivityComment
from app.models.admin import AUTH_USERS, SYSTEM_ADMIN_ID, AdminAuditLog
from app.models.availability import JobLock
from app.models.hike_log import HikeLog
from app.models.moderation import AccountRestriction, ModerationItem
from app.models.privacy import ProfileModeration, ProfileReport
from app.models.social import Block, Notification

log = logging.getLogger(__name__)

PHOTO_BUCKETS = {"hike_photo": "hike-photos", "avatar": "avatars"}
QUARANTINE_BUCKET = "moderation-quarantine"
WITHHELD = ("held", "hidden")
POST_HELD_REASON = "Hidden after reports, pending review."
DIGEST_JOB = "moderation_digest"


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ------------------------------------------------------------------ screening


@dataclass
class Screening:
    flagged: bool
    child_safety: bool
    scores: dict[str, float]
    categories: list[str]
    model: str


class ScreeningUnavailable(RuntimeError):
    """The moderation service couldn't give an answer."""


class Screener(Protocol):
    def screen(self, text: str | None, image: tuple[bytes, str] | None) -> Screening: ...


def judge(categories: dict, scores: dict, model: str, flagged: bool) -> Screening:
    """The verdict on one moderation result: OpenAI's own flag, or a score at
    a stricter CATEGORY_HOLD_SCORES line."""
    scores = {name: float(value) for name, value in (scores or {}).items() if isinstance(value, (int, float))}
    hits = sorted(name for name, hit in (categories or {}).items() if hit)
    for name, line in config.CATEGORY_HOLD_SCORES.items():
        if scores.get(name, 0.0) >= line and name not in hits:
            hits.append(name)
    child = any(name in hits for name in config.CHILD_SAFETY_CATEGORIES)
    return Screening(flagged=bool(flagged or hits), child_safety=child, scores=scores, categories=hits, model=model)


class OpenAIScreener:
    """OpenAI's moderation endpoint: text and an image in one request."""

    def __init__(self, api_key: str, url: str = config.MODERATION_URL):
        self.url = url
        # A closure, not an attribute, so the key never shows in a dump or a log.
        self._headers = lambda: {"Authorization": f"Bearer {api_key}"}

    def __repr__(self) -> str:
        return "OpenAIScreener()"

    def screen(self, text: str | None, image: tuple[bytes, str] | None) -> Screening:
        inputs: list[dict] = []
        if text:
            inputs.append({"type": "text", "text": text})
        if image is not None:
            data, mime = image
            encoded = base64.b64encode(data).decode()
            inputs.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        if not inputs:
            return Screening(False, False, {}, [], config.MODERATION_MODEL)
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"model": config.MODERATION_MODEL, "input": inputs}).encode(),
            method="POST",
            headers={**self._headers(), "Content-Type": "application/json", "User-Agent": "trekly-api/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=config.MODERATION_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
            result = payload["results"][0]
            return judge(result.get("categories"), result.get("category_scores"),
                         str(payload.get("model") or config.MODERATION_MODEL), bool(result.get("flagged")))
        except urllib.error.HTTPError as error:
            raise ScreeningUnavailable(f"HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
            raise ScreeningUnavailable("no usable answer") from None


def screener_from_env() -> Screener | None:
    key = os.getenv("OPENAI_API_KEY")
    return OpenAIScreener(key) if key else None


class MediaStore(Protocol):
    """User photos in Storage, read with the service-role key."""

    def read(self, bucket: str, path: str) -> tuple[bytes, str]: ...
    def quarantine(self, bucket: str, path: str) -> str: ...
    def signed_url(self, bucket: str, path: str) -> str | None: ...


class SupabaseMediaStore:
    def read(self, bucket: str, path: str) -> tuple[bytes, str]:
        from app.trail_photos import storage_from_env

        storage = storage_from_env(bucket)
        if storage is None:
            raise ScreeningUnavailable("storage isn't configured")
        return storage.download(path)

    def quarantine(self, bucket: str, path: str) -> str:
        """Copies the photo into the quarantine bucket, then removes the
        original from where its author can reach it. If the copy fails, the
        original stays put: evidence is never lost."""
        from app.trail_photos import storage_from_env

        source, target = storage_from_env(bucket), storage_from_env(QUARANTINE_BUCKET)
        if source is None or target is None:
            raise RuntimeError("storage isn't configured")
        data, mime = source.download(path)
        copy = f"{bucket}/{path}"
        target.upload(copy, data, upsert=True, content_type=mime.split(";")[0])
        source.delete([path])
        return copy

    def signed_url(self, bucket: str, path: str) -> str | None:
        from app.trail_photos import storage_from_env

        if bucket == "avatars":
            base = os.getenv("SUPABASE_URL", "").rstrip("/")
            return f"{base}/storage/v1/object/public/avatars/{path}" if base else None
        storage = storage_from_env(bucket)
        if storage is None:
            return None
        try:
            return storage.signed_url(path)
        except Exception:  # noqa: BLE001 - a missing preview never breaks the queue
            return None


# ------------------------------------------------------------------ accounts


@dataclass
class Account:
    created_at: datetime | None
    email_confirmed: bool
    email: str | None


def account(db: Session, user_id: UUID) -> Account | None:
    """The auth.users facts moderation needs. None when there's no row,
    which only happens in tests: such accounts get no new-account limits."""
    row = db.execute(
        select(AUTH_USERS.c.created_at, AUTH_USERS.c.email_confirmed_at, AUTH_USERS.c.email)
        .where(AUTH_USERS.c.id == user_id)
    ).first()
    if row is None:
        return None
    return Account(created_at=_aware(row.created_at), email_confirmed=row.email_confirmed_at is not None,
                   email=row.email)


def is_new_account(info: Account | None, at: datetime) -> bool:
    return info is not None and info.created_at is not None and at - info.created_at < config.NEW_ACCOUNT_PERIOD


def has_blocked(db: Session, blocker_id: UUID, blocked_id: UUID) -> bool:
    """Whether `blocker_id` has blocked `blocked_id` (the blocks table,
    migration e6b2d8a4c0f7)."""
    return db.get(Block, (blocker_id, blocked_id)) is not None


def restriction(db: Session, user_id: UUID, at: datetime | None = None) -> str | None:
    """"locked" or "suspended" while one is in force, else None."""
    row = db.get(AccountRestriction, user_id)
    if row is None:
        return None
    if row.locked_at is not None:
        return "locked"
    until = _aware(row.suspended_until)
    if until is not None and until > (at or now()):
        return "suspended"
    return None


def ensure_can_publish(db: Session, user_id: UUID) -> None:
    state = restriction(db, user_id)
    if state == "locked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"This account is locked. Contact {config.APPEAL_EMAIL}.")
    if state == "suspended":
        until = _aware(db.get(AccountRestriction, user_id).suspended_until)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account is suspended until {until:%B} {until.day}, {until.year}. "
            f"You can't post or change your profile until then. Questions: {config.APPEAL_EMAIL}.",
        )


def ensure_can_add_photo(db: Session, user_id: UUID) -> None:
    if not config.PHOTOS_NEED_CONFIRMED_EMAIL:
        return
    info = account(db, user_id)
    if info is not None and not info.email_confirmed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Confirm your email address to add photos. Check your inbox for the link.")


def ensure_can_comment(db: Session, user_id: UUID, count_since: Callable[[datetime], int]) -> None:
    """For the comments feature: confirmed email, no restriction, and the
    comment rate limits (`count_since(t)` = their comments since t)."""
    ensure_can_publish(db, user_id)
    info = account(db, user_id)
    if config.COMMENTS_NEED_CONFIRMED_EMAIL and info is not None and not info.email_confirmed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Confirm your email address to comment. Check your inbox for the link.")
    at = now()
    limits = config.NEW_ACCOUNT_COMMENT_LIMITS if is_new_account(info, at) else config.COMMENT_LIMITS
    _enforce(limits, count_since, at, "comments")


def _enforce(limits, count_since: Callable[[datetime], int], at: datetime, noun: str) -> None:
    for most, window in limits:
        if count_since(at - window) >= most:
            if window <= timedelta(minutes=1):
                detail = "You're commenting very quickly. Wait a minute, then try again." if noun == "comments"                     else f"You've reached the limit of {most} {noun} a minute. Wait a minute, then try again."
            elif window <= timedelta(hours=1):
                detail = f"You've reached the limit of {most} {noun} an hour. Try again a little later."
            else:
                detail = f"You've reached the limit of {most} {noun} a day. Try again tomorrow."
            raise HTTPException(status_code=429, detail=detail)


def ensure_post_rate(db: Session, user_id: UUID) -> None:
    """New Trail Journal entries. Undated hikes with no note or photo are
    what "Add past hikes" makes in bulk, so they don't count."""
    info = account(db, user_id)
    at = now()
    limits = config.NEW_ACCOUNT_POST_LIMITS if is_new_account(info, at) else config.POST_LIMITS

    def count_since(since: datetime) -> int:
        return db.scalar(
            select(func.count()).select_from(HikeLog).where(
                HikeLog.user_id == user_id,
                HikeLog.created_at >= since,
                (HikeLog.hiked_on.is_not(None)) | HikeLog.note.is_not(None) | HikeLog.photo_path.is_not(None),
            )
        ) or 0

    _enforce(limits, count_since, at, "posts")


# ------------------------------------------------------------------ items


def find_item(db: Session, kind: str, target_id: UUID) -> ModerationItem | None:
    return db.scalar(select(ModerationItem).where(ModerationItem.kind == kind, ModerationItem.target_id == target_id))


def _item(db: Session, kind: str, target_id: UUID, author_id: UUID) -> ModerationItem:
    item = find_item(db, kind, target_id)
    if item is None:
        item = ModerationItem(id=uuid.uuid4(), kind=kind, target_id=target_id, author_id=author_id, state="visible",
                              in_queue=False, created_at=now(), activity_at=now(),
                              qualifying_reports=0, open_reports=0)
        db.add(item)
    return item


def _queue(item: ModerationItem, reason: str) -> None:
    item.in_queue = True
    # A child-safety item stays marked as one whatever happens next.
    if item.queue_reason != "child_safety":
        item.queue_reason = reason
    item.activity_at = now()
    item.digest_sent_at = None


def _fields(db: Session, item: ModerationItem) -> list[tuple[object, str, str]]:
    """(row, column, item attribute) for each value this item can withhold."""
    if item.kind in ("hike_note", "hike_photo"):
        hike = db.get(HikeLog, item.target_id)
        if hike is None:
            return []
        return [(hike, "note", "text")] if item.kind == "hike_note" else [(hike, "photo_path", "photo_path")]
    if item.kind in ("bio", "avatar", "profile"):
        profile = db.get(Profile, item.target_id)
        if profile is None:
            return []
        return {
            "bio": [(profile, "bio", "text")],
            "avatar": [(profile, "avatar_path", "photo_path")],
            "profile": [(profile, "bio", "text"), (profile, "avatar_path", "photo_path")],
        }[item.kind]
    if item.kind == "comment":
        comment = db.get(ActivityComment, item.target_id)
        return [(comment, "body", "text")] if comment else []
    if item.kind == "post":
        post = db.get(ActivityPost, item.target_id)
        if post is None or post.kind != "hike" or post.hike_log_id is None:
            return []
        hike = db.get(HikeLog, post.hike_log_id)
        return [(hike, "note", "text"), (hike, "photo_path", "photo_path")] if hike else []
    return []


def withhold(db: Session, item: ModerationItem, state: str) -> None:
    """Moves the content out of its column into the item (state held or hidden)."""
    for row, column, attribute in _fields(db, item):
        value = getattr(row, column)
        if value is not None:
            setattr(item, attribute, value)
            setattr(row, column, None)
    if item.kind == "comment":
        # Nobody keeps a notification about a comment they can't see.
        db.execute(delete(Notification).where(Notification.comment_id == item.target_id))
    if item.kind == "post":
        post = db.get(ActivityPost, item.target_id)
        if post is not None and post.hidden_at is None:
            post.hidden_at, post.hidden_by, post.hidden_reason = now(), None, POST_HELD_REASON
    item.state = state


def restore(db: Session, item: ModerationItem) -> None:
    """Puts withheld content back, unless its column has since been refilled."""
    if item.state in WITHHELD:
        for row, column, attribute in _fields(db, item):
            value = getattr(item, attribute)
            if value is not None and getattr(row, column) is None:
                setattr(row, column, value)
    if item.kind == "post":
        post = db.get(ActivityPost, item.target_id)
        if post is not None:
            post.hidden_at = post.hidden_by = post.hidden_reason = None
    item.state = "visible"


def withheld_items(db: Session, kinds: Iterable[str], target_ids: Iterable[UUID]) -> dict[tuple[str, UUID], ModerationItem]:
    """Held or hidden items among these targets, for the author's own views."""
    target_ids = list(set(target_ids))
    if not target_ids:
        return {}
    rows = db.scalars(select(ModerationItem).where(
        ModerationItem.kind.in_(list(kinds)), ModerationItem.target_id.in_(target_ids),
        ModerationItem.state.in_(WITHHELD),
    ))
    return {(row.kind, row.target_id): row for row in rows}


def review_state(*items: ModerationItem | None) -> str | None:
    """What the author sees: "pending" (being reviewed) or "hidden" (removed)."""
    states = {item.state for item in items if item is not None and item.state in WITHHELD}
    if "hidden" in states:
        return "hidden"
    return "pending" if states else None


# ------------------------------------------------------------------ screening content


@dataclass
class Services:
    """What screening and the admin actions reach outside the database. The
    routers build one per request (get_moderation_services), tests replace it."""

    screener: Screener | None
    media: MediaStore
    # Admin emails (the digest, urgent alerts), and emails to authors (no-reply@).
    sender: object  # app.notify.EmailSender
    author_sender: object | None = None
    supabase: object | None = None  # app.supabase_admin.SupabaseAdmin
    after_commit: list[Callable[[], None]] = field(default_factory=list)

    def run_after_commit(self) -> None:
        tasks, self.after_commit = self.after_commit, []
        for task in tasks:
            try:
                task()
            except Exception:  # noqa: BLE001 - emails after the fact never fail a request
                log.exception("Moderation follow-up failed")


@dataclass
class Outcome:
    """publish: write the new value to its column. pending: the author sees
    "being reviewed"."""

    publish: bool
    item: ModerationItem

    @property
    def pending(self) -> bool:
        return not self.publish


def run_screening(services: Services, kind: str, text: str | None = None,
                  photo_path: str | None = None) -> Screening | None:
    """The automated check on a text or a photo; None when it's unavailable
    (no key, timeout, error, or the photo couldn't be read)."""
    try:
        if services.screener is None:
            raise ScreeningUnavailable("no key")
        image = services.media.read(PHOTO_BUCKETS[kind], photo_path) if photo_path else None
        return services.screener.screen(text, image)
    except Exception as error:  # noqa: BLE001 - any failure means "publish, review later"
        log.warning("Moderation screening unavailable for %s: %s", kind, error)
        return None


def publishable(verdict: Screening | None) -> bool:
    """Whether new content (with nothing hidden before it) goes straight up."""
    return verdict is None or not verdict.flagged


def record_screening(
    db: Session,
    services: Services,
    verdict: Screening | None,
    *,
    kind: str,
    target_id: UUID,
    author_id: UUID,
    text: str | None = None,
    photo_path: str | None = None,
) -> Outcome:
    """Records a screening on the content's item and decides what happens.
    The caller writes the value to its column only when `outcome.publish`;
    otherwise it's kept on the item (held). Adds to the session; the caller
    commits, then calls services.run_after_commit()."""
    item = _item(db, kind, target_id, author_id)
    replaces_hidden = item.decision == "hidden"
    item.text, item.photo_path, item.author_id = text, photo_path, author_id
    if not replaces_hidden:
        item.decision = None

    item.screened_at = now()
    if verdict is None:
        item.screening, item.scores, item.flagged_categories, item.screening_model = "unavailable", None, None, None
    else:
        item.screening = "flagged" if verdict.flagged else "passed"
        item.scores, item.flagged_categories, item.screening_model = verdict.scores, verdict.categories, verdict.model

    if verdict is not None and verdict.child_safety:
        _child_safety(db, services, item)
        return Outcome(publish=False, item=item)
    if verdict is not None and verdict.flagged:
        item.state = "held"
        _queue(item, "flagged")
        _notify_admin_later(db, services)
        return Outcome(publish=False, item=item)
    if replaces_hidden:
        item.state = "held"
        _queue(item, "edited_after_hide")
        _notify_admin_later(db, services)
        return Outcome(publish=False, item=item)

    item.state = "visible"
    if verdict is None:
        _queue(item, "unscreened")
        _notify_admin_later(db, services)
    elif item.open_reports == 0 and item.queue_reason != "child_safety":
        # The content it was queued over has been replaced, and this passed.
        item.in_queue, item.queue_reason = False, None
    return Outcome(publish=True, item=item)


def screen_content(db: Session, services: Services, *, kind: str, target_id: UUID, author_id: UUID,
                   text: str | None = None, photo_path: str | None = None) -> Outcome:
    """run_screening, then record_screening, for content whose target exists."""
    verdict = run_screening(services, kind, text, photo_path)
    return record_screening(db, services, verdict, kind=kind, target_id=target_id, author_id=author_id,
                            text=text, photo_path=photo_path)


def content_removed(db: Session, kind: str, target_id: UUID) -> None:
    """The author cleared a held or hidden value themselves: their views stop
    showing it. The item keeps it for the admin (and a child-safety one
    stays exactly as it is)."""
    item = find_item(db, kind, target_id)
    if item is not None and item.state in WITHHELD and not item.child_safety:
        item.state = "visible"


def unchanged(item: ModerationItem | None, value: str | None, attribute: str) -> bool:
    """The author re-sent the value they were shown, which is the withheld one."""
    return item is not None and item.state in WITHHELD and value is not None and getattr(item, attribute) == value


# ------------------------------------------------------------------ child safety


def _child_safety(db: Session, services: Services, item: ModerationItem) -> None:
    item.state, item.child_safety = "held", True
    _queue(item, "child_safety")
    if item.photo_path and item.kind in PHOTO_BUCKETS:
        try:
            item.quarantine_path = services.media.quarantine(PHOTO_BUCKETS[item.kind], item.photo_path)
        except Exception:  # noqa: BLE001 - the alert says so; the original stays where it was
            log.exception("Couldn't quarantine a child-safety photo")
    lock_account(db, services, item.author_id, "Automatic: possible child sexual abuse material.")
    db.add(AdminAuditLog(admin_id=SYSTEM_ADMIN_ID, action="lock_account", target_user_id=item.author_id,
                         details={"item_id": str(item.id), "kind": item.kind, "automatic": True},
                         created_at=now()))
    db.flush()
    item_id = item.id

    def alert() -> None:
        from app.moderation_emails import child_safety_email

        fresh = db.get(ModerationItem, item_id)
        services.sender.send(child_safety_email(db, fresh))

    services.after_commit.append(alert)


def lock_account(db: Session, services: Services, user_id: UUID, reason: str) -> bool:
    """Locks the account: the API refuses new content, the profile is
    hidden, and Supabase stops sign-ins. Returns whether Supabase agreed."""
    row = db.get(AccountRestriction, user_id) or AccountRestriction(user_id=user_id)
    row.locked_at, row.lock_reason, row.updated_at = row.locked_at or now(), reason[:500], now()
    db.add(row)
    if db.get(ProfileModeration, user_id) is None:
        db.add(ProfileModeration(user_id=user_id, hidden_at=now(), hidden_by=None, reason=reason[:500]))
    if services.supabase is None:
        return False
    try:
        services.supabase.ban(user_id)
        return True
    except Exception:  # noqa: BLE001 - the app-level lock still holds
        log.exception("Supabase ban failed during an account lock")
        return False


# ------------------------------------------------------------------ reports


def report_target(post: ActivityPost | None, trip_note: HikeLog | None, profile: Profile,
                  comment: ActivityComment | None = None) -> tuple[str, UUID, str | None, str | None]:
    """(kind, target id, text, photo path) of what a report is about."""
    if comment is not None:
        return "comment", comment.id, comment.body, None
    if post is not None:
        hike = post.hike_log if post.kind == "hike" else None
        return "post", post.id, (hike.note if hike else post.body), (hike.photo_path if hike else None)
    if trip_note is not None:
        return "hike_note", trip_note.id, trip_note.note, None
    return "profile", profile.id, profile.bio, profile.avatar_path


def reporter_qualifies(db: Session, reporter_id: UUID, reported_id: UUID, at: datetime) -> bool:
    if has_blocked(db, reported_id, reporter_id):
        return False
    info = account(db, reporter_id)
    if info is None:
        return True
    return (
        info.email_confirmed
        and info.created_at is not None
        and at - info.created_at >= config.REPORTER_MIN_ACCOUNT_AGE
    )


def record_report(db: Session, services: Services, report: ProfileReport, *, kind: str, target_id: UUID,
                  author_id: UUID, text: str | None, photo_path: str | None) -> ModerationItem:
    """Links a new report to its item, queues the item, and holds it once
    enough qualifying accounts have reported it. A report from someone the
    reported person blocked is kept but never counts (and doesn't queue)."""
    at = now()
    item = _item(db, kind, target_id, author_id)
    if item.state == "visible":
        item.text, item.photo_path = text, photo_path
    report.item_id = item.id
    report.counts_toward_hide = reporter_qualifies(db, report.reporter_id, author_id, at)
    db.flush()
    blocked = has_blocked(db, author_id, report.reporter_id)
    _recount(db, item)
    if blocked:
        return item
    item.last_reported_at = at
    _queue(item, "reported")
    if item.state == "visible" and item.qualifying_reports >= config.REPORTS_TO_HIDE:
        withhold(db, item, "held")
    _notify_admin_later(db, services)
    return item


def _recount(db: Session, item: ModerationItem) -> None:
    open_reports = select(ProfileReport.reporter_id).where(ProfileReport.item_id == item.id,
                                                           ProfileReport.status == "open")
    item.open_reports = db.scalar(select(func.count(func.distinct(open_reports.subquery().c.reporter_id)))) or 0
    qualifying = open_reports.where(ProfileReport.counts_toward_hide.is_(True)).subquery()
    item.qualifying_reports = db.scalar(select(func.count(func.distinct(qualifying.c.reporter_id)))) or 0


def resolve_reports(db: Session, item: ModerationItem, admin_id: UUID) -> None:
    db.execute(
        update(ProfileReport).execution_options(synchronize_session=False)
        .where(ProfileReport.item_id == item.id, ProfileReport.status == "open")
        .values(status="resolved", resolved_at=now(), resolved_by=admin_id)
    )
    item.open_reports = item.qualifying_reports = 0


# ------------------------------------------------------------------ admin digest


def _notify_admin_later(db: Session, services: Services) -> None:
    def task() -> None:
        maybe_send_digest(db, services.sender)

    if task.__qualname__ not in {t.__qualname__ for t in services.after_commit}:
        services.after_commit.append(task)


def maybe_send_digest(db: Session, sender, at: datetime | None = None) -> bool:
    """Emails the admin what's new in the queue, at most once per
    DIGEST_INTERVAL; items that arrive in between wait for the next one (an
    event or the hourly job, scripts/moderation_digest.py). Returns whether
    an email went."""
    from app.moderation_emails import digest_email

    at = at or now()
    pending = db.scalars(
        select(ModerationItem)
        .where(ModerationItem.in_queue.is_(True), ModerationItem.digest_sent_at.is_(None))
        .order_by(ModerationItem.child_safety.desc(), ModerationItem.activity_at.desc())
    ).all()
    if not pending:
        return False
    if db.get(JobLock, DIGEST_JOB) is None:
        db.add(JobLock(name=DIGEST_JOB))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    lock = db.get(JobLock, DIGEST_JOB)
    previous = lock.last_started_at
    # Claim this hour's digest; a concurrent claimer updates no row.
    claimed = db.execute(
        update(JobLock).execution_options(synchronize_session=False)
        .where(JobLock.name == DIGEST_JOB,
               (JobLock.last_started_at.is_(None)) | (JobLock.last_started_at <= at - config.DIGEST_INTERVAL))
        .values(last_started_at=at)
    ).rowcount
    db.commit()
    if not claimed:
        return False
    try:
        sender.send(digest_email(db, pending))
    except Exception:  # noqa: BLE001 - give the slot back; the next event or run retries
        log.exception("Moderation digest didn't send")
        db.execute(update(JobLock).execution_options(synchronize_session=False).where(JobLock.name == DIGEST_JOB).values(last_started_at=previous))
        db.commit()
        return False
    ids = [item.id for item in pending]
    db.execute(update(ModerationItem).execution_options(synchronize_session=False).where(ModerationItem.id.in_(ids)).values(digest_sent_at=at))
    db.execute(update(JobLock).execution_options(synchronize_session=False).where(JobLock.name == DIGEST_JOB).values(last_finished_at=at, last_result="sent"))
    db.commit()
    return True


def get_moderation_services() -> Services:
    """FastAPI dependency; tests override it with fakes."""
    from app.notify import get_account_email_sender, get_email_sender
    from app.supabase_admin import supabase_admin_from_env

    return Services(screener=screener_from_env(), media=SupabaseMediaStore(), sender=get_email_sender(),
                    author_sender=get_account_email_sender(), supabase=supabase_admin_from_env())
