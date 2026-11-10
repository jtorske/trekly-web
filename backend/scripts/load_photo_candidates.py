"""Load photo search results into trail_photo_candidates for the review page.

Reads the output of scripts/find_trail_photos.py and matches each trail to
the target database by (name, province_code), the trails' unique key, so a
database gets its own trail ids. Every candidate is validated first (image
host, https source page, license, a real credit), and nothing is written if
any check fails. Review decisions and approved photos are never touched:
a trail that already has a photo is skipped, and a trail whose new search
found nothing keeps its earlier candidates.

Run from backend/ (DATABASE_URL picks the database; backend/.env is local):

    python scripts/load_photo_candidates.py photo_candidates.json --dry-run
    python scripts/load_photo_candidates.py photo_candidates.json

Writing anywhere but a local database also needs --confirm-host <hostname>,
matching the DATABASE_URL host, so a hosted write is always deliberate.

Pixabay's image links expire within a day and it doesn't allow permanent
hotlinking, so before writing, each Pixabay candidate is looked up again by
id (PIXABAY_API_KEY), downloaded, re-encoded as WebP and copied to the
trail-photos bucket under candidates/ (SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY of the target); the candidate then points at the
copy. A dry run only checks the lookups.
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import inspect
from sqlalchemy.orm import noload

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.models.trail import Trail
from app.models.trail_photo import TrailPhoto, TrailPhotoCandidates
from app.trail_photos import CANDIDATE_PREFIX, allowed_fetch_url, is_candidate_copy, public_photo_url, storage_from_env

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CONFIDENCES = {"high", "medium", "park", "low", "off_topic"}
SOURCES = {"commons", "openverse", "pixabay", "pexels"}
PIXABAY_API = "https://pixabay.com/api/"
STOCK_CLIENT = "Trekly-photo-loader/1.0"
COPY_QUALITY = 92  # the approve step re-encodes again, so keep this copy close to the source
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@dataclass
class LoadPlan:
    rows: list[TrailPhotoCandidates] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)      # in the file, not in the database
    missing: list[str] = field(default_factory=list)        # live trails with no entry in the file
    problems: list[str] = field(default_factory=list)       # invalid candidates (nothing is written)
    replaced: int = 0                                       # trails that already had candidates
    has_photo: list[str] = field(default_factory=list)      # skipped: an approved or uploaded photo
    kept_earlier: list[str] = field(default_factory=list)   # skipped: nothing new found, earlier candidates stay
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
    # Our own copies (candidates/ in the bucket) follow SUPABASE_URL, which is http locally.
    if urlsplit(c["preview_url"]).scheme != "https" and not is_candidate_copy(c["preview_url"]):
        return "preview is not https"
    if EMAIL.search(c["photographer"]):
        return "photographer name is an email address"
    if not (isinstance(c["width"], int) and isinstance(c["height"], int) and c["width"] > c["height"] > 0):
        return "not a landscape size"
    return None


# ---------------------------------------------------------------- Pixabay copies

def _get(url: str, timeout=60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": STOCK_CLIENT})
    for wait in (0, 10, 30):
        time.sleep(wait or 0.7)  # Pixabay allows 100 requests a minute
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(20 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503):
                raise RuntimeError(f"HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            pass
    raise RuntimeError("no response")


def pixabay_lookup(image_id: str, key: str) -> dict | None:
    """Fresh links for one Pixabay image (they expire), or None if it's gone."""
    query = urllib.parse.urlencode({"key": key, "id": image_id})
    try:
        hits = json.loads(_get(f"{PIXABAY_API}?{query}")).get("hits") or []
    except RuntimeError as error:
        # The message never includes the request URL (it holds the key).
        raise RuntimeError(f"Pixabay lookup for {image_id} failed ({error})") from None
    return hits[0] if hits else None


def _webp(data: bytes) -> tuple[bytes, int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, "WEBP", quality=COPY_QUALITY, method=6)
        return out.getvalue(), image.width, image.height


def copy_paths(image_id: str) -> tuple[str, str]:
    return f"{CANDIDATE_PREFIX}pixabay-{image_id}.webp", f"{CANDIDATE_PREFIX}pixabay-{image_id}-preview.webp"


