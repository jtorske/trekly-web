"""Load photo search results into trail_photo_candidates for the review page.

Reads the output of scripts/find_trail_photos.py and matches each trail to
the target database by (name, province_code), the trails' unique key, so a
database gets its own trail ids. Every candidate is validated first (image
host, https source page, license, a real credit), and nothing is written if
any check fails. Review decisions and approved photos are never touched.

Run from backend/ (DATABASE_URL picks the database; backend/.env is local):

    python scripts/load_photo_candidates.py photo_candidates.json --dry-run
    python scripts/load_photo_candidates.py photo_candidates.json

Writing anywhere but a local database also needs --confirm-host <hostname>,
matching the DATABASE_URL host, so a hosted write is always deliberate.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import inspect

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.models.trail import Trail
from app.models.trail_photo import TrailPhotoCandidates
from app.trail_photos import allowed_fetch_url

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CONFIDENCES = {"high", "medium", "low", "off_topic"}
SOURCES = {"commons", "openverse"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@dataclass
class LoadPlan:
    rows: list[TrailPhotoCandidates] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)      # in the file, not in the database
    missing: list[str] = field(default_factory=list)        # live trails with no entry in the file
    problems: list[str] = field(default_factory=list)       # invalid candidates (nothing is written)
    replaced: int = 0                                       # trails that already had candidates
    table_exists: bool = True                               # migration aa84e0d9e26b has run


def candidate_problem(c: dict) -> str | None:
    for key in ("id", "source", "confidence", "title", "preview_url", "image_url", "photographer",
                "license", "source_url", "width", "height"):
        if c.get(key) in (None, ""):
            return f"missing {key}"
    if c["source"] not in SOURCES:
        return f"unknown source {c['source']!r}"
    if c["confidence"] not in CONFIDENCES:
        return f"unknown confidence {c['confidence']!r}"
    if not allowed_fetch_url(c["image_url"]):
        return f"image host not allowed: {urlsplit(c['image_url']).hostname}"
    if urlsplit(c["source_url"]).scheme != "https":
        return "source page is not https"
    if urlsplit(c["preview_url"]).scheme != "https":
        return "preview is not https"
    if EMAIL.search(c["photographer"]):
        return "photographer name is an email address"
    if not (isinstance(c["width"], int) and isinstance(c["height"], int) and c["width"] > c["height"] > 0):
        return "not a landscape size"
    return None


def plan_load(db, data: dict) -> LoadPlan:
    plan = LoadPlan()
    trails = {(t.name, t.province_code): t for t in db.query(Trail).all()}
    live = {
        key for key, t in trails.items()
        if t.retired_at is None and t.country_code in TRAIL_CATALOG_COUNTRIES
        and t.popularity_rank is not None and t.popularity_rank <= TRAIL_CATALOG_LIMIT
    }
    # A dry run works before migration aa84e0d9e26b; a write doesn't.
    plan.table_exists = inspect(db.get_bind()).has_table(TrailPhotoCandidates.__tablename__)
    existing = {row.trail_id for row in db.query(TrailPhotoCandidates.trail_id).all()} if plan.table_exists else set()
    searched_on = date.fromisoformat(data["generated"]) if data.get("generated") else None
    seen = set()
    for entry in data.get("trails", []):
        key = (entry["name"], entry.get("province_code"))
        label = f"{entry['name']} ({entry.get('province_code') or '-'})"
        trail = trails.get(key)
        if trail is None:
            plan.unmatched.append(label)
            continue
        seen.add(key)
        candidates = entry.get("candidates", [])
        for c in candidates:
            problem = candidate_problem(c)
            if problem:
                plan.problems.append(f"{label} {c.get('id', '?')}: {problem}")
        ids = {c.get("id") for c in candidates}
        if entry.get("default_choice") and entry["default_choice"] not in ids:
            plan.problems.append(f"{label}: default choice {entry['default_choice']} is not among its candidates")
        plan.replaced += trail.id in existing
        plan.rows.append(TrailPhotoCandidates(
            trail_id=trail.id,
            destination=entry.get("destination"),
            best_confidence=entry.get("best_confidence"),
            default_choice=entry.get("default_choice"),
            low_res=bool(entry.get("low_res")),
            candidates=candidates,
            searched_on=searched_on,
        ))
    plan.missing = sorted(f"{name} ({province or '-'})" for name, province in live - seen)
    return plan


def apply_plan(db, plan: LoadPlan) -> None:
    if not plan.table_exists:
        raise ValueError("trail_photo_candidates doesn't exist yet: run migration aa84e0d9e26b first")
    if plan.problems:
        raise ValueError(f"{len(plan.problems)} invalid candidates; nothing written")
    for row in plan.rows:
        db.merge(row)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("candidates", help="output of scripts/find_trail_photos.py")
    parser.add_argument("--dry-run", action="store_true", help="report what would be loaded; write nothing")
    parser.add_argument("--confirm-host", help="required to write to a non-local database: its hostname")
    args = parser.parse_args()

    from app.database import SessionLocal, engine

    host = engine.url.host or ""
    local = host in LOCAL_HOSTS
    print(f"Target database host: {host} ({'local' if local else 'NOT local'})")
    if not args.dry_run and not local and args.confirm_host != host:
        sys.exit(f"Refusing to write to {host}: pass --confirm-host {host} to confirm.")

    data = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        plan = plan_load(db, data)
        with_any = sum(1 for r in plan.rows if r.candidates)
        print(f"Trails in file: {len(data.get('trails', []))}")
        print(f"Matched: {len(plan.rows)} ({with_any} with candidates, "
              f"{sum(len(r.candidates) for r in plan.rows)} candidates, "
              f"{sum(1 for r in plan.rows if r.default_choice)} start on a photo, "
              f"{sum(1 for r in plan.rows if r.low_res)} low-res fallback)")
        print(f"Already loaded (would be replaced): {plan.replaced}"
              + ("" if plan.table_exists else "  [trail_photo_candidates doesn't exist yet: migrate first]"))
        print(f"Unmatched (in file, not in database): {len(plan.unmatched)}")
        for label in plan.unmatched:
            print(f"  - {label}")
        print(f"Live trails with no entry in the file: {len(plan.missing)}")
        for label in plan.missing:
            print(f"  - {label}")
        print(f"Invalid candidates: {len(plan.problems)}")
        for problem in plan.problems:
            print(f"  - {problem}")
        if args.dry_run:
            db.rollback()
            print("Dry run: nothing written.")
            return
        apply_plan(db, plan)
        print(f"Loaded {len(plan.rows)} trails.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
