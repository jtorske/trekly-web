"""Dog rules for each trail, from catalog_data/trail_dogs.json.

Like trail_winter.py: the file is the whole record, a trail it doesn't list
gets 'unknown', and every rule comes from an official park source (its URL
is required). Nothing is inferred: Trekly Guide's dog filter only keeps
trails marked on_leash, so a missing entry just leaves a trail out.

scripts/trail_dogs.py writes the file onto a database (dry run by default).
"""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.trail import DOG_POLICIES, Trail

DOGS_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trail_dogs.json"
FIELDS = ("dog_policy", "dog_policy_source_url", "dog_policy_note")
DEFAULTS = {"dog_policy": "unknown", "dog_policy_source_url": None, "dog_policy_note": None}


class DogDataError(ValueError):
    pass


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
    return values


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


def sync_dogs(db: Session, dogs: dict[tuple[str, str | None], dict]) -> list[tuple[str, dict]]:
    """Write the dog fields onto every active trail (caller commits)."""
    changed = []
    for trail in db.query(Trail).filter(Trail.retired_at.is_(None)).order_by(Trail.popularity_rank).all():
        wanted = dogs.get((trail.name, trail.province_code), DEFAULTS)
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