def copy_pixabay(data: dict, write: bool, log=print) -> tuple[int, list[str]]:
    """Point each Pixabay candidate at a copy in our bucket (made when `write`).
    Returns (candidates copied or checked, problems). A Pixabay image that's
    been taken down is dropped from its trail's candidates."""
    candidates = [c for t in data.get("trails", []) for c in t.get("candidates", []) if c.get("source") == "pixabay"]
    if not candidates:
        return 0, []
    key = (os.getenv("PIXABAY_API_KEY") or "").strip()
    if not key:
        return 0, ["PIXABAY_API_KEY isn't set: Pixabay candidates can't be copied"]
    storage = storage_from_env() if write else None
    if write and storage is None:
        return 0, ["SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY aren't set: Pixabay candidates can't be copied"]
    problems, done, gone = [], 0, set()
    for c in candidates:
        image_id = c["id"].split(":", 1)[1]
        try:
            hit = pixabay_lookup(image_id, key)
            if hit is None or hit.get("isAiGenerated"):
                gone.add(c["id"])
                log(f"  Pixabay {image_id} is no longer available; dropped")
                continue
            hero_path, preview_path = copy_paths(image_id)
            if write:
                hero, width, height = _webp(_get(hit["largeImageURL"]))
                preview, _, _ = _webp(_get(hit["webformatURL"]))
                storage.upload(hero_path, hero, upsert=True)
                storage.upload(preview_path, preview, upsert=True)
                c["width"], c["height"] = width, height
            c["image_url"], c["preview_url"] = public_photo_url(hero_path), public_photo_url(preview_path)
            done += 1
        except Exception as error:  # noqa: BLE001 - reported, nothing written
            problems.append(f"pixabay {image_id}: {error}")
    for trail in data.get("trails", []):
        if any(c["id"] in gone for c in trail.get("candidates", [])):
            trail["candidates"] = [c for c in trail["candidates"] if c["id"] not in gone]
            if trail.get("default_choice") in gone:
                trail["default_choice"] = None
    return done, problems


def plan_load(db, data: dict) -> LoadPlan:
    plan = LoadPlan()
    # Columns only: a dry run must work before the photo migrations have run there.
    trails = {(t.name, t.province_code): t for t in db.query(Trail).options(noload("*")).all()}
    live = {
        key for key, t in trails.items()
        if t.retired_at is None and t.country_code in TRAIL_CATALOG_COUNTRIES
        and t.popularity_rank is not None and t.popularity_rank <= TRAIL_CATALOG_LIMIT
    }
    # A dry run works before migration aa84e0d9e26b; a write doesn't.
    plan.table_exists = inspect(db.get_bind()).has_table(TrailPhotoCandidates.__tablename__)
    existing = {row.trail_id for row in db.query(TrailPhotoCandidates.trail_id).all()} if plan.table_exists else set()
    with_photo = {row.trail_id for row in db.query(TrailPhoto.trail_id).all()}
    # Set explicitly: merge() on an existing row leaves the server default alone,
    # and the review page compares this with the trail's last decision.
    loaded_at = datetime.now(timezone.utc)
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
        if trail.id in with_photo:
            plan.has_photo.append(label)
            continue
        if not candidates and trail.id in existing:
            plan.kept_earlier.append(label)
            continue
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
            loaded_at=loaded_at,
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
    # A dry run checks each Pixabay image is still there; a write copies it first.
    copied, copy_problems = copy_pixabay(data, write=not args.dry_run)
    if copied or copy_problems:
        print(f"Pixabay candidates {'copied to Storage' if not args.dry_run else 'still available (to copy)'}: {copied}")
    for problem in copy_problems:
        print(f"  - {problem}")
    if copy_problems and not args.dry_run:
        sys.exit("Some Pixabay copies failed; nothing written to the database. Rerun to retry.")
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
        print(f"Skipped, already has a photo: {len(plan.has_photo)}")
        for label in plan.has_photo:
            print(f"  - {label}")
        print(f"Skipped, nothing new found (earlier candidates kept): {len(plan.kept_earlier)}")
        for label in plan.kept_earlier:
            print(f"  - {label}")
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
