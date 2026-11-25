"""The one interface every chat provider implements.

chat(messages, tools) -> ChatResult with text and/or tool calls. Messages and
tools use the OpenAI-style shapes most providers accept:
- messages: {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
  (assistant messages may carry "tool_calls"; tool messages "tool_call_id")
- tools: [{"type": "function", "function": {"name", "description", "parameters"}}]

A provider raises ProviderRateLimited for quota and rate errors and
ProviderError for anything else; app/guide/chat.py then falls back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    # Raw JSON text from the model; app/guide/tools.py validates it.
    arguments: str


@dataclass(frozen=True)
class ChatResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ProviderError(RuntimeError):
    """The provider couldn't answer (network, 5xx, bad response)."""


class ProviderRateLimited(ProviderError):
    """Quota or rate limit: try later or fall back."""


class ChatProvider(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult: ...
