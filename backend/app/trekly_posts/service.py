"""The daily run, publishing, and pacing rules for automatic @trekly posts.

`run_daily` (scripts/trekly_posts.py):
1. takes the job lease, so overlapping runs can't both act;
2. expires drafts that have gone stale;
3. drafts one post per type scheduled for today (config/trekly_posts.toml),
   skipping anything already drafted (unique dedupe_key: idempotent). A post
   whose AI text fails the fact check is skipped: kept as "rejected" with the
   reason, never queued or published;
4. publishes at most one post: a draft an admin scheduled for today or
   earlier, else a draft of a type that auto-publishes (on by default in the
   config; the admin toggle overrides it). Pacing (`publish_refusal`) can stop it;
5. when TREKLY_POSTS_DIGEST_TO is set, emails a record of what went out and
   what was skipped, at most once a day. Without it, no email is sent.

Pacing rules, checked for every publish (the admin page's "Publish now" too):
- at most `max_posts_per_day` @trekly posts per local day, manual ones included;
- no trail twice within `trail_cooldown_days` (conditions posts excepted);
- a fact must still be approved; a stale draft can't go out.
The daily run also skips the day when real hikers have been busy posting.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_labels import official_id, real_user
from app.activity import _joined, visible_where
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.availability import JobLock
from app.models.trekly_post import TreklyFact, TreklyPostDraft, TreklyPostTypeSetting
from app.notify import Email, EmailSender
from app.trekly_posts import writer
from app.trekly_posts.config import PostsConfig
from app.trekly_posts.generators import GENERATORS, Candidate, GenContext

log = logging.getLogger(__name__)

JOB_NAME = "trekly_posts"
DIGEST_JOB = "trekly_posts_digest"
LEASE = timedelta(minutes=15)


class PublishRefused(Exception):
    pass


@dataclass
class RunReport:
    drafted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    expired: int = 0
    published: str | None = None
    # Types whose AI text failed the fact check today (skipped, not queued).
    failed_check: list[str] = field(default_factory=list)
    publish_note: str | None = None
    digest_sent_to: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"drafted {len(self.drafted)}", f"expired {self.expired}",
                 f"published {self.published or 'none'}"]
        if self.publish_note:
            parts.append(self.publish_note)
        if self.digest_sent_to:
            parts.append(f"digest to {self.digest_sent_to}")
        return "; ".join(parts)


def local_today(config: PostsConfig, now: datetime) -> date:
    return now.astimezone(ZoneInfo(config.timezone)).date()


def day_start_utc(config: PostsConfig, day: date) -> datetime:
    return datetime.combine(day, time.min, ZoneInfo(config.timezone)).astimezone(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- Locks -------------------------------------------------------------------

def _lock_row(db: Session, name: str) -> JobLock:
    if db.get(JobLock, name) is None:
        db.add(JobLock(name=name))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return db.scalar(select(JobLock).where(JobLock.name == name).with_for_update())


def acquire_lock(db: Session, now: datetime, holder: str) -> str | None:
    lock = _lock_row(db, JOB_NAME)
    if lock.locked_until and _aware(lock.locked_until) > now:
        db.rollback()
        return f"another run ({lock.locked_by}) holds the lock"
    lock.locked_by, lock.locked_until, lock.last_started_at = holder, now + LEASE, now
    db.commit()
    return None


def release_lock(db: Session, now: datetime, result: str) -> None:
    db.rollback()
    lock = db.get(JobLock, JOB_NAME)
    if lock is not None:
        lock.locked_by = lock.locked_until = None
        lock.last_finished_at, lock.last_result = now, result[:500]
        db.commit()


# --- Rules -------------------------------------------------------------------

def auto_publish_settings(db: Session, config: PostsConfig) -> dict[str, bool]:
    """Each type's auto-publish: the config's default, unless an admin set the toggle."""
    chosen = dict(db.execute(select(TreklyPostTypeSetting.post_type, TreklyPostTypeSetting.auto_publish)).all())
    return {name: bool(chosen.get(name, cfg.auto_publish)) for name, cfg in config.types.items()}


def auto_publish_types(db: Session, config: PostsConfig) -> set[str]:
    return {name for name, on in auto_publish_settings(db, config).items() if on}


def official_posts_on(db: Session, config: PostsConfig, day: date) -> int:
    official = official_id(db)
    if official is None:
        return 0
    start = day_start_utc(config, day)
    return db.scalar(
        select(func.count()).select_from(ActivityPost).where(
            ActivityPost.user_id == official, ActivityPost.created_at >= start,
            ActivityPost.created_at < start + timedelta(days=1),
        )
    ) or 0


def recent_real_posts(db: Session, config: PostsConfig, now: datetime, today: date) -> int:
    since = now - timedelta(hours=config.pacing.busy_window_hours)
    query = _joined().where(visible_where(today), ActivityPost.created_at >= since, real_user(ActivityPost.user_id))
    return db.scalar(select(func.count()).select_from(query.with_only_columns(ActivityPost.id).subquery())) or 0


def is_busy(db: Session, config: PostsConfig, now: datetime, today: date) -> bool:
    return recent_real_posts(db, config, now, today) >= config.pacing.busy_post_count


def trail_on_cooldown(db: Session, config: PostsConfig, draft: TreklyPostDraft, now: datetime) -> bool:
    if draft.trail_id is None or draft.post_type == "conditions":
        return False
    since = now - timedelta(days=config.pacing.trail_cooldown_days)
    official = official_id(db)
    posted = db.scalar(
        select(ActivityPost.id).where(
            ActivityPost.user_id == official, ActivityPost.trail_id == draft.trail_id,
            ActivityPost.created_at >= since,
        ).limit(1)
    ) if official else None
    return posted is not None


def is_stale(config: PostsConfig, draft: TreklyPostDraft, today: date) -> bool:
    days = config.type(draft.post_type).expires_after_days
    if draft.status == "scheduled" and draft.publish_on is not None:
        return draft.publish_on + timedelta(days=days) < today
    return draft.run_date + timedelta(days=days) < today


def publish_refusal(db: Session, config: PostsConfig, draft: TreklyPostDraft, now: datetime,
                    today: date) -> str | None:
    """Why this draft can't be published now, or None."""
    if draft.status not in ("draft", "scheduled"):
        return f"This post is {draft.status}."
    if official_id(db) is None:
        return "The Trekly account hasn't been set up yet (scripts/official_account.py)."
    if is_stale(config, draft, today):
        return "This draft is out of date; reject it and let the next run write a fresh one."
    if official_posts_on(db, config, today) >= config.pacing.max_posts_per_day:
        return f"@trekly has already posted {config.pacing.max_posts_per_day} time(s) today. Schedule it for another day."
    if trail_on_cooldown(db, config, draft, now):
        return f"@trekly posted about this trail within the last {config.pacing.trail_cooldown_days} days."
    if draft.fact_id is not None:
        fact = db.get(TreklyFact, draft.fact_id)
        if fact is None or not fact.approved:
            return "Its fact isn't approved any more."
    if draft.post_type == "fun_fact" and draft.fact_id is None:
        return "Its fact was deleted."
    return None


