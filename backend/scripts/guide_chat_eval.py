"""Run the chat scripts (tests/guide/chat_scripts.py) against the REAL provider.

    GROQ_API_KEY=... python scripts/guide_chat_eval.py            # every script
    GROQ_API_KEY=... python scripts/guide_chat_eval.py weekend_plan winter_snowshoe

Uses the committed trail catalogue in an in-memory database and a sample
hiker (four day hikes in Kananaskis/Banff); nothing is read from or written
to any real database, and no user data is sent. Each script is one real
chat turn (a few provider requests), so the full run uses about 60-100 of
the free tier's daily requests.

Checks per script (the same rules CI applies to the mocked runs):
- every tool call's arguments validated (refused calls are listed);
- the reply names no trail the tools didn't return (guard not triggered);
- no "safe", under ~90 words, avalanche.ca on winter answers;
- the script's own expectations where they don't depend on the mock
  (tools called, cards shown, fallback mode).
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401
from app.guide.chat import run_chat  # noqa: E402
from app.guide.estimate import TrailFacts  # noqa: E402
from app.guide.llm.config import GuideChatConfig, chat_config, provider_from_config  # noqa: E402
from app.guide.profile import HikeRecord, StatedPreferences, build_profile  # noqa: E402
from app.guide.tools import TOOLS, ToolContext  # noqa: E402
from app.models.trail import Trail  # noqa: E402
from tests.guide.chat_scripts import SCRIPTS  # noqa: E402
from tests.guide.conftest import seed_catalogue  # noqa: E402

TODAY = date.today()
# Scripts that only make sense against the mock (they test our own failure handling).
MOCK_ONLY = {"rate_limited", "provider_down", "too_many_rounds", "hallucinated_trail_name", "says_safe",
             "bad_arguments_then_fixed", "extra_argument_refused", "unknown_tool", "ambiguous_name"}


class Recording:
    """Wraps the real provider to record its tool calls."""

    def __init__(self, inner):
        self.inner, self.name, self.calls = inner, inner.name, []

    def chat(self, messages, tools):
        result = self.inner.chat(messages, tools)
        self.calls += result.tool_calls
        return result


def main(names: list[str]) -> int:
    config = chat_config()
    config = GuideChatConfig(**{**config.__dict__, "enabled": True})
    provider = provider_from_config(config)
    if provider is None:
        print("Set GROQ_API_KEY (and optionally GUIDE_LLM_MODEL) to run this against the real provider.")
        return 2

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in
                                             ("trails", "trail_photos", "trail_route_maps", "trail_seasonal_conditions")])
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_catalogue(db)
    rows = {t.id: t for t in db.query(Trail).filter(Trail.retired_at.is_(None))}
    facts = [TrailFacts.from_trail(t, TODAY) for t in rows.values()]
    by_slug = {f.slug: f for f in facts}
    profile = build_profile(
        [HikeRecord(by_slug[s], date(2026, 7, 1), 200) for s in ("ha-ling-peak", "prairie-mountain",
                                                                   "sulphur-skyline", "rawson-lake")],
        StatedPreferences(experience_level="few_seasons"), home_province="AB")
    catalogue_names = {f.name for f in facts}

    rows_out = []
    for script in SCRIPTS:
        if (names and script.name not in names) or script.name in MOCK_ONLY:
            continue
        recorder = Recording(provider)
        ctx = ToolContext(profile=profile, facts=facts, rows=rows, today=TODAY, db=db,
                          shown_ids={by_slug[s].id for s in script.shown_slugs})
        reply = run_chat(recorder, script.turns, ctx, catalogue_names, TODAY)
        problems = []
        refused = []
        for call in recorder.calls:
            model = TOOLS.get(call.name, (None, None, None))[1]
            try:
                if model is None:
                    raise ValueError("unknown tool")
                model.model_validate(json.loads(call.arguments or "{}"))
            except Exception as error:  # noqa: BLE001
                refused.append(f"{call.name}: {str(error)[:60]}")
        if refused:
            problems.append(f"refused args: {refused}")
        if reply.mode != "chat":
            problems.append(f"mode {reply.mode} ({reply.reason})")
        if reply.guarded:
            problems.append("guard replaced the reply (unknown trail name or 'safe')")
        if len(reply.text.split()) > 90:
            problems.append(f"{len(reply.text.split())} words")
        expect = script.expect
        if expect.get("avalanche") and "avalanche.ca" not in reply.text:
            problems.append("no avalanche.ca")
        if expect.get("no_tools") and recorder.calls:
            problems.append(f"called tools: {[c.name for c in recorder.calls]}")
        wanted = set(expect.get("tools", []))
        if wanted and not wanted <= {c.name for c in recorder.calls}:
            problems.append(f"expected tools {sorted(wanted)}, got {[c.name for c in recorder.calls]}")
        if expect.get("min_cards") and len(reply.cards) < expect["min_cards"]:
            problems.append("no cards")
        for text in expect.get("text_lacks", []):
            if text.lower() in reply.text.lower():
                problems.append(f"reply contains {text!r}")
        rows_out.append((script.name, "PASS" if not problems else "FAIL", "; ".join(problems),
                         reply.text.replace("\n", " ")[:110]))

    width = max(len(r[0]) for r in rows_out) if rows_out else 10
    print(f"{'script':<{width}}  result  problems / reply")
    for name, verdict, problems, text in rows_out:
        print(f"{name:<{width}}  {verdict:<6}  {problems or text}")
    failed = sum(1 for r in rows_out if r[1] == "FAIL")
    print(f"\n{len(rows_out) - failed}/{len(rows_out)} passed against {provider!r}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
