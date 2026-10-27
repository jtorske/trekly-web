"""Username rules: format, the reserved list, availability and suggestions.

Every account needs a username (it's the profile's address, /u/{username}).
The same rules are enforced three times: here for the API, by the database
(format check, a unique index on lower(username), and a trigger against
public.reserved_usernames; see migration 5d1c0e7a9b42), and in the sign-up
and "choose your username" forms, which ask the API rather than keep a copy.

Picking a username never changes privacy settings.
"""

import re
import secrets
import unicodedata
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import USERNAME_PATTERN, Profile

RESERVED_FILE = Path(__file__).resolve().parents[1] / "config" / "reserved_usernames.txt"
MIN_LENGTH, MAX_LENGTH = 3, 30

FORMAT_MESSAGE = "Use 3–30 lowercase letters, numbers or underscores."
RESERVED_MESSAGE = "That username is reserved. Pick another."
TAKEN_MESSAGE = "That username is taken."
REQUIRED_MESSAGE = "Choose a username."


def load_reserved(path: Path = RESERVED_FILE) -> frozenset[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip().lower()
        if name:
            names.add(name)
    return frozenset(names)


RESERVED_USERNAMES = load_reserved()


def normalize(value: str) -> str:
    return value.strip().lower()


def rule_problem(username: str) -> str | None:
    """Why `username` (already normalized) can't be used by anyone, or None."""
    if not re.fullmatch(USERNAME_PATTERN, username):
        return FORMAT_MESSAGE
    if username in RESERVED_USERNAMES:
        return RESERVED_MESSAGE
    return None


def is_taken(db: Session, username: str, by_other_than: UUID | None = None) -> bool:
    query = select(Profile.id).where(func.lower(Profile.username) == username.lower())
    if by_other_than is not None:
        query = query.where(Profile.id != by_other_than)
    return db.scalar(query.limit(1)) is not None


def base_from_hint(hint: str) -> str:
    """A valid-looking username from a display name or email: "Jordan Törske" -> "jordan_torske"."""
    hint = hint.strip()
    if "@" in hint:
        hint = hint.split("@", 1)[0]
    ascii_hint = unicodedata.normalize("NFKD", hint).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_hint.lower()).strip("_")
    # Leave room for a number on the end.
    base = base[: MAX_LENGTH - 4].rstrip("_")
    if len(base) < MIN_LENGTH:
        base = f"{base}_hiker" if base else "hiker"
    return base


def suggest(db: Session, hint: str) -> str:
    """The first free, allowed name from `hint`: jordan_torske, then jordan_torske2, 3, …"""
    base = base_from_hint(hint)
    candidates = [base] + [f"{base}{n}" for n in range(2, 100)]
    taken = set(db.scalars(select(func.lower(Profile.username)).where(func.lower(Profile.username).in_(candidates))))
    for candidate in candidates:
        if candidate not in taken and rule_problem(candidate) is None:
            return candidate
    # Practically unreachable; a random tail keeps it free.
    return f"{base[:20]}_{secrets.token_hex(3)}"
