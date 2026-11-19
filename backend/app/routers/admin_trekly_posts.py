"""The review queue for automatic @trekly posts (/admin/trekly-posts).

Drafts come from the daily run (app/trekly_posts/service.py). Admins preview,
edit, schedule, publish or reject them, switch each type's auto-publish on or
off (defaults in config/trekly_posts.toml), and keep the fact bank. Every publish goes through the
same pacing rules as the daily run (`publish_refusal`) and is audited.

A conditions draft quotes an official bulletin word for word, so its text
can't be edited here: reject it instead.
"""

from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.admin_access import audit, require_admin
from app.auth import CurrentUser
from app.database import get_db
from app.models.trail import Trail
from app.models.trekly_post import (
    DRAFT_STATUSES, MAX_FACT_TEXT, MAX_SOURCE_URL, POST_TYPES, TreklyFact, TreklyPostDraft, TreklyPostTypeSetting,
)
from app.routers.trails import live_trails
from app.schemas.trail import TrailListItemOut
from app.trekly_posts.config import PostsConfig, load_config
from app.trekly_posts.service import (
    PublishRefused, auto_publish_settings, is_busy, local_today, official_posts_on, official_profile, publish, publish_refusal,
)

router = APIRouter(prefix="/api/admin/trekly-posts", tags=["admin"], dependencies=[Depends(require_admin)])

PostType = Literal["trending", "spotlight", "new_on_trekly", "roundup", "fun_fact", "conditions"]
TYPE_LABELS = {
    "trending": "Trending trails",
    "spotlight": "Trail spotlight",
    "new_on_trekly": "New on Trekly",
    "roundup": "Community roundup",
    "fun_fact": "Fun fact",
    "conditions": "Conditions and warnings",
}
NO_STORE = {"Cache-Control": "no-store"}


def get_posts_config() -> PostsConfig:
    return load_config()


def get_now() -> datetime:
    return datetime.now(timezone.utc)


class TypeOut(BaseModel):
    post_type: PostType
    label: str
    enabled: bool
    days: list[str]
    ai: bool
    auto_publish: bool


class DraftOut(BaseModel):
    id: UUID
    post_type: PostType
    status: str
    body: str
    template_body: str
    writer: str
    ai_note: str | None
    trail: TrailListItemOut | None
    source_url: str | None
    source_label: str | None
    source_date: date | None
    data: dict
    run_date: date
    publish_on: date | None
    published_at: datetime | None
    post_id: UUID | None
    created_at: datetime
    # Why "Publish now" would be refused right now (pacing), if it would.
    blocked: str | None = None


class AccountOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None


class QueueOut(BaseModel):
    account: AccountOut | None
    today: date
    posts_today: int
    max_posts_per_day: int
    busy: bool
    types: list[TypeOut]
    counts: dict[str, int]
    drafts: list[DraftOut]


def _draft_out(db, config, draft: TreklyPostDraft, now: datetime, today: date) -> DraftOut:
    trail = draft.trail if draft.trail is not None and draft.trail.retired_at is None else None
    return DraftOut(
        id=draft.id, post_type=draft.post_type, status=draft.status, body=draft.body,
        template_body=draft.template_body, writer=draft.writer, ai_note=draft.ai_note,
        trail=TrailListItemOut.model_validate(trail) if trail else None,
        source_url=draft.source_url, source_label=draft.source_label, source_date=draft.source_date,
        data=draft.data or {}, run_date=draft.run_date, publish_on=draft.publish_on,
        published_at=draft.published_at, post_id=draft.post_id, created_at=draft.created_at,
        blocked=publish_refusal(db, config, draft, now, today) if draft.status in ("draft", "scheduled") else None,
    )


def _types(db: Session, config: PostsConfig) -> list[TypeOut]:
    auto = auto_publish_settings(db, config)
    return [
        TypeOut(post_type=name, label=TYPE_LABELS[name], enabled=config.type(name).enabled,
                days=list(config.type(name).days), ai=config.type(name).ai, auto_publish=auto[name])
        for name in POST_TYPES
    ]


