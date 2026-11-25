"""Trekly Guide chat endpoints (signed-in only).

- GET  /api/guide/chat/status   whether chat is on for them, and messages left today
- POST /api/guide/chat          one message -> {mode, text, cards, quick_replies}

Nothing a user writes is stored: the browser keeps the conversation for the
session and sends the last few turns each time. The server keeps counts
only (app/models/guide_chat.py): messages per user per day for the cap, and
daily totals for the admin area.

Order for each message: kill switch / key -> daily caps -> moderation of the
message (the existing OpenAI screen; flagged is refused, unavailable lets it
through) -> the model and tools (app/guide/chat.py). Anything that stops
chat answers mode "fallback_to_form" and the browser shows the guided form.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.guide.chat import MAX_TURNS, run_chat, scrub
from app.guide.llm import ChatProvider, GuideChatConfig, chat_config, provider_from_config
from app.guide.profile import get_hiker_profile
from app.guide.tools import ToolContext
from app.models.guide_chat import GuideChatMetrics, GuideChatUsage
from app.moderation import Services, get_moderation_services
from app.routers.availability import get_today
from app.routers.guide import facts_of, load_catalogue

router = APIRouter(prefix="/api/guide/chat", tags=["trekly guide"])

MAX_USER_CHARS = 600
MAX_ASSISTANT_CHARS = 1200

CAP_TEXT = ("You've used today's Trekly Guide messages ({limit}). "
            "The planner below still works, and chat is back tomorrow.")
BLOCKED_TEXT = "I can't help with that. Ask me about trails, trips or gear and I'll find you a hike."


def get_chat_config() -> GuideChatConfig:
    """FastAPI dependency; tests override it."""
    return chat_config()


def get_chat_provider(config: GuideChatConfig = Depends(get_chat_config)) -> ChatProvider | None:
    """FastAPI dependency; tests override it with a scripted provider."""
    return provider_from_config(config)


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_ASSISTANT_CHARS)


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[TurnIn] = Field(min_length=1, max_length=MAX_TURNS)
    # Trails already shown in this conversation, for "show me more".
    shown_trail_ids: list[UUID] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _last_is_user(self):
        last = self.messages[-1]
        if last.role != "user":
            raise ValueError("the last message must be the user's")
        if len(last.content) > MAX_USER_CHARS:
            raise ValueError(f"keep messages under {MAX_USER_CHARS} characters")
        return self


class ChatOut(BaseModel):
    mode: Literal["chat", "fallback_to_form", "blocked"]
    text: str = ""
    cards: list[dict] = []
    quick_replies: list[str] = []
    # disabled | user_cap | global_cap | rate_limited | provider_error
    reason: str | None = None
    remaining_today: int


class StatusOut(BaseModel):
    available: bool
    remaining_today: int
    daily_limit: int


def _usage(db: Session, user_id: UUID, today: date) -> GuideChatUsage:
    row = db.get(GuideChatUsage, (user_id, today))
    if row is None:
        row = GuideChatUsage(user_id=user_id, day=today, messages=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.get(GuideChatUsage, (user_id, today))
    return row


def _metrics(db: Session, today: date) -> GuideChatMetrics:
    row = db.get(GuideChatMetrics, today)
    if row is None:
        row = GuideChatMetrics(day=today, **{name: 0 for name in (
            "messages", "tool_calls", "fallbacks", "provider_errors", "rate_limited",
            "moderation_blocked", "cap_reached", "guarded")})
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.get(GuideChatMetrics, today)
    return row


def _count(db: Session, today: date, **increments: int) -> None:
    row = _metrics(db, today)
    for name, value in increments.items():
        setattr(row, name, (getattr(row, name) or 0) + value)


def _remaining(db: Session, user_id: UUID, today: date, config: GuideChatConfig) -> int:
    row = db.get(GuideChatUsage, (user_id, today))
    return max(0, config.user_daily_limit - (row.messages if row else 0))


@router.get("/status", response_model=StatusOut)
def chat_status(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    config: GuideChatConfig = Depends(get_chat_config),
    provider: ChatProvider | None = Depends(get_chat_provider),
    today: date = Depends(get_today),
):
    remaining = _remaining(db, user.id, today, config)
    metrics = db.get(GuideChatMetrics, today)
    global_left = config.global_daily_limit - (metrics.messages if metrics else 0)
    return StatusOut(available=provider is not None and remaining > 0 and global_left > 0,
                     remaining_today=remaining, daily_limit=config.user_daily_limit)


@router.post("", response_model=ChatOut)
def chat(
    body: ChatIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    config: GuideChatConfig = Depends(get_chat_config),
    provider: ChatProvider | None = Depends(get_chat_provider),
    services: Services = Depends(get_moderation_services),
    today: date = Depends(get_today),
):
    if provider is None:
        return ChatOut(mode="fallback_to_form", reason="disabled", remaining_today=0)

    usage = _usage(db, user.id, today)
    metrics = _metrics(db, today)
    if usage.messages >= config.user_daily_limit or metrics.messages >= config.global_daily_limit:
        reason = "user_cap" if usage.messages >= config.user_daily_limit else "global_cap"
        _count(db, today, cap_reached=1, fallbacks=1)
        db.commit()
        text = CAP_TEXT.format(limit=config.user_daily_limit) if reason == "user_cap" else (
            "Trekly Guide is resting for today. The planner below still works.")
        return ChatOut(mode="fallback_to_form", reason=reason, text=text,
                       remaining_today=max(0, config.user_daily_limit - usage.messages))

    usage.messages += 1
    _count(db, today, messages=1)
    db.commit()
    remaining = max(0, config.user_daily_limit - usage.messages)

    message = body.messages[-1].content
    if services.screener is not None:
        try:
            verdict = services.screener.screen(scrub(message), None)
        except Exception:  # noqa: BLE001 - screening down: the message only goes to the chat model
            verdict = None
        if verdict is not None and verdict.flagged:
            _count(db, today, moderation_blocked=1)
            db.commit()
            return ChatOut(mode="blocked", text=BLOCKED_TEXT, quick_replies=["Plan this weekend", "An easy hike"],
                           remaining_today=remaining)

    catalogue = load_catalogue(db)
    ctx = ToolContext(
        profile=get_hiker_profile(db, user.id),
        facts=facts_of(catalogue, today),
        rows=catalogue,
        today=today,
        db=db,
        shown_ids=set(body.shown_trail_ids),
    )
    reply = run_chat(provider, [t.model_dump() for t in body.messages], ctx,
                     {t.name for t in catalogue.values()}, today)
    increments = {"tool_calls": reply.tool_calls}
    if reply.mode == "fallback_to_form":
        increments["fallbacks"] = 1
        increments["rate_limited" if reply.reason == "rate_limited" else "provider_errors"] = 1
    if reply.guarded:
        increments["guarded"] = 1
    _count(db, today, **increments)
    db.commit()
    return ChatOut(mode=reply.mode, text=reply.text, cards=reply.cards, quick_replies=reply.quick_replies,
                   reason=reply.reason, remaining_today=remaining)
