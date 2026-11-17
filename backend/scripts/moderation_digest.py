"""Email the admin what's new in the moderation queue, if anything is.

Run from backend/ by any cron, e.g. hourly (.github/workflows/moderation-digest.yml):

    python scripts/moderation_digest.py

New held or reported content also tries to send a digest straight away;
this run catches whatever arrived within the hour after the last one. At
most one digest goes out per DIGEST_INTERVAL (app/moderation_config.py),
however often this runs. EMAIL_BACKEND picks how mail is sent (app/notify.py).

Exit code 0 when it sent or had nothing to do, 1 on errors.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.moderation import maybe_send_digest  # noqa: E402
from app.notify import email_sender_from_env  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        sent = maybe_send_digest(db, email_sender_from_env())
    except Exception as error:  # noqa: BLE001
        print(f"moderation digest failed: {type(error).__name__}")
        return 1
    finally:
        db.close()
    print("moderation digest: sent" if sent else "moderation digest: nothing new, or one went out within the hour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
