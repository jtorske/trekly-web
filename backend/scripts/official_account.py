"""Make the official @trekly account, and optionally post the starter drafts.

    python -m scripts.official_account              # the account only (idempotent)
    python -m scripts.official_account --drafts     # print the drafts, post nothing
    python -m scripts.official_account --post       # the account, then the drafts not yet posted

Uses DATABASE_URL, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (local by
default; see backend/.env). For hosted, pass .env.hosted's values for one
command, with approval.

The account gets a random password nobody keeps: admins post as @trekly
from /admin/posts. app/labeled_accounts.py does the work.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.database import SessionLocal  # noqa: E402
from app.labeled_accounts import AVATAR_BUCKET, OfficialDraft, ensure_official, post_drafts  # noqa: E402
from app.supabase_admin import supabase_admin_from_env  # noqa: E402
from app.trail_photos import storage_from_env  # noqa: E402

# Shown to the user before anything is posted on hosted. Newest last.
DRAFTS = [
    OfficialDraft(
        "Welcome to the Activity feed! When hikers share a hike or earn a badge, it shows up here. "
        "Log a hike and tick “Share to Activity” to join in. You can turn sharing off any time in Settings → Privacy.",
        days_ago=6,
    ),
    OfficialDraft(
        "New: 31 Parks Canada backcountry trails added, with their campgrounds. Open a trail, pick a campsite "
        "and set an alert: we'll email you when a spot opens up.",
        days_ago=5,
    ),
    OfficialDraft(
        "Featured trail: Lake Agnes Tea House. A steady climb from Lake Louise past Mirror Lake to a tea house "
        "that has served hikers for more than a century. The tea house is closed for the season now, but the "
        "trail makes a fine shoulder-season walk with microspikes.",
        trail=("Lake Agnes Tea House", "AB"),
        days_ago=3,
    ),
    OfficialDraft(
        "Featured trail: Elfin Lakes in Garibaldi Provincial Park. Once the snow comes it's a classic snowshoe "
        "with big views of the Garibaldi massif. Staying overnight at the shelter needs a reservation through BC Parks.",
        trail=("Elfin Lakes", "BC"),
        days_ago=2,
    ),
    OfficialDraft(
        "November tip: the days are short now. Start early, carry a headlamp even on a day hike, and check "
        "avalanche.ca before heading above the treeline.",
        days_ago=0,
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--drafts", action="store_true", help="print the starter posts and exit")
    group.add_argument("--post", action="store_true", help="post the starter drafts not yet posted")
    args = parser.parse_args()

    if args.drafts:
        for draft in DRAFTS:
            trail = f"  [trail: {draft.trail[0]}, {draft.trail[1]}]" if draft.trail else ""
            print(f"- {draft.body}{trail}\n")
        return

    auth = supabase_admin_from_env()
    if auth is None:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    db = SessionLocal()
    try:
        user_id, made = ensure_official(db, auth, storage_from_env(AVATAR_BUCKET))
        print(f"@trekly {'created' if made else 'already exists'} ({user_id})")
        if args.post:
            posted = post_drafts(db, DRAFTS)
            print(f"posted {len(posted)} new drafts ({len(DRAFTS) - len(posted)} were already posted)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
