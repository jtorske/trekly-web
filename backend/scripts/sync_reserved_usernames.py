"""Sync public.reserved_usernames with config/reserved_usernames.txt.

The file is the list; the table is the database's copy, used by the profile
triggers (migration 5d1c0e7a9b42). Run after editing the file. Names already
held by someone are reported, not taken away.

Run from backend/:
    python scripts/sync_reserved_usernames.py --dry-run   # show what would change
    python scripts/sync_reserved_usernames.py
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.usernames import load_reserved  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes, then roll back")
    args = parser.parse_args()

    wanted = load_reserved()
    db = SessionLocal()
    try:
        current = set(db.scalars(text("SELECT name FROM public.reserved_usernames")))
        added, removed = sorted(wanted - current), sorted(current - wanted)
        for name in added:
            db.execute(text("INSERT INTO public.reserved_usernames (name) VALUES (:name)"), {"name": name})
        if removed:
            db.execute(text("DELETE FROM public.reserved_usernames WHERE name = ANY(:names)"), {"names": removed})
        held = sorted(db.scalars(
            text("SELECT username FROM public.profiles WHERE lower(username) = ANY(:names)"),
            {"names": sorted(wanted)},
        ))
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print(f"{'DRY RUN - nothing committed. ' if args.dry_run else ''}Reserved usernames: {len(wanted)}")
    print(f"  added: {', '.join(added) or 'none'}")
    print(f"  removed: {', '.join(removed) or 'none'}")
    if held:
        print(f"  already held (left as they are): {', '.join(held)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
