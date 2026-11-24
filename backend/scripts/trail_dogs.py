"""Write catalog_data/trail_dogs.json onto the trails in DATABASE_URL.

    python scripts/trail_dogs.py report            # the review table (no database)
    python scripts/trail_dogs.py sync-db           # dry run: shows the changes, writes nothing
    python scripts/trail_dogs.py sync-db --apply   # writes them

Matched by trail name and province; never inserts or retires a trail. Active
trails the file doesn't list are reset to dog_policy 'unknown'.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.trail_dogs import load_dogs, sync_dogs, unmatched  # noqa: E402


def cmd_report(_args):
    dogs = load_dogs()
    print("| Trail | Dogs | Note | Source | Checked | Expires |")
    print("|---|---|---|---|---|---|")
    for (name, province), d in dogs.items():
        print(f"| {name} ({province}) | {d['dog_policy']} | {d['dog_policy_note'] or ''} "
              f"| {d['dog_policy_source_url'] or ''} | {d['checked_on'] or ''} | {d['expires_on'] or ''} |")


def cmd_sync_db(args):
    from app.database import SessionLocal

    dogs = load_dogs()
    db = SessionLocal()
    try:
        missing = unmatched(db, dogs)
        if missing:
            print("No active trail for:", ", ".join(f"{n} ({p})" for n, p in missing))
        changed = sync_dogs(db, dogs)
        for name, diff in changed:
            print(f"  {name}: " + ", ".join(f"{f} {a!r} -> {b!r}" for f, (a, b) in diff.items()))
        print(f"{len(changed)} trails updated")
        if args.apply:
            db.commit()
        else:
            db.rollback()
            print("Dry run: rolled back, nothing written. Add --apply to write.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report", help="print the classification as a review table")
    sync = sub.add_parser("sync-db", help="write the file onto the trails in DATABASE_URL")
    sync.add_argument("--apply", action="store_true", help="commit (default is a dry run)")
    args = parser.parse_args()
    {"report": cmd_report, "sync-db": cmd_sync_db}[args.command](args)


if __name__ == "__main__":
    main()
