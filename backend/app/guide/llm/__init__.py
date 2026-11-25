"""Trekly Guide's chat providers behind one interface (base.ChatProvider).

The model only turns the user's words into calls to the deterministic
engine (app/guide/tools.py) and writes a short reply around the results.
Configuration (all optional; see config.py):

    GUIDE_ENABLED=true            kill switch: anything else turns chat off
    GUIDE_LLM_PROVIDER=groq       which provider (only "groq" today)
    GROQ_API_KEY=...              the provider's key; without it chat is off
    GUIDE_LLM_MODEL=...           model id (default openai/gpt-oss-120b)
    GUIDE_USER_DAILY_LIMIT=25     messages per user per day
    GUIDE_GLOBAL_DAILY_LIMIT=150  messages per day across Trekly

When chat is off, capped or the provider fails, the endpoint answers
"fallback_to_form" and the browser shows the Phase 1 planner instead.
"""

from app.guide.llm.base import (  # noqa: F401
    ChatProvider,
    ChatResult,
    ProviderError,
    ProviderRateLimited,
    ToolCall,
)
from app.guide.llm.config import GuideChatConfig, chat_config, provider_from_config  # noqa: F401
