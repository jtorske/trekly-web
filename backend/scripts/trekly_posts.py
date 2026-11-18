"""Automatic @trekly posts: the daily run, a preview, and the fact bank seed.

Run from backend/:

    python scripts/trekly_posts.py run          # draft today's posts, publish one if allowed, send the digest
    python scripts/trekly_posts.py preview      # print what today's generators would draft; writes nothing
    python scripts/trekly_posts.py seed-facts   # load config/trekly_facts_seed.json (unapproved; safe to rerun)

`run` is idempotent: drafts are keyed (dedupe_key), at most one post goes out
a day, and the digest is sent once a day, so running it twice changes nothing.
ANTHROPIC_API_KEY (optional) turns on the AI wording; EMAIL_BACKEND and
RESEND_* send the digest (app/notify.py); TREKLY_POSTS_DIGEST_TO overrides
who gets it. Exit code 0 when the run finished or was skipped, 1 on errors.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.trail import Trail  # noqa: E402
from app.models.trekly_post import TreklyFact  # noqa: E402
from app.notify import email_sender_from_env  # noqa: E402
from app.trekly_posts import service, writer  # noqa: E402
from app.trekly_posts.config import load_config  # noqa: E402
from app.trekly_posts.generators import GENERATORS, GenContext  # noqa: E402

SEED_PATH = Path(__file__).resolve().parents[1] / "config" / "trekly_facts_seed.json"


def run() -> int:
    config = load_config()
    db = SessionLocal()
    try:
        client = writer.client_from_env(config.ai.model, config.ai.max_chars) if config.ai.enabled else None
        report = service.run_daily(
            db, config, now=datetime.now(timezone.utc), client=client, sender=email_sender_from_env(),
            recipients=service.digest_recipients(db), holder=os.getenv("GITHUB_RUN_ID", "cli"),
        )
    finally:
        db.close()
    print(f"trekly posts: {report.summary()}")
    for note in report.notes:
        print(f"  - {note}")
    return 1 if any("failed" in note for note in report.notes) else 0


def preview() -> int:
    config = load_config()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        ctx = GenContext(db=db, config=config, today=service.local_today(config, now), now=now)
        for name, generate in GENERATORS.items():
            scheduled = "today" if config.type(name).runs_on(ctx.today) else "not today"
            candidate = generate(ctx) if config.type(name).enabled else None
            print(f"[{name}] ({scheduled}{'' if config.type(name).enabled else ', off'})")
            print(f"  {candidate.template_body if candidate else '(nothing to post)'}")
            if candidate and candidate.source_url:
                print(f"  source: {candidate.source_url}")
        for note in ctx.notes:
            print(f"  - {note}")
    finally:
        db.rollback()
        db.close()
    return 0


def seed_facts() -> int:
    facts = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    db = SessionLocal()
    added = 0
    try:
        for item in facts:
            if db.scalar(select(TreklyFact.id).where(TreklyFact.seed_key == item["key"])):
                continue
            trail_id = None
            if item.get("trail"):
                query = select(Trail.id).where(Trail.name == item["trail"], Trail.retired_at.is_(None))
                if item.get("province"):
                    query = query.where(Trail.province_code == item["province"])
                trail_id = db.scalar(query.limit(1))
                if trail_id is None:
                    print(f"  ! {item['key']}: trail {item['trail']!r} not found; saved without it")
            db.add(TreklyFact(text=item["text"], source_url=item["source_url"], park_name=item.get("park"),
                              trail_id=trail_id, approved=False, seed_key=item["key"]))
            added += 1
        db.commit()
    finally:
        db.close()
    print(f"fact bank: added {added} of {len(facts)} (all unapproved)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("run", "preview", "seed-facts"))
    args = parser.parse_args()
    return {"run": run, "preview": preview, "seed-facts": seed_facts}[args.command]()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