def publish(db: Session, config: PostsConfig, draft: TreklyPostDraft, now: datetime, today: date,
            by: UUID | None = None) -> ActivityPost:
    """Publish a draft as an announcement from @trekly (caller commits)."""
    # Lock the draft so two publishers can't both post it.
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.id == draft.id).with_for_update())
    reason = publish_refusal(db, config, draft, now, today)
    if reason:
        raise PublishRefused(reason)
    post = ActivityPost(
        user_id=official_id(db), kind="announcement", body=draft.body, trail_id=draft.trail_id,
        source_url=draft.source_url, source_label=draft.source_label, source_date=draft.source_date,
        created_at=now,
    )
    db.add(post)
    db.flush()
    draft.status, draft.post_id, draft.published_at, draft.updated_at = "published", post.id, now, now
    if by is not None:
        draft.decided_by, draft.decided_at = by, now
    return post


# --- Drafting ----------------------------------------------------------------

def draft_from(db: Session, config: PostsConfig, candidate: Candidate, today: date, now: datetime,
               client: writer.TextClient | None) -> TreklyPostDraft | None:
    """Insert the candidate as a draft; None if it was drafted already. A
    candidate whose AI text failed the fact check is stored as rejected (a
    record, and so the run doesn't try it again), never as a draft."""
    type_cfg = config.type(candidate.post_type)
    written = writer.write(
        candidate.post_type, candidate.template_body, candidate.data,
        use_ai=type_cfg.ai and config.ai.enabled, client=client, max_chars=config.ai.max_chars,
    )
    draft = TreklyPostDraft(
        post_type=candidate.post_type, status="rejected" if written.failed_check else "draft", dedupe_key=candidate.dedupe_key, run_date=today,
        body=written.body, template_body=candidate.template_body, writer=written.writer, ai_note=written.note,
        trail_id=candidate.trail_id, fact_id=candidate.fact_id, source_url=candidate.source_url,
        source_label=candidate.source_label, source_date=candidate.source_date,
        data={k: v for k, v in candidate.data.items() if k != "must_mention"},
        created_at=now, updated_at=now, decided_at=now if written.failed_check else None,
    )
    savepoint = db.begin_nested()
    db.add(draft)
    try:
        savepoint.commit()
    except IntegrityError:
        # Another run drafted the same thing a moment ago.
        savepoint.rollback()
        return None
    return draft


