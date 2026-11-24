"""Winter use of each trail, from catalog_data/trail_winter.json.

The file is the whole record: a trail it doesn't list gets the defaults (no
winter activities, avalanche exposure 'unknown'), so removing an entry and
syncing again resets the trail. Every value comes from an official source
(Parks Canada, Alberta Parks, BC Parks, park winter guides); nothing is
inferred.

Safety rules, enforced here and by the trails table's check constraints:
- avalanche_exposure other than 'unknown' (including 'none') needs the URL
  of the official ATES rating it came from;
- winter activities need the URL of the source that lists the trail for them;
- winter_route_ends (only part of the trail is a winter route) needs activities.

scripts/trail_winter.py writes the file onto a database (dry run by default).
"""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.trail import Trail

WINTER_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trail_winter.json"

WINTER_ACTIVITIES = ("winter_hike", "snowshoe", "xc_ski")
AVALANCHE_EXPOSURES = ("none", "simple", "challenging", "complex", "unknown")
FIELDS = ("winter_activities", "avalanche_exposure", "avalanche_source_url",
          "winter_access_note", "winter_notes", "winter_route_ends", "winter_source_url",
          "winter_report_url")
DEFAULTS = {
    "winter_activities": [],
    "avalanche_exposure": "unknown",
    "avalanche_source_url": None,
    "winter_access_note": None,
    "winter_notes": None,
    "winter_route_ends": None,
    "winter_source_url": None,
    "winter_report_url": None,
}


class WinterDataError(ValueError):
    pass


def validate(entry: dict) -> dict:
    """The entry's winter fields, defaults filled in; raises WinterDataError."""
    label = f"{entry.get('name')} ({entry.get('province_code')})"
    values = {**DEFAULTS, **{f: entry[f] for f in FIELDS if f in entry}}
    activities = values["winter_activities"]
    if not isinstance(activities, list) or len(set(activities)) != len(activities):
        raise WinterDataError(f"{label}: winter_activities must be a list without repeats")
    unknown = [a for a in activities if a not in WINTER_ACTIVITIES]
    if unknown:
        raise WinterDataError(f"{label}: unknown winter activities {unknown}")
    # Stored in a fixed order so a re-sync of the same file changes nothing.
    values["winter_activities"] = [a for a in WINTER_ACTIVITIES if a in activities]
    if values["avalanche_exposure"] not in AVALANCHE_EXPOSURES:
        raise WinterDataError(f"{label}: avalanche_exposure {values['avalanche_exposure']!r} is not an ATES class")
    if values["avalanche_exposure"] != "unknown" and not values["avalanche_source_url"]:
        raise WinterDataError(f"{label}: an avalanche rating needs its official source URL")
    if values["winter_route_ends"] and not activities:
        raise WinterDataError(f"{label}: winter_route_ends only applies to a winter route")
    if activities and not values["winter_source_url"]:
        raise WinterDataError(f"{label}: winter activities need a source URL")
    for field in ("avalanche_source_url", "winter_source_url", "winter_report_url"):
        url = values[field]
        if url and not url.startswith("https://"):
            raise WinterDataError(f"{label}: {field} must be an https URL")
    return values


@lru_cache
def load_winter(path: Path = WINTER_PATH) -> dict[tuple[str, str | None], dict]:
    """Validated winter fields keyed by (name, province_code)."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        trails = json.load(f)["trails"]
    out = {}
    for entry in trails:
        key = (entry["name"], entry["province_code"])
        if key in out:
            raise WinterDataError(f"{key}: listed twice")
        out[key] = validate(entry)
    return out


def sync_winter(db: Session, winter: dict[tuple[str, str | None], dict]) -> list[tuple[str, dict]]:
    """Write the winter fields onto every active trail (caller commits).

    Listed trails get their entry, the rest the defaults. Never inserts or
    retires a trail. Returns [(trail name, {field: (old, new)})] for changes."""
    changed = []
    for trail in db.query(Trail).filter(Trail.retired_at.is_(None)).order_by(Trail.popularity_rank).all():
        wanted = winter.get((trail.name, trail.province_code), DEFAULTS)
        diff = {}
        for field in FIELDS:
            current, value = getattr(trail, field), wanted[field]
            if current != value:
                diff[field] = (current, value)
                setattr(trail, field, list(value) if isinstance(value, list) else value)
        if diff:
            changed.append((trail.name, diff))
    db.flush()
    return changed


def unmatched(db: Session, winter: dict[tuple[str, str | None], dict]) -> list[tuple[str, str | None]]:
    """Entries with no active trail (a typo, or a trail retired since)."""
    live = {(n, p) for n, p in db.query(Trail.name, Trail.province_code).filter(Trail.retired_at.is_(None))}
    return [key for key in winter if key not in live]
