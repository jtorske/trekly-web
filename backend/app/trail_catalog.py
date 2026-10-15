"""Sync the trails table with the curated catalogue in catalog_data/.

The JSON file is the source of truth: the top N entries (by rank) for the
configured countries are upserted on (name, province_code) and become the
live catalogue; every other trail is retired (retired_at set, rank cleared),
never deleted, so bookmarks, seasonal conditions and campsites survive.
Re-running with unchanged inputs changes nothing.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.trail import Trail

CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trails_canada.json"

# Fields copied from a catalogue entry onto the trail row.
TRAIL_FIELDS = (
    "region", "country_code", "province_code", "latitude", "longitude",
    "elevation_gain_m", "max_elevation_m", "terrain_difficulty",
    "typical_duration_nights", "climate_zone", "description",
)


@dataclass
class SyncResult:
    inserted: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    unchanged: int = 0


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def select_entries(catalog: dict, countries: tuple[str, ...], limit: int) -> list[dict]:
    """Top `limit` entries in the given countries, ordered by editorial rank."""
    entries = [t for t in catalog["trails"] if t["country_code"] in countries]
    return sorted(entries, key=lambda t: t["rank"])[:limit]


def popularity_score(rank: int, total: int) -> Decimal:
    """Linear score from rank: 1.0000 for #1 down to 1/total for the last."""
    return (Decimal(total - rank + 1) / Decimal(total)).quantize(Decimal("0.0001"))


def _normalize(name: str, value):
    if value is None:
        return None
    if name in ("latitude", "longitude"):
        return Decimal(str(value)).quantize(Decimal("0.000001"))
    if name == "popularity_score":
        return Decimal(value).quantize(Decimal("0.0001"))
    return value


def sync_trails(
    db: Session,
    catalog: dict,
    countries: tuple[str, ...],
    limit: int,
    now: datetime | None = None,
) -> SyncResult:
    """Apply the catalogue to the database (caller commits)."""
    now = now or datetime.now(timezone.utc)
    source = catalog["meta"]["popularity_source"]
    selected = select_entries(catalog, countries, limit)
    total = len([t for t in catalog["trails"] if t["country_code"] in countries])
    result = SyncResult()

    existing = {(t.name, t.province_code): t for t in db.query(Trail).all()}
    live_ids = set()

    for position, entry in enumerate(selected, 1):
        wanted = {name: _normalize(name, entry.get(name)) for name in TRAIL_FIELDS}
        wanted["popularity_rank"] = position
        wanted["popularity_score"] = popularity_score(entry["rank"], total)
        wanted["popularity_source"] = source

        trail = existing.get((entry["name"], entry["province_code"]))
        if trail is None:
            trail = Trail(name=entry["name"], **wanted, popularity_updated_at=now)
            db.add(trail)
            db.flush()
            result.inserted.append(entry["name"])
        else:
            changed = {
                name: value for name, value in wanted.items()
                if _normalize(name, getattr(trail, name)) != value
            }
            if trail.retired_at is not None:
                changed["retired_at"] = None
            if changed:
                if {"popularity_rank", "popularity_score", "popularity_source"} & changed.keys():
                    changed["popularity_updated_at"] = now
                for name, value in changed.items():
                    setattr(trail, name, value)
                result.updated.append(entry["name"])
            else:
                result.unchanged += 1
        live_ids.add(trail.id)

    for trail in existing.values():
        if trail.id in live_ids or trail.retired_at is not None:
            continue
        trail.retired_at = now
        trail.popularity_rank = None
        trail.popularity_score = None
        trail.popularity_updated_at = now
        result.retired.append(f"{trail.name} ({trail.region})")

    db.flush()
    return result
