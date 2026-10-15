"""Seed trail ↔ campground links and booking systems from catalog_data/trail_campgrounds.json.

Idempotent: links are upserted, links to retired sites are kept and reported,
and links taken out of the file are removed. See app/trail_campgrounds.py.
Run after scripts/seed_trails.py and scripts/sync_backcountry.py.

Run from backend/:
    python scripts/seed_trail_campgrounds.py --dry-run   # show what would change
    python scripts/seed_trail_campgrounds.py
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.trail_campgrounds import load_mapping, seed_trail_campgrounds  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes, then roll back")
    args = parser.parse_args()

    mapping = load_mapping()
    db = SessionLocal()
    try:
        report = seed_trail_campgrounds(db, mapping)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print(f"{'DRY RUN - nothing committed. ' if args.dry_run else ''}Trail campgrounds:")
    print(f"  links: {report.links_created} new, {report.links_updated} updated, "
          f"{report.links_unchanged} unchanged, {len(report.links_removed)} removed")
    print(f"  booking systems: {report.booking_created} new, {report.booking_updated} updated, "
          f"{report.booking_unchanged} unchanged, {len(report.booking_removed)} removed")
    for label, rows in (("Removed links", report.links_removed),
                        ("Removed booking systems", report.booking_removed),
                        ("Links to retired sites (kept)", report.retired_links),
                        ("Warnings", report.warnings)):
        if rows:
            print(f"\n{label}:")
            for row in rows:
                print(f"  - {row}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
