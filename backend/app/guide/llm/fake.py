"""A scripted provider for tests and CI: no network, no keys.

Give it the ChatResults to return in order; it records every request so a
test can check what would have been sent (data minimisation).
"""

from __future__ import annotations

from app.guide.llm.base import ChatResult, ProviderError


class ScriptedProvider:
    name = "scripted"

    def __init__(self, replies: list):
        """Each reply is a ChatResult, an exception to raise, or a function
        of the messages so far that returns a ChatResult (to answer from the
        tool results it was given)."""
        self.replies = list(replies)
        self.requests: list[dict] = []

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.replies:
            raise ProviderError("script ran out")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(messages)
        return reply
