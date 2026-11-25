"""Groq's OpenAI-compatible chat completions API (free tier).

Groq doesn't keep API inputs by default; it may log them for up to 30 days
for abuse investigations unless the organisation opts out (Zero Data
Retention in the console's Data Controls). We send only what
app/guide/chat.py builds: the system prompt, the last few chat turns with
emails and phone numbers stripped, and tool results made of trail data and
the hiker's numbers. No names, usernames, emails, ids or post text.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.guide.llm.base import ChatResult, ProviderError, ProviderRateLimited, ToolCall

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT_SECONDS = 25
MAX_REPLY_TOKENS = 400


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, url: str = GROQ_URL):
        self.model = model
        self.url = url
        # A closure, not an attribute, so the key never shows in a dump or a log.
        self._headers = lambda: {"Authorization": f"Bearer {api_key}"}

    def __repr__(self) -> str:
        return f"GroqProvider(model={self.model!r})"

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": MAX_REPLY_TOKENS,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={**self._headers(), "Content-Type": "application/json", "User-Agent": "trekly-api/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in (413, 429) or error.code == 498:
                raise ProviderRateLimited(f"HTTP {error.code}") from None
            raise ProviderError(f"HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise ProviderError(type(error).__name__) from None
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("no message in the response") from None
        calls = [
            ToolCall(id=str(call.get("id") or f"call_{i}"), name=str(call["function"]["name"]),
                     arguments=str(call["function"].get("arguments") or "{}"))
            for i, call in enumerate(message.get("tool_calls") or [])
            if isinstance(call, dict) and call.get("function", {}).get("name")
        ]
        text = message.get("content")
        return ChatResult(text=text.strip() if isinstance(text, str) and text.strip() else None, tool_calls=calls)