def expire_stale(db: Session, config: PostsConfig, today: date, now: datetime) -> int:
    count = 0
    for draft in db.scalars(select(TreklyPostDraft).where(TreklyPostDraft.status.in_(("draft", "scheduled")))).all():
        if is_stale(config, draft, today):
            draft.status, draft.updated_at = "expired", now
            count += 1
    return count


def _publish_queue(db: Session, config: PostsConfig, today: date) -> list[TreklyPostDraft]:
    scheduled = db.scalars(
        select(TreklyPostDraft).where(TreklyPostDraft.status == "scheduled", TreklyPostDraft.publish_on <= today)
        .order_by(TreklyPostDraft.publish_on, TreklyPostDraft.created_at)
    ).all()
    auto = auto_publish_types(db, config)
    order = list(GENERATORS)
    automatic = sorted(
        db.scalars(select(TreklyPostDraft).where(
            TreklyPostDraft.status == "draft", TreklyPostDraft.post_type.in_(auto) if auto else False,
        )).all(),
        key=lambda d: (order.index(d.post_type), d.created_at),
    ) if auto else []
    return list(scheduled) + automatic


def run_daily(db: Session, config: PostsConfig, *, now: datetime, client: writer.TextClient | None,
              sender: EmailSender | None, recipients: list[str], fetch=None, holder: str = "daily") -> RunReport:
    report = RunReport()
    today = local_today(config, now)
    reason = acquire_lock(db, now, holder)
    if reason:
        report.notes.append(f"skipped: {reason}")
        return report
    try:
        report.expired = expire_stale(db, config, today, now)
        db.commit()

        ctx = GenContext(db=db, config=config, today=today, now=now)
        if fetch is not None:
            ctx.fetch = fetch
        for name, generate in GENERATORS.items():
            type_cfg = config.type(name)
            if not type_cfg.runs_on(today):
                continue
            if db.scalar(select(TreklyPostDraft.id).where(TreklyPostDraft.post_type == name,
                                                          TreklyPostDraft.run_date == today).limit(1)):
                # One draft per type a day, however often the run happens.
                report.skipped.append(name)
                continue
            try:
                candidate = generate(ctx)
            except Exception as error:  # one broken generator mustn't stop the rest
                db.rollback()
                log.exception("Generator %s failed", name)
                report.notes.append(f"{name}: failed ({type(error).__name__})")
                continue
            if candidate is None:
                report.skipped.append(name)
                continue
            draft = draft_from(db, config, candidate, today, now, client)
            if draft is None:
                report.skipped.append(name)
            elif draft.status == "rejected":
                report.failed_check.append(name)
                report.notes.append(f"{name}: skipped, the AI text failed the fact check")
            else:
                report.drafted.append(name)
                if draft.trail_id is not None:
                    ctx.excluded_trails.add(draft.trail_id)
            db.commit()
        report.notes += ctx.notes

        if is_busy(db, config, now, today):
            report.publish_note = "busy day: hikers have been posting, so @trekly sits this one out"
        else:
            for draft in _publish_queue(db, config, today):
                try:
                    publish(db, config, draft, now, today)
                except PublishRefused as refused:
                    db.rollback()
                    report.notes.append(f"didn't publish {draft.post_type}: {refused}")
                    if official_posts_on(db, config, today) >= config.pacing.max_posts_per_day:
                        break
                    continue
                db.commit()
                report.published = draft.post_type
                break

        report.digest_sent_to = send_digest(db, config, now, today, sender, recipients)
    finally:
        release_lock(db, now, report.summary())
    return report