@router.get("", response_model=QueueOut)
def queue(
    response: Response,
    status_filter: Literal["waiting", "published", "closed", "all"] = Query(default="waiting", alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    config: PostsConfig = Depends(get_posts_config),
    now: datetime = Depends(get_now),
):
    response.headers.update(NO_STORE)
    today = local_today(config, now)
    statuses = {
        "waiting": ("draft", "scheduled"), "published": ("published",),
        "closed": ("rejected", "expired"), "all": DRAFT_STATUSES,
    }[status_filter]
    drafts = db.scalars(
        select(TreklyPostDraft).options(joinedload(TreklyPostDraft.trail))
        .where(TreklyPostDraft.status.in_(statuses))
        .order_by(TreklyPostDraft.publish_on.is_(None), TreklyPostDraft.publish_on, TreklyPostDraft.created_at.desc())
        .limit(limit)
    ).all()
    counts = dict(db.execute(select(TreklyPostDraft.status, func.count()).group_by(TreklyPostDraft.status)).all())
    profile = official_profile(db)
    return QueueOut(
        account=AccountOut(username=profile.username or "", display_name=profile.display_name,
                           avatar_path=profile.avatar_path) if profile else None,
        today=today,
        posts_today=official_posts_on(db, config, today),
        max_posts_per_day=config.pacing.max_posts_per_day,
        busy=is_busy(db, config, now, today),
        types=_types(db, config),
        counts={s: int(counts.get(s, 0)) for s in DRAFT_STATUSES},
        drafts=[_draft_out(db, config, d, now, today) for d in drafts],
    )


def _draft(db: Session, draft_id: UUID) -> TreklyPostDraft:
    draft = db.get(TreklyPostDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


def _open(draft: TreklyPostDraft) -> None:
    if draft.status not in ("draft", "scheduled"):
        raise HTTPException(status_code=409, detail=f"This post is already {draft.status}.")


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=500)

    @field_validator("body", mode="before")
    @classmethod
    def _strip(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


@router.patch("/{draft_id}", response_model=DraftOut)
def edit(draft_id: UUID, payload: EditIn, admin: CurrentUser = Depends(require_admin),
         db: Session = Depends(get_db), config: PostsConfig = Depends(get_posts_config),
         now: datetime = Depends(get_now)):
    draft = _draft(db, draft_id)
    _open(draft)
    if draft.post_type == "conditions":
        raise HTTPException(status_code=422, detail="Conditions posts quote the official bulletin word for word, "
                                                    "so they can't be edited. Reject it instead.")
    if payload.body != draft.body:
        draft.body, draft.writer, draft.updated_at = payload.body, "admin", now
        draft.decided_by, draft.decided_at = admin.id, now
    db.commit()
    return _draft_out(db, config, draft, now, local_today(config, now))


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # None takes it back to a plain draft.
    publish_on: date | None


@router.post("/{draft_id}/schedule", response_model=DraftOut)
def schedule(draft_id: UUID, payload: ScheduleIn, admin: CurrentUser = Depends(require_admin),
             db: Session = Depends(get_db), config: PostsConfig = Depends(get_posts_config),
             now: datetime = Depends(get_now)):
    """Approve for a day: the daily run publishes it that day (pacing allowing)."""
    draft = _draft(db, draft_id)
    _open(draft)
    today = local_today(config, now)
    if payload.publish_on is None:
        draft.status, draft.publish_on = "draft", None
    else:
        if payload.publish_on < today:
            raise HTTPException(status_code=422, detail="Pick today or a later day.")
        if (payload.publish_on - today).days > 60:
            raise HTTPException(status_code=422, detail="Pick a day within the next 60 days.")
        draft.status, draft.publish_on = "scheduled", payload.publish_on
    draft.decided_by, draft.decided_at, draft.updated_at = admin.id, now, now
    db.commit()
    return _draft_out(db, config, draft, now, today)


@router.post("/{draft_id}/publish", response_model=DraftOut)
def publish_now(draft_id: UUID, admin: CurrentUser = Depends(require_admin),
                db: Session = Depends(get_db), config: PostsConfig = Depends(get_posts_config),
                now: datetime = Depends(get_now)):
    draft = _draft(db, draft_id)
    today = local_today(config, now)
    try:
        post = publish(db, config, draft, now, today, by=admin.id)
    except PublishRefused as refused:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    audit(db, admin, "official_post", post_id=str(post.id), body=draft.body[:120], draft_id=str(draft.id),
          post_type=draft.post_type)
    db.commit()
    db.refresh(draft)
    return _draft_out(db, config, draft, now, today)


@router.post("/{draft_id}/reject", response_model=DraftOut)
def reject(draft_id: UUID, admin: CurrentUser = Depends(require_admin),
           db: Session = Depends(get_db), config: PostsConfig = Depends(get_posts_config),
           now: datetime = Depends(get_now)):
    draft = _draft(db, draft_id)
    _open(draft)
    draft.status, draft.publish_on = "rejected", None
    draft.decided_by, draft.decided_at, draft.updated_at = admin.id, now, now
    db.commit()
    return _draft_out(db, config, draft, now, local_today(config, now))


class AutoPublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_publish: bool


@router.put("/types/{post_type}", response_model=TypeOut)
def set_auto_publish(post_type: PostType, payload: AutoPublishIn, admin: CurrentUser = Depends(require_admin),
                     db: Session = Depends(get_db), config: PostsConfig = Depends(get_posts_config),
                     now: datetime = Depends(get_now)):
    row = db.get(TreklyPostTypeSetting, post_type)
    if row is None:
        row = TreklyPostTypeSetting(post_type=post_type)
        db.add(row)
    row.auto_publish, row.updated_by, row.updated_at = payload.auto_publish, admin.id, now
    db.commit()
    return next(t for t in _types(db, config) if t.post_type == post_type)


# --- Fact bank ---------------------------------------------------------------

class FactOut(BaseModel):
    id: UUID
    text: str
    trail: TrailListItemOut | None
    park_name: str | None
    source_url: str
    approved: bool
    created_at: datetime
    updated_at: datetime


class FactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_FACT_TEXT)
    source_url: str = Field(min_length=1, max_length=MAX_SOURCE_URL)
    trail_id: UUID | None = None
    park_name: str | None = Field(default=None, max_length=120)
    approved: bool = False

    @field_validator("text", "park_name", mode="before")
    @classmethod
    def _strip(cls, value):
        if isinstance(value, str):
            value = " ".join(value.split())
            return value or None
        return value

    @field_validator("source_url")
    @classmethod
    def _https(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname:
            raise ValueError("Use the full https:// link to the source page.")
        return value


class FactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=MAX_FACT_TEXT)
    source_url: str | None = Field(default=None, min_length=1, max_length=MAX_SOURCE_URL)
    trail_id: UUID | None = None
    park_name: str | None = Field(default=None, max_length=120)
    approved: bool | None = None

    @field_validator("text", "park_name", mode="before")
    @classmethod
    def _strip(cls, value):
        return FactIn._strip(value)

    @field_validator("source_url")
    @classmethod
    def _https(cls, value: str | None) -> str | None:
        return None if value is None else FactIn._https(value)


def _fact_out(fact: TreklyFact) -> FactOut:
    trail = fact.trail if fact.trail is not None and fact.trail.retired_at is None else None
    return FactOut(id=fact.id, text=fact.text, trail=TrailListItemOut.model_validate(trail) if trail else None,
                   park_name=fact.park_name, source_url=fact.source_url, approved=fact.approved,
                   created_at=fact.created_at, updated_at=fact.updated_at)


def _check_trail(db: Session, trail_id: UUID | None) -> None:
    if trail_id is not None and db.scalar(select(Trail.id).where(Trail.id == trail_id, *live_trails())) is None:
        raise HTTPException(status_code=422, detail="That trail isn't in the catalogue.")


@router.get("/facts", response_model=list[FactOut])
def list_facts(response: Response, db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    facts = db.scalars(
        select(TreklyFact).options(joinedload(TreklyFact.trail))
        .order_by(TreklyFact.approved, TreklyFact.created_at, TreklyFact.id)
    ).all()
    return [_fact_out(f) for f in facts]


@router.post("/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED)
def create_fact(payload: FactIn, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db),
                now: datetime = Depends(get_now)):
    _check_trail(db, payload.trail_id)
    fact = TreklyFact(text=payload.text, source_url=payload.source_url, trail_id=payload.trail_id,
                      park_name=payload.park_name, approved=payload.approved, updated_by=admin.id,
                      created_at=now, updated_at=now)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return _fact_out(fact)


@router.patch("/facts/{fact_id}", response_model=FactOut)
def update_fact(fact_id: UUID, payload: FactPatch, admin: CurrentUser = Depends(require_admin),
                db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    fact = db.get(TreklyFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    changes = payload.model_dump(exclude_unset=True)
    if "trail_id" in changes:
        _check_trail(db, changes["trail_id"])
    for key in ("text", "source_url"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=422, detail=f"{key} can't be empty.")
    if "approved" in changes and changes["approved"] is None:
        del changes["approved"]
    for key, value in changes.items():
        setattr(fact, key, value)
    if ("text" in changes or "source_url" in changes) and "approved" not in changes:
        # A changed fact needs approving again.
        fact.approved = False
    fact.updated_by, fact.updated_at = admin.id, now
    db.commit()
    db.refresh(fact)
    return _fact_out(fact)


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(fact_id: UUID, db: Session = Depends(get_db)):
    fact = db.get(TreklyFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    db.delete(fact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
