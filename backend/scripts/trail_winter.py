"""Write catalog_data/trail_winter.json onto the trails in DATABASE_URL.

    python scripts/trail_winter.py report            # the review table (no database)
    python scripts/trail_winter.py sync-db           # dry run: shows the changes, writes nothing
    python scripts/trail_winter.py sync-db --apply   # writes them

Matched by trail name and province; never inserts or retires a trail. Active
trails the file doesn't list are reset to the defaults (no winter
activities, avalanche exposure unknown).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.trail_winter import WINTER_PATH, load_winter, sync_winter, unmatched  # noqa: E402

LABELS = {"winter_hike": "Winter hike", "snowshoe": "Snowshoe", "xc_ski": "XC ski"}


def cmd_report(_args):
    winter = load_winter()
    flags = {(t["name"], t["province_code"]): t.get("review_flag")
             for t in json.loads(WINTER_PATH.read_text(encoding="utf-8"))["trails"]}
    print("| Trail | Activities | ATES | Access note | Source | Flag |")
    print("|---|---|---|---|---|---|")
    for (name, province), w in winter.items():
        acts = ", ".join(LABELS[a] for a in w["winter_activities"]) or "Not recommended"
        sources = " ".join(u for u in (w["winter_source_url"], w["avalanche_source_url"]) if u)
        print(f"| {name} ({province}) | {acts} | {w['avalanche_exposure']} | {w['winter_access_note'] or ''} "
              f"| {sources} | {flags.get((name, province)) or ''} |")


def cmd_sync_db(args):
    from app.database import SessionLocal

    winter = load_winter()
    db = SessionLocal()
    try:
        missing = unmatched(db, winter)
        if missing:
            print("No active trail for:", ", ".join(f"{n} ({p})" for n, p in missing))
        changed = sync_winter(db, winter)
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
