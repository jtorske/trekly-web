"""Stand-ins for what moderation reaches outside the database: the OpenAI
screener, Storage, email and the Supabase admin API."""

from __future__ import annotations

from app.moderation import Screening, ScreeningUnavailable, Services


class FakeScreener:
    """Passes everything unless told otherwise. `flag` maps a word (found in
    a text) or a photo path to the categories it trips; `down` makes every
    call fail like an outage."""

    def __init__(self, flag: dict[str, list[str]] | None = None, down: bool = False):
        self.flag = flag or {}
        self.down = down
        self.calls: list[tuple[str | None, bytes | None]] = []

    def screen(self, text, image):
        self.calls.append((text, image[0] if image else None))
        if self.down:
            raise ScreeningUnavailable("timeout")
        hits: list[str] = []
        for needle, categories in self.flag.items():
            if (text and needle in text) or (image and needle.encode() == image[0]):
                hits += categories
        scores = {"harassment": 0.01, "sexual": 0.01, "sexual/minors": 0.0, "violence": 0.01}
        for category in hits:
            scores[category] = 0.97
        from app import moderation_config as config

        return Screening(flagged=bool(hits), child_safety=any(c in config.CHILD_SAFETY_CATEGORIES for c in hits),
                         scores=scores, categories=sorted(set(hits)), model="omni-moderation-test")


class FakeMedia:
    """A photo's bytes are its path, so FakeScreener can flag a path."""

    def __init__(self):
        self.quarantined: list[tuple[str, str]] = []

    def read(self, bucket, path):
        return path.encode(), "image/webp"

    def quarantine(self, bucket, path):
        self.quarantined.append((bucket, path))
        return f"{bucket}/{path}"

    def signed_url(self, bucket, path):
        return f"https://storage.test/{bucket}/{path}?signed"


class Outbox:
    def __init__(self, fail: bool = False):
        self.sent = []
        self.fail = fail

    def send(self, email) -> None:
        if self.fail:
            raise RuntimeError("mail server down")
        self.sent.append(email)


class FakeSupabase:
    def __init__(self, fail: bool = False):
        self.calls: list[tuple] = []
        self.fail = fail

    def _call(self, *call):
        if self.fail:
            raise RuntimeError("supabase down")
        self.calls.append(call)

    def ban(self, user_id):
        self._call("ban", user_id)

    def suspend(self, user_id, days):
        self._call("suspend", user_id, days)

    def unban(self, user_id):
        self._call("unban", user_id)


def fake_services(screener=None, outbox=None, author_outbox=None, media=None, supabase=None) -> Services:
    """Fresh per request (as in the app), sharing the fakes passed in."""
    return Services(screener=screener if screener is not None else FakeScreener(), media=media or FakeMedia(),
                    sender=outbox if outbox is not None else Outbox(),
                    author_sender=author_outbox if author_outbox is not None else Outbox(),
                    supabase=supabase if supabase is not None else FakeSupabase())
