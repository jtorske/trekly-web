"""The admin moderation queue (/admin/moderation): held and reported content
together, with one-click actions. Admins only (require_admin), and every
action is written to admin_audit_log in the same commit as the change.

- approve: puts withheld content back (or keeps it up), closes its reports.
- hide: withholds it for good (until approved later) and emails the author
  the reason and the appeal address.
- warn: emails the author a warning with a reason. Nothing else changes.
- suspend N days: Supabase ban for N days, and the API refuses new content
  until then. Emails the author.
- ban: Supabase ban with no end, and the account is locked.
- unlock: lifts a suspension, lock or ban (e.g. a child-safety false positive).

A child-safety item never shows its photo here, only that it exists.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import moderation_config as config
from app.activity import MILESTONES
from app.admin_access import audit, is_admin, require_admin
from app.auth import CurrentUser
from app.database import get_db
from app.models.activity import ActivityPost
from app.models.admin import AUTH_USERS
from app.models.hike_log import HikeLog
from app.models.moderation import AccountRestriction, ModerationItem
from app.models.privacy import ProfileReport
from app.moderation import (
    PHOTO_BUCKETS, Services, get_moderation_services, now, resolve_reports, restore, restriction, withhold,
)
from app.moderation_emails import hidden_email, suspension_email, warning_email
from app.points_config import RANKS
from app.routers.admin import ActionOut, PersonRef, TrailRef, _people

router = APIRouter(prefix="/api/admin/moderation", tags=["admin"], dependencies=[Depends(require_admin)])

# Where an item's photo_path lives, for the admin preview.
PREVIEW_BUCKETS = {**PHOTO_BUCKETS, "post": "hike-photos", "profile": "avatars"}
View = Literal["queue", "held", "hidden", "all"]
Sort = Literal["newest", "most_reported"]


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _clean(cls, value):
        return value.strip() if isinstance(value, str) else value


class SuspendIn(Reason):
    days: int = Field(ge=1, le=config.MAX_SUSPENSION_DAYS)


class ReportRow(BaseModel):
    id: UUID
    reason: str
    details: str | None
    reporter: PersonRef
    counts_toward_hide: bool
    status: str
    created_at: datetime


class AuthorOut(PersonRef):
    email_confirmed: bool | None
    joined: datetime | None
    # "locked" or "suspended" while in force.
    restriction: Literal["locked", "suspended"] | None
    suspended_until: datetime | None
    # Other items of theirs that were held or hidden before.
    previous_items: int


class Score(BaseModel):
    category: str
    score: float


class ItemOut(BaseModel):
    id: UUID
    kind: str
    target_id: UUID
    state: Literal["visible", "held", "hidden"]
    in_queue: bool
    queue_reason: str | None
    child_safety: bool
    text: str | None
    # A short-lived link to look at the photo; never for a child-safety item.
    photo_url: str | None
    has_photo: bool
    # Where it is: the trail of a hike note or photo, what a post was.
    context: str | None
    trail: TrailRef | None
    screening: Literal["passed", "flagged", "unavailable"] | None
    flagged_categories: list[str]
    # Highest first.
    scores: list[Score]
    screened_at: datetime | None
    open_reports: int
    qualifying_reports: int
    reports: list[ReportRow]
    author: AuthorOut
    created_at: datetime
    activity_at: datetime
    decision: str | None
    decision_reason: str | None
    decided_at: datetime | None
    decided_by: PersonRef | None


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    per_page: int
    # Always the whole queue's size, for the tab.
    queue_total: int


def _context(db: Session, item: ModerationItem) -> tuple[str | None, TrailRef | None]:
    if item.kind in ("hike_note", "hike_photo"):
        hike = db.get(HikeLog, item.target_id)
        if hike is None:
            return "The hike has since been deleted", None
        return f"On {hike.trail.name}", TrailRef(id=hike.trail.id, slug=hike.trail.slug, name=hike.trail.name)
    if item.kind == "post":
        post = db.get(ActivityPost, item.target_id)
        if post is None:
            return "The post has since been deleted", None
        if post.kind == "hike" and post.hike_log is not None:
            trail = post.hike_log.trail
            return f"Activity post: hiked {trail.name}", TrailRef(id=trail.id, slug=trail.slug, name=trail.name)
        if post.kind == "milestone":
            milestone = MILESTONES.get(post.milestone)
            return f"Activity post: earned {milestone.title if milestone else post.milestone}", None
        if post.kind == "rank" and post.rank_level and 1 <= post.rank_level <= len(RANKS):
            return f"Activity post: reached {RANKS[post.rank_level - 1][1]}", None
        return f"Activity post ({post.kind})", None
    return None, None


def _items_out(db: Session, services: Services, items: list[ModerationItem]) -> list[ItemOut]:
    ids = [item.id for item in items]
    reports = db.scalars(
        select(ProfileReport).where(ProfileReport.item_id.in_(ids)).order_by(ProfileReport.created_at.desc())
    ).all() if ids else []
    authors = {item.author_id for item in items}
    people = _people(db, {*authors, *(r.reporter_id for r in reports), *(i.decided_by for i in items)})
    accounts = {
        row.id: row for row in db.execute(
            select(AUTH_USERS.c.id, AUTH_USERS.c.created_at, AUTH_USERS.c.email_confirmed_at)
            .where(AUTH_USERS.c.id.in_(authors))
        )
    } if authors else {}
    previous = dict(db.execute(
        select(ModerationItem.author_id, func.count())
        .where(ModerationItem.author_id.in_(authors),
               (ModerationItem.decision == "hidden") | ModerationItem.state.in_(("held", "hidden")))
        .group_by(ModerationItem.author_id)
    ).all()) if authors else {}
    out = []
    for item in items:
        account = accounts.get(item.author_id)
        restricted = db.get(AccountRestriction, item.author_id)
        photo_url = None
        bucket = PREVIEW_BUCKETS.get(item.kind)
        if item.photo_path and bucket and not item.child_safety:
            photo_url = services.media.signed_url(bucket, item.photo_path)
        context, trail = _context(db, item)
        scores = sorted(((k, v) for k, v in (item.scores or {}).items()), key=lambda kv: kv[1], reverse=True)
        out.append(ItemOut(
            id=item.id, kind=item.kind, target_id=item.target_id, state=item.state, in_queue=item.in_queue,
            queue_reason=item.queue_reason, child_safety=item.child_safety, text=item.text,
            photo_url=photo_url, has_photo=bool(item.photo_path or item.quarantine_path),
            context=context, trail=trail, screening=item.screening,
            flagged_categories=list(item.flagged_categories or []),
            scores=[Score(category=k, score=round(float(v), 4)) for k, v in scores],
            screened_at=item.screened_at, open_reports=item.open_reports,
            qualifying_reports=item.qualifying_reports,
            reports=[
                ReportRow(id=r.id, reason=r.reason, details=r.details, reporter=people[r.reporter_id],
                          counts_toward_hide=bool(r.counts_toward_hide), status=r.status, created_at=r.created_at)
                for r in reports if r.item_id == item.id
            ],
            author=AuthorOut(
                **people[item.author_id].model_dump(),
                email_confirmed=(account.email_confirmed_at is not None) if account else None,
                joined=account.created_at if account else None,
                restriction=restriction(db, item.author_id),
                suspended_until=restricted.suspended_until if restricted else None,
                previous_items=max(0, previous.get(item.author_id, 0)
                                   - (1 if item.state != "visible" or item.decision == "hidden" else 0)),
            ),
            created_at=item.created_at, activity_at=item.activity_at, decision=item.decision,
            decision_reason=item.decision_reason, decided_at=item.decided_at,
            decided_by=people.get(item.decided_by) if item.decided_by else None,
        ))
    return out


@router.get("", response_model=ItemPage)
def list_items(
    view: View = "queue",
    sort: Sort = "newest",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    """Child-safety items always come first; then newest (last held,
    edited or reported) or most reported first."""
    query = select(ModerationItem)
    if view == "queue":
        query = query.where(ModerationItem.in_queue.is_(True))
    elif view in ("held", "hidden"):
        query = query.where(ModerationItem.state == view)
    else:
        query = query.where((ModerationItem.in_queue.is_(True)) | (ModerationItem.decision.is_not(None))
                            | ModerationItem.state.in_(("held", "hidden")))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = [ModerationItem.child_safety.desc()]
    if sort == "most_reported":
        order += [ModerationItem.open_reports.desc()]
    order += [ModerationItem.activity_at.desc(), ModerationItem.id]
    rows = db.scalars(query.order_by(*order).offset((page - 1) * per_page).limit(per_page)).all()
    queue_total = db.scalar(select(func.count()).select_from(ModerationItem)
                            .where(ModerationItem.in_queue.is_(True))) or 0
    return ItemPage(items=_items_out(db, services, rows), total=total, page=page, per_page=per_page,
                    queue_total=queue_total)


def _get(db: Session, item_id: UUID) -> ModerationItem:
    item = db.get(ModerationItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That item isn't in the moderation records.")
    return item


def _decide(item: ModerationItem, admin: CurrentUser, decision: str, reason: str | None) -> None:
    item.decision, item.decision_reason = decision, reason
    item.decided_at, item.decided_by = now(), admin.id
    item.in_queue = False


def _email_of(db: Session, user_id: UUID) -> str | None:
    return db.scalar(select(AUTH_USERS.c.email).where(AUTH_USERS.c.id == user_id))


def _send(sender, email) -> bool:
    try:
        sender.send(email)
        return True
    except Exception:  # noqa: BLE001 - the action stands; the admin is told the email didn't go
        return False


@router.post("/{item_id}/approve", response_model=ActionOut)
def approve(item_id: UUID, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    item = _get(db, item_id)
    restore(db, item)
    resolve_reports(db, item, admin.id)
    _decide(item, admin, "approved", None)
    audit(db, admin, "approve_item", user_id=item.author_id, item_id=str(item.id), kind=item.kind,
          child_safety=item.child_safety or None)
    db.commit()
    return ActionOut(message="Approved. It's visible again." if item.text or item.photo_path else "Approved.")


@router.post("/{item_id}/hide", response_model=ActionOut)
def hide(
    item_id: UUID,
    payload: Reason,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    item = _get(db, item_id)
    withhold(db, item, "hidden")
    resolve_reports(db, item, admin.id)
    _decide(item, admin, "hidden", payload.reason)
    audit(db, admin, "hide_item", user_id=item.author_id, item_id=str(item.id), kind=item.kind,
          reason=payload.reason)
    db.commit()
    # Never tip off the author of a child-safety item.
    if item.child_safety:
        return ActionOut(message="Hidden. (No email: child-safety items are never emailed to the author.)")
    to = _email_of(db, item.author_id)
    sent = bool(to) and _send(services.author_sender or services.sender, hidden_email(to, item, payload.reason))
    return ActionOut(message="Hidden, and the author was emailed." if sent
                     else "Hidden. The email to the author didn't send.")


def _target(db: Session, admin: CurrentUser, user_id: UUID, verb: str) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=422, detail=f"You can't {verb} your own account.")
    if is_admin(user_id):
        raise HTTPException(status_code=422, detail=f"You can't {verb} another admin.")


@router.post("/users/{user_id}/warn", response_model=ActionOut)
def warn(
    user_id: UUID,
    payload: Reason,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    _target(db, admin, user_id, "warn")
    to = _email_of(db, user_id)
    if not to:
        raise HTTPException(status_code=404, detail="That account has no email address.")
    if not _send(services.author_sender or services.sender, warning_email(to, payload.reason)):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The warning email didn't send.")
    audit(db, admin, "warn_user", user_id=user_id, reason=payload.reason)
    db.commit()
    return ActionOut(message="Warning sent.")


def _supabase_or_502(services: Services, call: str, *args) -> None:
    if services.supabase is None:
        raise HTTPException(status_code=503, detail="Account actions need SUPABASE_SERVICE_ROLE_KEY on the server.")
    try:
        getattr(services.supabase, call)(*args)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Supabase didn't accept that. Nothing changed.") from None


@router.post("/users/{user_id}/suspend", response_model=ActionOut)
def suspend(
    user_id: UUID,
    payload: SuspendIn,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    _target(db, admin, user_id, "suspend")
    _supabase_or_502(services, "suspend", user_id, payload.days)
    until = now() + timedelta(days=payload.days)
    row = db.get(AccountRestriction, user_id) or AccountRestriction(user_id=user_id)
    row.suspended_until, row.updated_at = until, now()
    db.add(row)
    audit(db, admin, "suspend_user", user_id=user_id, days=payload.days, reason=payload.reason)
    db.commit()
    to = _email_of(db, user_id)
    label = f"{until:%B} {until.day}, {until.year}"
    sent = bool(to) and _send(services.author_sender or services.sender,
                              suspension_email(to, payload.reason, label))
    return ActionOut(message=f"Suspended until {label}." + ("" if sent else " The email to them didn't send."))


@router.post("/users/{user_id}/ban", response_model=ActionOut)
def ban(
    user_id: UUID,
    payload: Reason,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    _target(db, admin, user_id, "ban")
    _supabase_or_502(services, "ban", user_id)
    row = db.get(AccountRestriction, user_id) or AccountRestriction(user_id=user_id)
    row.locked_at, row.lock_reason, row.updated_at = now(), payload.reason, now()
    db.add(row)
    audit(db, admin, "ban_user", user_id=user_id, reason=payload.reason)
    db.commit()
    return ActionOut(message="Banned. They can't sign in or post.")


@router.post("/users/{user_id}/unlock", response_model=ActionOut)
def unlock(
    user_id: UUID,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_moderation_services),
):
    """Lifts a suspension, lock or ban. A profile hidden by the lock stays
    hidden until it's unhidden from the user's page."""
    _target(db, admin, user_id, "unlock")
    _supabase_or_502(services, "unban", user_id)
    row = db.get(AccountRestriction, user_id)
    if row is not None:
        db.delete(row)
    audit(db, admin, "unsuspend_user", user_id=user_id)
    db.commit()
    return ActionOut(message="Lifted. They can sign in and post again.")

