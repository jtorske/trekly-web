"""Check active campground alerts and email anyone whose stay has opened up.

Run from backend/ by any cron or worker, e.g. every 5-10 minutes:

    python scripts/poll_alerts.py

Overlapping runs are refused (a lease in job_locks), and a run that starts
less than ALERT_POLL_MIN_INTERVAL_MINUTES (default 10) after the previous one
exits straight away, so a too-eager schedule can't raise the request rate.
Each run makes at most ALERT_POLL_MAX_REQUESTS (default 20) Parks Canada
requests, within the global per-minute budget shared with the API.
EMAIL_BACKEND picks how mail is sent (see app/notify.py).

Exit code 0 when the run finished or was skipped, 1 on errors.
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import alert_poller  # noqa: E402
from app.backcountry.availability import AvailabilityChecker  # noqa: E402
from app.backcountry.parks_canada import ParksCanadaClient  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.notify import email_sender_from_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-requests", type=int, default=alert_poller.MAX_REQUESTS)
    args = parser.parse_args()

    client = ParksCanadaClient(None, delay_s=2.0, max_retries=4)
    db = SessionLocal()
    try:
        checker = AvailabilityChecker(db, client.get_live)
        report = alert_poller.run_alert_poll(
            db, checker, email_sender_from_env(), max_requests=args.max_requests,
            min_interval=alert_poller.MIN_INTERVAL,
        )
    finally:
        db.close()
    print(f"alert poll: {report.summary()}")
    for error in report.errors:
        print(f"  ! {error}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
