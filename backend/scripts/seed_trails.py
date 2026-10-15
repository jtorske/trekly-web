"""Sync the trails table with catalog_data/trails_canada.json.

Keeps the top TRAIL_CATALOG_LIMIT trails in TRAIL_CATALOG_COUNTRIES (see
app/config.py) and retires every other trail. Idempotent; retired trails are
never deleted. See app/trail_catalog.py.

Run from backend/:
    python scripts/seed_trails.py --dry-run   # show what would change
    python scripts/seed_trails.py
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.database import SessionLocal
from app.trail_catalog import load_catalog, sync_trails


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes, then roll back")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = sync_trails(db, load_catalog(), TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT)
        print(f"Countries: {','.join(TRAIL_CATALOG_COUNTRIES)}  limit: {TRAIL_CATALOG_LIMIT}")
        for label, names in (("Inserted", result.inserted), ("Updated", result.updated), ("Retired", result.retired)):
            print(f"{label}: {len(names)}")
            for name in names:
                print(f"  - {name}")
        print(f"Unchanged: {result.unchanged}")
        if args.dry_run:
            db.rollback()
            print("Dry run: rolled back, nothing written.")
        else:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
