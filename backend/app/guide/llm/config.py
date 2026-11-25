"""Chat configuration from the environment (see app/guide/llm/__init__.py)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.guide.llm.base import ChatProvider

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_USER_DAILY_LIMIT = 25
# Each message can take up to 5 provider requests (4 tool rounds + the
# reply); Groq's free tier allows on the order of 1,000 requests a day.
DEFAULT_GLOBAL_DAILY_LIMIT = 150


@dataclass(frozen=True)
class GuideChatConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str | None
    user_daily_limit: int
    global_daily_limit: int

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, default)))
    except ValueError:
        return default


def chat_config() -> GuideChatConfig:
    provider = os.getenv("GUIDE_LLM_PROVIDER", "groq").strip().lower() or "groq"
    key = os.getenv("GROQ_API_KEY") if provider == "groq" else None
    return GuideChatConfig(
        enabled=os.getenv("GUIDE_ENABLED", "").strip().lower() == "true",
        provider=provider,
        model=os.getenv("GUIDE_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        api_key=key or None,
        user_daily_limit=_int("GUIDE_USER_DAILY_LIMIT", DEFAULT_USER_DAILY_LIMIT),
        global_daily_limit=_int("GUIDE_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT),
    )


def provider_from_config(config: GuideChatConfig) -> ChatProvider | None:
    """The configured provider, or None when chat is off or has no key."""
    if not config.available:
        return None
    if config.provider == "groq":
        from app.guide.llm.groq import GroqProvider

        return GroqProvider(config.api_key, config.model)
    return None
