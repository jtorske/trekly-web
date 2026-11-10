"""Create or remove the demo hikers, all of them, in one go.

    python -m scripts.demo_accounts create    # makes the ones that don't exist yet
    python -m scripts.demo_accounts remove    # deletes every demo account and every row naming one
    python -m scripts.demo_accounts status    # who's there, and any leftover rows

Demo hikers are labeled "demo" (app/account_labels.py): a "Demo account"
badge wherever their name appears, left out of stats, trending, "Hiked by",
search and suggestions, and they never interact with real users. Their data
is in app/demo_data.py; app/labeled_accounts.py does the work.

Uses DATABASE_URL, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (local by
default; see backend/.env). Run it locally first; hosted needs approval.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.labeled_accounts import AVATAR_BUCKET, create_demo, demo_ids, references, remove_demo  # noqa: E402
from app.models.account import Profile  # noqa: E402
from app.supabase_admin import supabase_admin_from_env  # noqa: E402
from app.trail_photos import storage_from_env  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["create", "remove", "status"])
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.action == "status":
            ids = demo_ids(db)
            names = db.scalars(select(Profile.username).where(Profile.id.in_(ids))).all() if ids else []
            print(f"{len(ids)} demo accounts: {', '.join(sorted(n for n in names if n)) or '-'}")
            print(f"rows naming them: {references(db, ids)}")
            return
        auth = supabase_admin_from_env()
        if auth is None:
            sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        store = storage_from_env(AVATAR_BUCKET)
        if args.action == "create":
            made = create_demo(db, auth, store, date.today(), log=print)
            print(f"created {len(made)} demo accounts")
        else:
            remove_demo(db, auth, store, log=print)
    finally:
        db.close()


if __name__ == "__main__":
    main()
