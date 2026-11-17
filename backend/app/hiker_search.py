"""People search and "Hikers you might know".

Matching, ranking and who may appear live in the database, in
private.search_hikers and private.suggest_hikers (migration e6b2d8a4c0f7),
so there's one copy of the rules. In short:

- Matches the username and display name: prefix, substring and (from three
  characters) fuzzy trigram matches, ignoring case and accents. Two
  characters at least.
- Ranks an exact username first, then people the viewer follows, then people
  with trails or home province in common (counting only what the viewer may
  see), then the rest.
- Lists only profiles with a username, not hidden by an admin, not a labeled
  (official or demo) account, not blocked either way, and public or private
  with "Let people find me in search" on.
- Suggestions: people with trails in common or from the viewer's home
  province, who've turned on community features, and whom the viewer doesn't
  already follow (or has asked to).

This module adds what the result rows show. A private profile the viewer
can't open shows only its name, username and photo (and "Request to
follow"); otherwise the rank shows when its owner shows it, the province
when they show it, and "You've both hiked N trails" when their journal is
visible to the viewer.

Search is rate-limited per user and per client IP (SearchLimiter); the
search box debounces, so a person typing stays well under the limits.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.account import Profile
from app.models.privacy import ProfileSettings

MIN_QUERY = 2
MAX_QUERY = 60
PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
SUGGESTIONS = 5


@dataclass(frozen=True)
class SearchHit:
    user_id: UUID
    tier: int
    common_trails: int | None
    """Trails both have hiked; None when their journal isn't visible to the viewer."""
    opened: bool
    """The viewer may see their profile's sections (public, or an approved follower)."""


@dataclass(frozen=True)
class Suggestion:
    user_id: UUID
    common_trails: int
    same_province: bool


class HikerFinder(Protocol):
    def search(self, db: Session, viewer_id: UUID, q: str, limit: int, offset: int) -> list[SearchHit]: ...

    def suggest(self, db: Session, viewer_id: UUID, limit: int) -> list[Suggestion]: ...


class DatabaseHikerFinder:
    """The database's own rules (Postgres only)."""

    def search(self, db: Session, viewer_id: UUID, q: str, limit: int, offset: int) -> list[SearchHit]:
        rows = db.execute(
            text(
                "SELECT user_id, tier, common_trails, opened "
                "FROM private.search_hikers(:viewer, :q, :limit, :offset)"
            ),
            {"viewer": viewer_id, "q": q, "limit": limit, "offset": offset},
        )
        return [SearchHit(UUID(str(r.user_id)), r.tier, r.common_trails, r.opened) for r in rows]

    def suggest(self, db: Session, viewer_id: UUID, limit: int) -> list[Suggestion]:
        rows = db.execute(
            text("SELECT user_id, common_trails, same_province FROM private.suggest_hikers(:viewer, :limit)"),
            {"viewer": viewer_id, "limit": limit},
        )
        return [Suggestion(UUID(str(r.user_id)), r.common_trails, r.same_province) for r in rows]


def normalize_query(q: str | None) -> str:
    """The query as the database will fold it: trimmed, without a leading @."""
    return (q or "").strip().lstrip("@").strip()


@dataclass(frozen=True)
class HikerCard:
    profile: Profile
    is_private: bool
    opened: bool
    show_rank: bool
    show_province: bool
    common_trails: int | None
    same_province: bool = False


def cards(db: Session, viewer_id: UUID, entries: list[tuple[UUID, bool, int | None, bool]]) -> list[HikerCard]:
    """(user_id, opened, common_trails, same_province) -> what each row may show, in order."""
    ids = [entry[0] for entry in entries]
    if not ids:
        return []
    profiles = {p.id: p for p in db.scalars(select(Profile).where(Profile.id.in_(ids)))}
    settings = {s.user_id: s for s in db.scalars(select(ProfileSettings).where(ProfileSettings.user_id.in_(ids)))}
    out = []
    for user_id, opened, common_trails, same_province in entries:
        profile, setting = profiles.get(user_id), settings.get(user_id)
        if profile is None or setting is None or not profile.username:
            continue  # gone since the search ran
        out.append(HikerCard(
            profile=profile,
            is_private=bool(setting.is_private),
            opened=opened,
            show_rank=opened and bool(setting.show_rank),
            show_province=opened and bool(setting.show_home_province) and profile.home_province is not None,
            common_trails=common_trails if opened and setting.show_journal else None,
            same_province=same_province,
        ))
    return out


class SearchLimiter:
    """Sliding-window limits per user and per client IP, in memory.

    Per process: each API instance counts on its own, which is enough to stop
    one client scraping the directory. A refused request doesn't count.
    """

    def __init__(self, per_user: int = 60, per_ip: int = 120, window: float = 60.0, clock=time.monotonic):
        self.per_user, self.per_ip, self.window, self.clock = per_user, per_ip, window, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _ip_key(ip: str) -> str:
        return "ip:" + hashlib.sha256(f"trekly-search:{ip}".encode()).hexdigest()

    def _trim(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def check(self, user_id: UUID, ip: str) -> float | None:
        """Count one request; None if allowed, else seconds until it would be."""
        now = self.clock()
        keys = ((f"user:{user_id}", self.per_user), (self._ip_key(ip), self.per_ip))
        with self._lock:
            waits = []
            for key, limit in keys:
                hits = self._hits[key]
                self._trim(hits, now)
                if len(hits) >= limit:
                    waits.append(hits[0] + self.window - now)
            if waits:
                return max(max(waits), 1.0)
            for key, _ in keys:
                self._hits[key].append(now)
            # Forget idle keys now and then, so memory stays bounded.
            if len(self._hits) > 10_000:
                for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - self.window]:
                    del self._hits[key]
            return None