# --- Digest ------------------------------------------------------------------

def digest_recipients() -> list[str]:
    """TREKLY_POSTS_DIGEST_TO (comma-separated); empty means no digest."""
    return [e.strip() for e in os.getenv("TREKLY_POSTS_DIGEST_TO", "").split(",") if e.strip()]


def _today_record(db: Session, config: PostsConfig, today: date) -> tuple[list, list]:
    start = day_start_utc(config, today)
    published = db.scalars(
        select(TreklyPostDraft).where(TreklyPostDraft.status == "published", TreklyPostDraft.published_at >= start,
                                      TreklyPostDraft.published_at < start + timedelta(days=1))
        .order_by(TreklyPostDraft.published_at)
    ).all()
    # Skipped by the fact check: rejected by the run itself, not by an admin.
    skipped = db.scalars(
        select(TreklyPostDraft).where(TreklyPostDraft.status == "rejected", TreklyPostDraft.run_date == today,
                                      TreklyPostDraft.decided_by.is_(None))
        .order_by(TreklyPostDraft.created_at)
    ).all()
    return list(published), list(skipped)


def digest_email(to: str, published: list[TreklyPostDraft], skipped: list[TreklyPostDraft], waiting: int,
                 app_url: str) -> Email:
    lines: list[str] = []
    if published:
        lines += ["Posted as @trekly today:", ""]
        for draft in published:
            lines.append(f"- [{draft.post_type}] {draft.body}")
            if draft.source_url:
                lines.append(f"  Source: {draft.source_url}")
    else:
        lines.append("Nothing was posted as @trekly today.")
    if skipped:
        lines += ["", "Skipped (the AI text failed the fact check):", ""]
        lines += [f"- [{draft.post_type}] {draft.ai_note or ''}" for draft in skipped]
    if waiting:
        lines += ["", f"{waiting} draft{'s' if waiting != 1 else ''} waiting for a later day or for review."]
    lines += ["", f"See them all: {app_url}/admin/trekly-posts"]
    if len(published) == 1:
        subject = f"Trekly posted: {published[0].body[:60]}"
    elif published:
        subject = f"Trekly: {len(published)} posts today"
    else:
        subject = "Trekly: no post today"
    return Email(to=to, subject=subject, text="\n".join(lines))


def send_digest(db: Session, config: PostsConfig, now: datetime, today: date, sender: EmailSender | None,
                recipients: list[str]) -> int:
    """A record of what went out (or was skipped) today, at most once a day."""
    if not config.digest_enabled or sender is None or not recipients:
        return 0
    published, skipped = _today_record(db, config, today)
    if not published and not skipped:
        return 0
    lock = _lock_row(db, DIGEST_JOB)
    if lock.last_finished_at and local_today(config, _aware(lock.last_finished_at)) == today:
        db.rollback()
        return 0
    waiting = db.scalar(select(func.count()).select_from(TreklyPostDraft).where(
        TreklyPostDraft.status.in_(("draft", "scheduled")))) or 0
    app_url = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    sent = 0
    for to in recipients:
        try:
            sender.send(digest_email(to, published, skipped, waiting, app_url))
            sent += 1
        except Exception as error:
            log.warning("Digest email failed: %s", type(error).__name__)
    if sent:
        lock.last_finished_at, lock.last_result = now, f"digest: {len(published)} posted, {len(skipped)} skipped"
    db.commit()
    return sent


def official_profile(db: Session) -> Profile | None:
    user_id = official_id(db)
    return db.get(Profile, user_id) if user_id else None
