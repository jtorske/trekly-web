"""Medium (~1000 px) renditions for trail photos approved before that size existed.

Trail photos only (trail_photos rows: reviewed candidates and the site
owner's trail photos). Never avatars, gear, journal or post photos: those
live in other buckets and tables this script doesn't read.

Additive only. For each trail photo with no medium_path whose hero is wider
than 1000 px, it downloads the stored hero, writes
`{trail_id}/{uuid}-medium.webp` next to it (upload without upsert, so an
existing object is never overwritten) and fills medium_path. The hero and
thumbnail files and every other column stay as they are. Rerunning skips
photos that already have one.

Run from backend/ (migration d5f8a1c3e7b2 first):

    python scripts/trail_photo_medium.py                  # dry run: count + paths
    python scripts/trail_photo_medium.py --apply          # local database
    python scripts/trail_photo_medium.py --apply --confirm-host <db host>   # anywhere else

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for --apply.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND))

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def has_medium_column(db) -> bool:
    from sqlalchemy import inspect

    return "medium_path" in {column["name"] for column in inspect(db.get_bind()).get_columns("trail_photos")}


def plan(db):
    """(to make, already done, too narrow): trail photo rows. Works before the
    migration too (read-only dry run): then nothing has a medium yet."""
    from types import SimpleNamespace

    from app.models.trail import Trail
    from app.models.trail_photo import TrailPhoto
    from app.trail_photos import MEDIUM_WIDTH

    migrated = has_medium_column(db)
    if migrated:
        rows = (
            db.query(TrailPhoto, Trail.name, Trail.province_code)
            .join(Trail, Trail.id == TrailPhoto.trail_id)
            .order_by(Trail.name)
            .all()
        )
    else:
        rows = [
            (SimpleNamespace(hero_path=hero, hero_width=width, hero_height=height, medium_path=None), name, province)
            for hero, width, height, name, province in db.query(
                TrailPhoto.hero_path, TrailPhoto.hero_width, TrailPhoto.hero_height, Trail.name, Trail.province_code
            )
            .join(Trail, Trail.id == TrailPhoto.trail_id)
            .order_by(Trail.name)
            .all()
        ]
    todo, done, narrow = [], [], []
    for photo, name, province in rows:
        label = f"{name} ({province or '-'})"
        if photo.medium_path:
            done.append((photo, label))
        elif photo.hero_width <= MEDIUM_WIDTH:
            narrow.append((photo, label))
        else:
            todo.append((photo, label))
    return todo, done, narrow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="upload and write; without it, a dry run")
    parser.add_argument("--confirm-host", help="the DATABASE_URL host, required to write anywhere but local")
    args = parser.parse_args(argv)

    from app.database import SessionLocal, engine
    from app.trail_photos import StorageError, medium_from_hero, medium_path_for, storage_from_env

    host = engine.url.host or ""
    local = host in LOCAL_HOSTS
    print(f"Target database host: {host} ({'local' if local else 'NOT local'})")
    if args.apply and not local and args.confirm_host != host:
        sys.exit(f"Refusing to write to {host}: pass --confirm-host {host} to confirm.")

    db = SessionLocal()
    try:
        todo, done, narrow = plan(db)
        print(f"Trail photos: {len(todo) + len(done) + len(narrow)}")
        print(f"  to make: {len(todo)}   already have one: {len(done)}   hero 1000 px or narrower (none needed): {len(narrow)}")
        for photo, label in todo:
            print(f"  + {medium_path_for(photo.hero_path)}   {label}, hero {photo.hero_width}x{photo.hero_height}")
        for photo, label in narrow:
            print(f"  = {label}: hero is {photo.hero_width} px, skipped")
        if not args.apply:
            print("Dry run: nothing uploaded or written.")
            return 0
        if not has_medium_column(db):
            sys.exit("trail_photos.medium_path doesn't exist yet: run migration d5f8a1c3e7b2 first. Nothing written.")

        storage = storage_from_env()
        if storage is None:
            sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are needed to upload.")
        made = failed = 0
        for photo, label in todo:
            path = medium_path_for(photo.hero_path)
            try:
                hero, _ = storage.download(photo.hero_path)
                medium = medium_from_hero(hero)
                if medium is None:
                    print(f"  = {label}: stored hero isn't wider than 1000 px, skipped")
                    continue
                storage.upload(path, medium, upsert=False)
            except (StorageError, OSError, ValueError) as error:
                failed += 1
                print(f"  ! {label}: {error}", flush=True)
                continue
            # One commit per photo: a later failure never orphans a file that's already referenced.
            photo.medium_path = path
            db.commit()
            made += 1
            print(f"  made {path} ({len(medium) // 1024} KB)", flush=True)
        print(f"Made {made} medium renditions; {failed} failed (rerun to retry).")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
