"""Dog rules for each trail, from catalog_data/trail_dogs.json.

Like trail_winter.py: the file is the whole record, a trail it doesn't list
gets 'unknown', and every rule comes from an official source (its URL is
required, with the date it was checked_on). Nothing is inferred.

A rule can expire (expires_on, e.g. a park bulletin that runs to a set
date). From the day after, it no longer counts: effective_policy() falls
back to 'unknown' ("Check dog rules"), never to allowed, and the admin
overview counts it under "dog rules expired, re-check" (expired_rules()).
sync_dogs() writes an expired rule as 'unknown' too.

scripts/trail_dogs.py writes the file onto a database (dry run by default).
"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.trail import DOG_POLICIES, Trail

DOGS_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trail_dogs.json"
FIELDS = ("dog_policy", "dog_policy_source_url", "dog_policy_note")
DEFAULTS = {"dog_policy": "unknown", "dog_policy_source_url": None, "dog_policy_note": None}


class DogDataError(ValueError):
    pass


def _date(label: str, field: str, value) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise DogDataError(f"{label}: {field} must be a YYYY-MM-DD date") from None


def validate(entry: dict) -> dict:
    label = f"{entry.get('name')} ({entry.get('province_code')})"
    values = {**DEFAULTS, **{f: entry[f] for f in FIELDS if f in entry}}
    if values["dog_policy"] not in DOG_POLICIES:
        raise DogDataError(f"{label}: dog_policy {values['dog_policy']!r} is not one of {DOG_POLICIES}")
    url = values["dog_policy_source_url"]
    if values["dog_policy"] != "unknown" and not url:
        raise DogDataError(f"{label}: a dog rule needs its official source URL")
    if url and not url.startswith("https://"):
        raise DogDataError(f"{label}: dog_policy_source_url must be an https URL")
    checked_on = _date(label, "checked_on", entry.get("checked_on"))
    expires_on = _date(label, "expires_on", entry.get("expires_on"))
    if values["dog_policy"] != "unknown" and checked_on is None:
        raise DogDataError(f"{label}: a dog rule needs the date it was checked_on")
    if expires_on and checked_on and expires_on < checked_on:
        raise DogDataError(f"{label}: expires_on is before checked_on")
    return {**values, "checked_on": checked_on, "expires_on": expires_on}


@lru_cache
def load_dogs(path: Path = DOGS_PATH) -> dict[tuple[str, str | None], dict]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        trails = json.load(f)["trails"]
    out = {}
    for entry in trails:
        key = (entry["name"], entry["province_code"])
        if key in out:
            raise DogDataError(f"{key}: listed twice")
        out[key] = validate(entry)
    return out


def is_expired(rule: dict, today: date) -> bool:
    return rule.get("expires_on") is not None and today > rule["expires_on"]


def effective_policy(name: str, province_code: str | None, stored: str, today: date,
                     dogs: dict | None = None) -> str:
    """The rule that counts today: an expired rule falls back to 'unknown'."""
    rule = (load_dogs() if dogs is None else dogs).get((name, province_code))
    if rule is not None and is_expired(rule, today):
        return "unknown"
    return stored or "unknown"


def expired_rules(today: date, dogs: dict | None = None) -> list[tuple[str, str | None]]:
    """Rules past their expires_on: re-check them against the official source."""
    dogs = load_dogs() if dogs is None else dogs
    return [key for key, rule in dogs.items() if is_expired(rule, today)]


def sync_dogs(db: Session, dogs: dict[tuple[str, str | None], dict],
              today: date | None = None) -> list[tuple[str, dict]]:
    """Write the dog fields onto every active trail (caller commits). Expired
    rules are written as 'unknown'."""
    today = today or date.today()
    changed = []
    for trail in db.query(Trail).filter(Trail.retired_at.is_(None)).order_by(Trail.popularity_rank).all():
        rule = dogs.get((trail.name, trail.province_code))
        wanted = DEFAULTS if rule is None or is_expired(rule, today) else rule
        diff = {}
        for field in FIELDS:
            if getattr(trail, field) != wanted[field]:
                diff[field] = (getattr(trail, field), wanted[field])
                setattr(trail, field, wanted[field])
        if diff:
            changed.append((trail.name, diff))
    db.flush()
    return changed


def unmatched(db: Session, dogs: dict[tuple[str, str | None], dict]) -> list[tuple[str, str | None]]:
    live = {(n, p) for n, p in db.query(Trail.name, Trail.province_code).filter(Trail.retired_at.is_(None))}
    return [key for key in dogs if key not in live]
