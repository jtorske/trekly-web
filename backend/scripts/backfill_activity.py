"""Post every hiker's unposted hikes (app/activity.py backfill_posts).

The API does this for one hiker when they open their profile's Activity tab;
this does it for everyone at once, so visitors see the posts too without
waiting for the owner to come back. Safe to rerun: hikes that already have a
post, or that their owner unshared, are left alone.

    python scripts/backfill_activity.py            # list who would get posts
    python scripts/backfill_activity.py --apply    # post them
"""

import argparse
import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from app.activity import backfill_posts, unposted_hikes  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.hike_log import HikeLog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="post them (default: only list)")
    args = parser.parse_args()
    today = date.today()
    db = SessionLocal()
    try:
        users = db.scalars(select(HikeLog.user_id).distinct()).all()
        total = 0
        for user_id in users:
            waiting = db.scalar(select(func.count()).select_from(unposted_hikes(user_id, today).subquery())) or 0
            if not waiting:
                continue
            posted = backfill_posts(db, user_id, today) if args.apply else waiting
            total += posted
            print(f"{user_id}: {posted} hike{'s' if posted != 1 else ''}{' posted' if args.apply else ' to post'}")
        print(f"{'Posted' if args.apply else 'Would post'} {total} hikes.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
