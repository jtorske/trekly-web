"""Automatic @trekly posts: generators, the AI fact check and fallback, pacing,
duplicates, the review queue API, and that warnings never pass through the AI."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.account import SavedTrail
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.models.trail import Trail
from app.models.trail_photo import TrailPhoto
from app.models.trekly_post import TreklyFact, TreklyPostDraft, TreklyPostTypeSetting
from app.notify import Email
from app.routers.admin_trekly_posts import get_now, get_posts_config
from app.main import app
from app.trekly_posts import conditions as cond
from app.trekly_posts import service, writer
from app.trekly_posts.config import ConfigError, load_config, parse_config
from app.trekly_posts.generators import GENERATORS, GenContext
from tests.test_activity import feed, log, person  # noqa: F401  (fixture)
from tests.test_labeled_accounts import ADMIN, admin_headers, auth, official  # noqa: F401  (fixtures)

# Wednesday 2026-09-23, 9 am in Alberta: larch season, spotlight day.
NOW = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 23)

BULLETIN_PAGE = """
<div class="search-alert-results">
  <div class="info">
    <a href="https://parks.canada.ca/pn-np/ab/banff/bulletins/AAAA-1111"><h4 class="x">Trail Closure: Larch Valley Trail</h4></a>
    <span class="text-muted small">September 22, 2026</span>
  </div>
  <div class="info">
    <a href="https://parks.canada.ca/pn-np/ab/banff/bulletins/BBBB-2222"><h4 class="x">Bear Warning: Skoki trails</h4></a>
    <span class="text-muted small">September 01, 2026</span>
  </div>
  <div class="info">
    <a href="https://parks.canada.ca/pn-np/ab/banff/bulletins/CCCC-3333"><h4 class="x">Visitor centre hours</h4></a>
    <span class="text-muted small">September 23, 2026</span>
  </div>
  <div class="info">
    <a href="https://evil.example.com/pn-np/ab/banff/bulletins/DDDD"><h4 class="x">Trail Closure: fake</h4></a>
    <span class="text-muted small">September 23, 2026</span>
  </div>
</div>
"""


def config(auto=None, **overrides):
    """The real config file, with every type on every day unless overridden.
    `auto` forces every type's auto-publish default on or off."""
    import tomllib
    from app.trekly_posts.config import CONFIG_PATH

    raw = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for name in raw["types"]:
        raw["types"][name]["enabled"] = True
        raw["types"][name]["days"] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        if auto is not None:
            raw["types"][name]["auto_publish"] = auto
    for path, value in overrides.items():
        target = raw
        keys = path.split(".")
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value
    return parse_config(raw)


class FakeAI:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.answer(user) if callable(self.answer) else self.answer


class Outbox:
    def __init__(self):
        self.sent: list[Email] = []

    def send(self, email):
        self.sent.append(email)


@pytest.fixture
def trails(session_factory):
    db = session_factory()
    specs = [
        ("Larch Valley", "Banff National Park", 1, ["larch"], 11.6, 535, 2611),
        ("Lake Low", "Banff National Park", 2, [], 5.0, 120, 1500),
        ("Ridge High", "Jasper National Park", 3, [], 14.2, 900, 2500),
        ("Falls Four", "Yoho National Park", 4, [], 3.0, 50, 1300),
    ]
    ids = {}
    for name, park, rank, tags, km, gain, top in specs:
        trail = Trail(name=name, region="Rockies", country_code="CA", province_code="AB", park_name=park,
                      park_type="national", terrain_difficulty="moderate", popularity_rank=rank, tags=tags,
                      distance_km=km, route_type="out_and_back", elevation_gain_m=gain, max_elevation_m=top,
                      created_at=NOW - timedelta(days=400))
        db.add(trail)
        db.flush()
        ids[name] = trail.id
    db.commit()
    db.close()
    return ids


def hikes(db, trail_id, hikers, *, when=NOW - timedelta(days=1)):
    for _ in range(hikers):
        db.add(HikeLog(user_id=uuid.uuid4(), trail_id=trail_id, hiked_on=when.date(), created_at=when))
    db.commit()


def ctx(db, cfg=None, **kw):
    return GenContext(db=db, config=cfg or config(), today=kw.pop("today", TODAY), now=kw.pop("now", NOW), **kw)


def run(db, cfg=None, *, now=NOW, ai=None, outbox=None, fetch=None, recipients=("admin@example.com",)):
    return service.run_daily(db, cfg or config(), now=now, client=ai, sender=outbox or Outbox(),
                             recipients=list(recipients), fetch=fetch or (lambda url: "<html></html>"))


# ------------------------------------------------------------------ config

def test_the_shipped_config_reviews_facts_and_warnings_and_auto_publishes_the_rest():
    cfg = load_config()
    assert set(cfg.types) == set(GENERATORS)
    assert {name for name in GENERATORS if cfg.type(name).auto_publish} == {
        "trending", "new_on_trekly", "roundup"}
    # Spotlights recommend a trail for the season: always reviewed (user, 2026-11-24).
    assert cfg.type("spotlight").auto_publish is False
    assert cfg.type("fun_fact").auto_publish is False
    assert cfg.type("conditions").auto_publish is False
    assert cfg.type("conditions").enabled is False
    assert cfg.type("conditions").ai is False
    assert cfg.pacing.max_posts_per_day == 1
    assert cfg.pacing.trail_cooldown_days == 30


def test_config_can_never_send_conditions_to_the_ai():
    assert config(**{"types.conditions.ai": True}).type("conditions").ai is False


def test_bad_config_is_refused():
    with pytest.raises(ConfigError):
        parse_config({"types": {"memes": {}}})
    with pytest.raises(ConfigError):
        parse_config({"types": {"trending": {"days": ["someday"]}}})


# --------------------------------------------------------------- generators

def test_trending_needs_several_real_hikers_and_names_the_top_trail(session_factory, trails):
    db = session_factory()
    hikes(db, trails["Ridge High"], 2)
    assert GENERATORS["trending"](ctx(db)) is None  # 2 hikers: could point at someone
    hikes(db, trails["Ridge High"], 1)
    db.add(SavedTrail(user_id=uuid.uuid4(), trail_id=trails["Lake Low"], created_at=NOW - timedelta(days=2)))
    db.commit()
    candidate = GENERATORS["trending"](ctx(db))
    assert candidate.trail_id == trails["Ridge High"]
    assert "Ridge High in Jasper National Park" in candidate.template_body
    assert "14.2 km out and back, 900 m of elevation gain" in candidate.template_body
    assert candidate.dedupe_key == "trending:2026-W39"


def test_trending_ignores_old_activity(session_factory, trails):
    db = session_factory()
    hikes(db, trails["Ridge High"], 5, when=NOW - timedelta(days=9))
    assert GENERATORS["trending"](ctx(db)) is None


def test_spotlight_picks_a_larch_trail_in_larch_season(session_factory, trails):
    db = session_factory()
    candidate = GENERATORS["spotlight"](ctx(db))
    assert candidate.trail_id == trails["Larch Valley"]
    assert "larch season" in candidate.template_body
    assert "11.6 km" in candidate.template_body


def test_spotlight_picks_low_trails_in_shoulder_season(session_factory, trails):
    db = session_factory()
    day = date(2026, 5, 6)
    candidate = GENERATORS["spotlight"](ctx(db, today=day, now=datetime(2026, 5, 6, 15, tzinfo=timezone.utc)))
    trail = db.get(Trail, candidate.trail_id)
    assert trail.max_elevation_m <= 1800
    assert f"tops out at {trail.max_elevation_m} m" in candidate.template_body


def test_spotlight_otherwise_picks_a_popular_trail(session_factory, trails):
    db = session_factory()
    day = date(2026, 7, 15)
    candidate = GENERATORS["spotlight"](ctx(db, today=day, now=datetime(2026, 7, 15, 15, tzinfo=timezone.utc)))
    assert candidate.trail_id in trails.values()
    assert "most popular trails in the Trekly catalogue" in candidate.template_body


def test_new_on_trekly_announces_features_then_new_trails_then_photos(session_factory, trails):
    db = session_factory()
    cfg = config(features=[{"id": "export", "text": "You can now export your Trail Journal.", "url": "/journal"}])
    candidate = GENERATORS["new_on_trekly"](ctx(db, cfg))
    assert candidate.dedupe_key == "feature:export"
    assert candidate.template_body == "New on Trekly: You can now export your Trail Journal."

    assert GENERATORS["new_on_trekly"](ctx(db)) is None  # nothing new
    db.get(Trail, trails["Falls Four"]).created_at = NOW - timedelta(days=3)
    db.add(TrailPhoto(trail_id=trails["Lake Low"], source="owner", photographer="Me", hero_path="a/hero.webp",
                      thumb_path="a/thumb.webp", hero_width=10, hero_height=10, approved_by=uuid.uuid4(),
                      created_at=NOW - timedelta(days=2)))
    db.commit()
    candidate = GENERATORS["new_on_trekly"](ctx(db))
    assert candidate.dedupe_key == f"new_trail:{trails['Falls Four']}"
    assert "just joined the catalogue" in candidate.template_body
    service.draft_from(db, config(), candidate, TODAY, NOW, None)
    db.commit()
    candidate = GENERATORS["new_on_trekly"](ctx(db))
    assert candidate.dedupe_key == f"new_photo:{trails['Lake Low']}:a/hero.webp"


def test_roundup_posts_anonymous_totals_only_above_a_minimum(session_factory, trails):
    db = session_factory()
    hikes(db, trails["Ridge High"], 4)
    hikes(db, trails["Lake Low"], 3)
    assert GENERATORS["roundup"](ctx(db)) is None  # 7 hikers but only 7 hikes
    hikes(db, trails["Falls Four"], 2)
    candidate = GENERATORS["roundup"](ctx(db))
    assert candidate.template_body.startswith("Community roundup: hikers logged 9 hikes on 3 different trails")
    assert candidate.trail_id is None
    assert set(candidate.data) == {"hikes_logged", "trails", "window_days"}


def test_roundup_leaves_out_demo_and_official_accounts(session_factory, trails):
    from app.models.account_label import AccountLabel

    db = session_factory()
    for _ in range(10):
        user = uuid.uuid4()
        db.add(AccountLabel(user_id=user, label="demo"))
        db.add(HikeLog(user_id=user, trail_id=trails["Lake Low"], hiked_on=TODAY, created_at=NOW - timedelta(hours=3)))
    db.commit()
    assert GENERATORS["roundup"](ctx(db)) is None


def test_fun_facts_use_only_approved_facts_with_their_source(session_factory, trails):
    db = session_factory()
    db.add(TreklyFact(text="Unapproved fact.", source_url="https://parks.canada.ca/a", approved=False,
                      created_at=NOW - timedelta(days=5)))
    db.commit()
    assert GENERATORS["fun_fact"](ctx(db)) is None
    fact = TreklyFact(text="Banff was founded in 1885.", source_url="https://parks.canada.ca/b", approved=True,
                      trail_id=trails["Lake Low"], created_at=NOW - timedelta(days=4))
    db.add(fact)
    db.commit()
    candidate = GENERATORS["fun_fact"](ctx(db))
    assert candidate.template_body == "Fun fact: Banff was founded in 1885."
    assert candidate.source_url == "https://parks.canada.ca/b"
    assert candidate.source_label == "Source: parks.canada.ca"
    assert candidate.fact_id == fact.id


def test_a_fact_is_not_reused_within_its_cooldown(session_factory, trails):
    db = session_factory()
    db.add(TreklyFact(text="Fact A.", source_url="https://parks.canada.ca/a", approved=True))
    db.commit()
    first = GENERATORS["fun_fact"](ctx(db))
    service.draft_from(db, config(), first, TODAY, NOW, None)
    db.commit()
    later = TODAY + timedelta(days=7)
    assert GENERATORS["fun_fact"](ctx(db, today=later, now=NOW + timedelta(days=7))) is None


def test_bulletins_are_parsed_from_the_official_page_only():
    bulletins = cond.parse_bulletins(BULLETIN_PAGE, "Banff National Park",
                                     "https://parks.canada.ca/pn-np/ab/banff/bulletins")
    assert [(b.title, b.issued_on) for b in bulletins] == [
        ("Trail Closure: Larch Valley Trail", date(2026, 9, 22)),
        ("Bear Warning: Skoki trails", date(2026, 9, 1)),
        ("Visitor centre hours", date(2026, 9, 23)),
    ]


def test_conditions_quote_the_bulletin_with_date_link_and_notice(session_factory, trails):
    db = session_factory()
    candidate = GENERATORS["conditions"](ctx(db, fetch=lambda url: BULLETIN_PAGE))
    assert candidate.template_body == (
        'Parks Canada bulletin for Banff National Park, issued September 22, 2026: '
        '"Trail Closure: Larch Valley Trail" Copied from the official version on parks.canada.ca. '
        "Check official conditions before you go."
    )
    assert candidate.source_url == "https://parks.canada.ca/pn-np/ab/banff/bulletins/AAAA-1111"
    assert candidate.source_date == date(2026, 9, 22)
    assert candidate.trail_id == trails["Larch Valley"]
    assert candidate.dedupe_key == "conditions:aaaa-1111"


def test_a_park_page_that_fails_doesnt_stop_conditions(session_factory, trails):
    db = session_factory()

    def fetch(url):
        if "banff" in url:
            return BULLETIN_PAGE
        raise TimeoutError

    context = ctx(db, fetch=fetch)
    assert GENERATORS["conditions"](context) is not None
    assert any("Jasper National Park" in note for note in context.notes)


# ------------------------------------------------------ AI writer and checks

DATA = {"trail_name": "Ridge High", "place": "Jasper National Park", "distance_km": "14.2",
        "elevation_gain_m": "900", "difficulty": "moderate", "must_mention": ["Ridge High"]}
TEMPLATE = ("Trail spotlight: Ridge High in Jasper National Park. 14.2 km out and back, 900 m of elevation gain, "
            "rated moderate.")


@pytest.mark.parametrize("text", [
    "Ridge High in Jasper National Park is calling: 14.2 km out and back with 900 m of climbing.",
    "Looking for a moderate day? Ridge High in Jasper National Park covers 14.2 km with 900 m of elevation gain.",
])
def test_ai_text_that_sticks_to_the_data_passes(text):
    assert writer.check_ai_text(text, DATA, TEMPLATE, 280) == []


@pytest.mark.parametrize("text, problem", [
    ("Ridge High in Jasper National Park: 14.2 km and 950 m of gain.", "numbers not in the data"),
    ("Ridge High in Jasper National Park is 15 km long.", "numbers not in the data"),
    ("Ridge High near Maligne Lake in Jasper National Park, 14.2 km.", "name 'Maligne'"),
    ("Ridge High in Jasper National Park is best in October.", "'october'"),
    ("Ridge High in Jasper National Park takes two days.", "'two'"),
    ("Ridge High in Jasper National Park is the busiest trail around.", "'busiest'"),
    ("Ridge High in Jasper National Park has bears right now.", "'bears'"),
    ("Jasper National Park has a 14.2 km out and back.", "leaves out 'Ridge High'"),
    ("Ridge High in Jasper National Park. See https://example.com for more.", "link"),
    ("Ridge High in Jasper National Park. 14.2 km. 900 m. Moderate. Go.", "more than 3 sentences"),
    ("Ridge High in Jasper National Park " + "is lovely " * 40, "longer than 280"),
])
def test_ai_text_that_adds_facts_is_caught(text, problem):
    problems = writer.check_ai_text(text, DATA, TEMPLATE, 280)
    assert any(problem.lower() in p.lower() for p in problems), problems


def test_the_writer_uses_good_ai_text_and_falls_back_to_the_template_otherwise():
    good = FakeAI("Ridge High in Jasper National Park: 14.2 km out and back, 900 m of elevation gain.")
    written = writer.write("spotlight", TEMPLATE, DATA, use_ai=True, client=good, max_chars=280)
    assert (written.writer, written.body) == ("ai", good.answer)
    assert "DATA:" in good.calls[0][1] and "Use only the facts" in good.calls[0][0]

    invented = FakeAI("Ridge High in Jasper National Park has 2,000 m of gain.")
    written = writer.write("spotlight", TEMPLATE, DATA, use_ai=True, client=invented, max_chars=280)
    assert (written.writer, written.body) == ("template", TEMPLATE)
    assert written.note.startswith("Skipped: the AI text failed the fact check")
    assert written.failed_check is True

    for broken in (FakeAI(None), FakeAI(error=RuntimeError("down"))):
        written = writer.write("spotlight", TEMPLATE, DATA, use_ai=True, client=broken, max_chars=280)
        # Unreachable AI isn't a failed check: the template's own text is used.
        assert (written.writer, written.body, written.failed_check) == ("template", TEMPLATE, False)

    off = FakeAI("anything")
    assert writer.write("spotlight", TEMPLATE, DATA, use_ai=False, client=off, max_chars=280).writer == "template"
    assert off.calls == []


def test_warnings_never_reach_the_ai_even_when_asked():
    ai = FakeAI("Totally rewritten warning.")
    written = writer.write("conditions", "Official text.", {}, use_ai=True, client=ai, max_chars=280)
    assert written.body == "Official text." and written.writer == "template"
    assert ai.calls == []


def test_with_the_shipped_defaults_facts_and_warnings_wait_for_review(session_factory, trails):
    import tomllib
    from app.trekly_posts.config import CONFIG_PATH

    db = session_factory()
    make_official(db)
    raw = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Only these two types run today, with their shipped auto-publish defaults.
    for name in raw["types"]:
        raw["types"][name]["enabled"] = name in ("fun_fact", "conditions")
        raw["types"][name]["days"] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    db.add(TreklyFact(text="Banff was founded in 1885.", source_url="https://parks.canada.ca/b", approved=True))
    db.commit()
    report = run(db, parse_config(raw), fetch=lambda url: BULLETIN_PAGE)
    assert set(report.drafted) == {"fun_fact", "conditions"}
    assert report.published is None and count(db, ActivityPost) == 0
    assert count(db, TreklyPostDraft, TreklyPostDraft.status == "draft") == 2


def test_no_code_path_from_conditions_reaches_the_ai():
    from pathlib import Path

    source = (Path(cond.__file__)).read_text(encoding="utf-8")
    assert "writer" not in source.split('"""', 2)[2] and "anthropic" not in source.lower()
    assert "conditions" in writer.NEVER_AI_TYPES


def test_the_daily_run_never_sends_conditions_to_the_ai(session_factory, trails):
    db = session_factory()
    ai = FakeAI(lambda user: "rewritten")
    report = run(db, config(**{"types.conditions.ai": True}), ai=ai, fetch=lambda url: BULLETIN_PAGE)
    assert "conditions" in report.drafted
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "conditions"))
    assert draft.writer == "template" and "Check official conditions before you go." in draft.body
    assert all("Larch Valley Trail" not in user for _system, user in ai.calls)
    assert all("parks.canada.ca" not in user for _system, user in ai.calls)


def test_ai_text_is_stored_with_the_template_for_comparison(session_factory, trails):
    db = session_factory()
    answer = "It's larch season: Larch Valley in Banff National Park, 11.6 km out and back, rated moderate."
    run(db, config(**{"types.conditions.enabled": False}), ai=FakeAI(answer))
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "spotlight"))
    assert draft.writer == "ai" and draft.body == answer
    assert draft.template_body.startswith("Trail spotlight: it's larch season")


# ------------------------------------------------- the daily run and pacing

def make_official(db):
    from app.models.account import Profile
    from app.models.account_label import AccountLabel

    user = uuid.uuid4()
    db.add(AccountLabel(user_id=user, label="official"))
    db.add(Profile(id=user, username="trekly", display_name="Trekly"))
    db.commit()
    return user


def auto(db, *types):
    for name in types:
        db.add(TreklyPostTypeSetting(post_type=name, auto_publish=True))
    db.commit()


@pytest.fixture
def spotlight_unlocked(monkeypatch):
    """For tests of the publishing pipeline that use spotlight as their example
    type: lift the always-reviewed lock (tested on its own below)."""
    monkeypatch.setattr(service, "ALWAYS_REVIEWED", frozenset())


def count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_running_twice_never_duplicates_drafts_or_posts(spotlight_unlocked, session_factory, trails):
    db = session_factory()
    make_official(db)
    auto(db, "spotlight", "trending", "fun_fact", "roundup", "new_on_trekly")
    outbox = Outbox()
    first = run(db, outbox=outbox)
    drafts, posts = count(db, TreklyPostDraft), count(db, ActivityPost)
    assert first.drafted and first.published == "spotlight" and posts == 1
    second = run(db, outbox=outbox, now=NOW + timedelta(hours=2))
    assert second.drafted == [] and second.published is None
    assert (count(db, TreklyPostDraft), count(db, ActivityPost)) == (drafts, posts)
    assert len(outbox.sent) <= 1  # one digest a day at most


def test_a_rerun_drafts_nothing_more_the_same_day(session_factory, trails):
    db = session_factory()
    for name in ("Falls Four", "Lake Low"):
        db.get(Trail, trails[name]).created_at = NOW - timedelta(days=2)
    db.commit()
    cfg = config(**{"types.conditions.enabled": False})
    assert "new_on_trekly" in run(db, cfg).drafted
    assert run(db, cfg, now=NOW + timedelta(hours=1)).drafted == []
    assert count(db, TreklyPostDraft, TreklyPostDraft.post_type == "new_on_trekly") == 1


def test_with_auto_publish_off_nothing_goes_out_without_approval(session_factory, trails):
    db = session_factory()
    make_official(db)
    report = run(db, config(auto=False))
    assert report.drafted and report.published is None
    assert count(db, ActivityPost) == 0
    assert count(db, TreklyPostDraft, TreklyPostDraft.status == "draft") == len(report.drafted)


def test_a_scheduled_draft_is_published_on_its_day_and_once(session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    run(db, config(auto=False))
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "spotlight"))
    draft.status, draft.publish_on = "scheduled", TODAY + timedelta(days=1)
    db.commit()
    assert run(db, config(auto=False), now=NOW + timedelta(hours=1)).published is None  # not its day yet
    tomorrow = NOW + timedelta(days=1)
    assert run(db, config(auto=False), now=tomorrow).published == "spotlight"
    post = db.get(ActivityPost, db.get(TreklyPostDraft, draft.id).post_id)
    assert (post.user_id, post.kind, post.body, post.trail_id) == (official_id, "announcement", draft.body,
                                                                   draft.trail_id)
    assert run(db, config(auto=False), now=tomorrow + timedelta(hours=1)).published is None


def test_at_most_one_post_a_day_counting_manual_ones(spotlight_unlocked, session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    db.add(ActivityPost(user_id=official_id, kind="announcement", body="Manual post", created_at=NOW - timedelta(hours=1)))
    db.commit()
    auto(db, "spotlight")
    report = run(db)
    assert report.published is None
    assert any("already posted" in note for note in report.notes)


def test_the_day_counts_in_alberta_time(spotlight_unlocked, session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    # 05:00 UTC on the 23rd is still the 22nd in Alberta.
    db.add(ActivityPost(user_id=official_id, kind="announcement", body="Yesterday",
                        created_at=datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)))
    db.commit()
    auto(db, "spotlight")
    assert run(db).published == "spotlight"


def test_no_trail_twice_within_30_days(session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    larch = trails["Larch Valley"]
    db.add(ActivityPost(user_id=official_id, kind="announcement", body="Earlier", trail_id=larch,
                        created_at=NOW - timedelta(days=29)))
    db.commit()
    candidate = GENERATORS["spotlight"](ctx(db))
    assert candidate is None or candidate.trail_id != larch


def test_publishing_refuses_a_trail_posted_about_since_the_draft(session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    run(db, config(auto=False))
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "spotlight"))
    db.add(ActivityPost(user_id=official_id, kind="announcement", body="Manual", trail_id=draft.trail_id,
                        created_at=NOW - timedelta(days=2)))
    db.commit()
    assert "within the last 30 days" in service.publish_refusal(db, config(), draft, NOW + timedelta(days=1),
                                                                TODAY + timedelta(days=1))


def test_conditions_are_exempt_from_the_trail_cooldown(session_factory, trails):
    db = session_factory()
    official_id = make_official(db)
    db.add(ActivityPost(user_id=official_id, kind="announcement", body="Earlier", trail_id=trails["Larch Valley"],
                        created_at=NOW - timedelta(days=3)))
    db.commit()
    candidate = GENERATORS["conditions"](ctx(db, fetch=lambda url: BULLETIN_PAGE))
    assert candidate.trail_id == trails["Larch Valley"]


def test_a_busy_feed_skips_the_day(client, person, session_factory, trails):  # noqa: F811
    db = session_factory()
    make_official(db)
    auto(db, "spotlight")
    for i in range(6):
        who = person(f"busy{i}")
        log(client, who, trails["Falls Four"], hiked_on="2026-09-20")
    db.expire_all()
    now = datetime.now(timezone.utc)
    report = run(db, now=now)
    assert report.published is None and "busy day" in report.publish_note


def test_stale_drafts_expire_and_cant_be_published(session_factory, trails):
    db = session_factory()
    make_official(db)
    run(db, config(auto=False))
    later = NOW + timedelta(days=6)
    run(db, config(auto=False), now=later)
    trending = db.scalars(select(TreklyPostDraft).where(TreklyPostDraft.run_date == TODAY)).all()
    assert trending and all(d.status == "expired" for d in trending if d.post_type == "spotlight")


def test_an_unapproved_fact_cant_be_published(session_factory, trails):
    db = session_factory()
    make_official(db)
    fact = TreklyFact(text="A fact.", source_url="https://parks.canada.ca/a", approved=True)
    db.add(fact)
    db.commit()
    run(db, config(auto=False))
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "fun_fact"))
    fact.approved = False
    db.commit()
    assert "isn't approved" in service.publish_refusal(db, config(), draft, NOW, TODAY)


def test_nothing_publishes_until_the_official_account_exists(session_factory, trails):
    db = session_factory()
    auto(db, "spotlight")
    report = run(db)
    assert report.published is None and count(db, ActivityPost) == 0


def test_by_default_spotlights_wait_for_review(session_factory, trails):
    db = session_factory()
    make_official(db)
    report = run(db)
    assert report.drafted == ["spotlight"] and report.published is None
    assert count(db, ActivityPost) == 0
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "spotlight"))
    assert draft.status == "draft" and draft.trail_id == trails["Larch Valley"]


def test_spotlights_never_auto_publish_even_if_an_admin_row_says_so(session_factory, trails):
    db = session_factory()
    make_official(db)
    db.add(TreklyPostTypeSetting(post_type="spotlight", auto_publish=True))  # e.g. set before the lock
    db.commit()
    assert service.auto_publish_settings(db, config())["spotlight"] is False
    assert run(db).published is None and count(db, ActivityPost) == 0


def test_an_admin_can_still_turn_a_type_off(session_factory, trails):
    db = session_factory()
    make_official(db)
    db.add(TreklyPostTypeSetting(post_type="spotlight", auto_publish=False))
    db.commit()
    assert run(db).published is None
    assert count(db, TreklyPostDraft, TreklyPostDraft.status == "draft") >= 1
    assert service.auto_publish_settings(db, config())["spotlight"] is False
    assert service.auto_publish_settings(db, config())["trending"] is True


def test_a_post_that_fails_the_fact_check_is_skipped_not_queued(session_factory, trails):
    db = session_factory()
    make_official(db)
    outbox = Outbox()
    invented = FakeAI("Larch Valley in Banff National Park is the busiest trail, with 2,000 m of gain.")
    report = run(db, config(**{"types.conditions.enabled": False}), ai=invented, outbox=outbox)
    assert report.failed_check == ["spotlight"] and report.published is None
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "spotlight"))
    assert draft.status == "rejected" and draft.ai_note.startswith("Skipped: the AI text failed the fact check")
    assert count(db, ActivityPost) == 0
    # It isn't tried again the same day.
    assert run(db, config(**{"types.conditions.enabled": False}), ai=invented,
               now=NOW + timedelta(hours=1)).failed_check == []
    assert "Skipped (the AI text failed the fact check)" in outbox.sent[0].text


def test_the_digest_is_a_record_of_what_went_out_once_a_day(spotlight_unlocked, session_factory, trails, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://trekly.example")
    db = session_factory()
    make_official(db)
    auto(db, "spotlight")
    outbox = Outbox()
    run(db, outbox=outbox)
    assert len(outbox.sent) == 1
    email = outbox.sent[0]
    post = db.scalar(select(ActivityPost))
    assert email.to == "admin@example.com" and email.subject.startswith("Trekly posted:")
    assert "Posted as @trekly today:" in email.text and post.body in email.text
    assert "https://trekly.example/admin/trekly-posts" in email.text
    run(db, outbox=outbox, now=NOW + timedelta(hours=3))
    assert len(outbox.sent) == 1


def test_no_digest_when_nothing_went_out(session_factory, trails):
    db = session_factory()
    make_official(db)
    outbox = Outbox()
    run(db, config(auto=False), outbox=outbox)
    assert outbox.sent == []


def test_without_digest_recipients_it_still_runs_and_publishes(spotlight_unlocked, session_factory, trails):
    db = session_factory()
    make_official(db)
    auto(db, "spotlight")
    report = service.run_daily(db, config(), now=NOW, client=None, sender=None, recipients=[],
                               fetch=lambda url: "<html></html>")
    assert report.published == "spotlight" and report.digest_sent_to == 0


def test_digest_recipients_come_only_from_the_env(monkeypatch):
    monkeypatch.setenv("TREKLY_POSTS_DIGEST_TO", "a@example.com, b@example.com")
    assert service.digest_recipients() == ["a@example.com", "b@example.com"]
    monkeypatch.delenv("TREKLY_POSTS_DIGEST_TO")
    monkeypatch.setenv("ADMIN_USER_IDS", str(uuid.uuid4()))
    assert service.digest_recipients() == []


def test_the_lock_stops_overlapping_runs(session_factory, trails):
    db = session_factory()
    assert service.acquire_lock(db, NOW, "first") is None
    report = run(db, now=NOW + timedelta(minutes=1))
    assert report.drafted == [] and "another run" in report.notes[0]


# -------------------------------------------------------- the review API

@pytest.fixture
def api(client, admin_headers, official, session_factory, trails):  # noqa: F811
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_posts_config] = lambda: config(auto=False, **{"types.conditions.enabled": False})
    db = session_factory()
    db.add(TreklyFact(text="Banff was founded in 1885.", source_url="https://parks.canada.ca/b", approved=True))
    db.commit()
    run(db, config(auto=False, **{"types.conditions.enabled": False}))
    db.close()
    yield {"client": client, "headers": admin_headers}
    app.dependency_overrides.pop(get_now, None)
    app.dependency_overrides.pop(get_posts_config, None)


def queue(api, **params):
    response = api["client"].get("/api/admin/trekly-posts", params=params, headers=api["headers"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_the_queue_lists_drafts_and_each_types_auto_publish(api):
    body = queue(api)
    assert body["account"]["username"] == "trekly"
    assert all(t["auto_publish"] is False for t in body["types"])
    assert {d["post_type"] for d in body["drafts"]} >= {"spotlight", "fun_fact"}
    assert body["posts_today"] == 0 and body["max_posts_per_day"] == 1


def test_edit_schedule_publish_and_reject(api, session_factory):
    c, h = api["client"], api["headers"]
    spotlight = next(d for d in queue(api)["drafts"] if d["post_type"] == "spotlight")
    edited = c.patch(f"/api/admin/trekly-posts/{spotlight['id']}", json={"body": "  Edited   by hand.  "}, headers=h)
    assert edited.status_code == 200 and edited.json()["body"] == "Edited by hand."
    assert edited.json()["writer"] == "admin"

    past = c.post(f"/api/admin/trekly-posts/{spotlight['id']}/schedule", json={"publish_on": "2026-09-01"}, headers=h)
    assert past.status_code == 422
    scheduled = c.post(f"/api/admin/trekly-posts/{spotlight['id']}/schedule", json={"publish_on": "2026-09-25"},
                       headers=h)
    assert scheduled.json()["status"] == "scheduled"

    published = c.post(f"/api/admin/trekly-posts/{spotlight['id']}/publish", headers=h)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    items = feed(c)["items"]
    assert items[0]["kind"] == "announcement" and items[0]["announcement"]["body"] == "Edited by hand."
    assert items[0]["author"]["label"] == "official"

    other = next(d for d in queue(api)["drafts"] if d["status"] == "draft")
    second = c.post(f"/api/admin/trekly-posts/{other['id']}/publish", headers=h)
    assert second.status_code == 409 and "already posted" in second.json()["detail"]
    assert c.post(f"/api/admin/trekly-posts/{spotlight['id']}/publish", headers=h).status_code == 409

    rejected = c.post(f"/api/admin/trekly-posts/{other['id']}/reject", headers=h)
    assert rejected.json()["status"] == "rejected"
    assert c.patch(f"/api/admin/trekly-posts/{other['id']}", json={"body": "x"}, headers=h).status_code == 409


def test_a_published_fact_shows_its_source_link_in_the_feed(api, session_factory):
    db = session_factory()
    draft = db.scalar(select(TreklyPostDraft).where(TreklyPostDraft.post_type == "fun_fact"))
    db.close()  # SQLite here shares one connection with the client
    assert api["client"].post(f"/api/admin/trekly-posts/{draft.id}/publish", headers=api["headers"]).status_code == 200
    announcement = feed(api["client"])["items"][0]["announcement"]
    assert announcement["source_url"] == "https://parks.canada.ca/b"
    assert announcement["source_label"] == "Source: parks.canada.ca"


def test_conditions_drafts_cant_be_edited(api, session_factory):
    db = session_factory()
    draft = TreklyPostDraft(post_type="conditions", dedupe_key="conditions:x", run_date=TODAY, body="Official.",
                            template_body="Official.", data={})
    db.add(draft)
    db.commit()
    response = api["client"].patch(f"/api/admin/trekly-posts/{draft.id}", json={"body": "Paraphrased."},
                                   headers=api["headers"])
    assert response.status_code == 422


def test_auto_publish_toggle(api):
    c, h = api["client"], api["headers"]
    response = c.put("/api/admin/trekly-posts/types/trending", json={"auto_publish": True}, headers=h)
    assert response.status_code == 200 and response.json()["auto_publish"] is True
    assert next(t for t in queue(api)["types"] if t["post_type"] == "trending")["auto_publish"] is True
    assert c.put("/api/admin/trekly-posts/types/memes", json={"auto_publish": True}, headers=h).status_code == 422


def test_spotlight_auto_publish_cannot_be_turned_on(api):
    c, h = api["client"], api["headers"]
    refused = c.put("/api/admin/trekly-posts/types/spotlight", json={"auto_publish": True}, headers=h)
    assert refused.status_code == 409
    spotlight = next(t for t in queue(api)["types"] if t["post_type"] == "spotlight")
    assert spotlight["auto_publish"] is False and spotlight["auto_publish_locked"] is True
    # Turning it off is always fine.
    assert c.put("/api/admin/trekly-posts/types/spotlight", json={"auto_publish": False}, headers=h).status_code == 200


# -------------------------------------------------------- winter spotlights

WINTER_DAY = date(2026, 12, 2)  # a Wednesday in winter
WINTER_NOW = datetime(2026, 12, 2, 16, tzinfo=timezone.utc)


def _winterize(db, trails, name, acts, ends=None):
    t = db.get(Trail, trails[name])
    t.winter_activities, t.winter_source_url, t.winter_route_ends = acts, "https://parks.canada.ca/w", ends
    db.commit()
    return t


def test_winter_spotlight_picks_only_winter_trails(session_factory, trails):
    db = session_factory()
    _winterize(db, trails, "Lake Low", ["snowshoe", "winter_hike"])
    seen = {GENERATORS["spotlight"](ctx(db, today=WINTER_DAY + timedelta(days=k), now=WINTER_NOW)).trail_id
            for k in range(0, 21, 7)}
    assert seen == {trails["Lake Low"]}
    candidate = GENERATORS["spotlight"](ctx(db, today=WINTER_DAY, now=WINTER_NOW))
    assert candidate.data["reason"] == "winter"
    assert "winter hiking and snowshoeing" in candidate.template_body
    assert "avalanche forecast" in candidate.template_body and "safe" not in candidate.template_body.lower()


def test_winter_spotlight_with_no_winter_trails_drafts_nothing(session_factory, trails):
    db = session_factory()
    assert GENERATORS["spotlight"](ctx(db, today=WINTER_DAY, now=WINTER_NOW)) is None


def test_winter_spotlight_gives_a_partial_route_its_end_not_summer_stats(session_factory, trails):
    db = session_factory()
    _winterize(db, trails, "Lake Low", ["winter_hike"], ends="The Red Chairs viewpoint (about 3.4 km return).")
    body = GENERATORS["spotlight"](ctx(db, today=WINTER_DAY, now=WINTER_NOW)).template_body
    assert "Winter route: The Red Chairs viewpoint" in body and "elevation gain" not in body


def test_winter_spotlight_keeps_its_template_wording():
    written = writer.write("spotlight", "Trail spotlight: a winter pick. Check conditions.", {"reason": "winter"},
                           use_ai=True, client=FakeAI("Totally different words."), max_chars=280)
    assert (written.body, written.writer) == ("Trail spotlight: a winter pick. Check conditions.", "template")


def test_summer_spotlight_skips_winter_only_trails(session_factory, trails):
    db = session_factory()
    for t in db.scalars(select(Trail)).all():
        t.tags = ["winter_only"]
    db.commit()
    day = date(2026, 7, 15)
    assert GENERATORS["spotlight"](ctx(db, today=day, now=datetime(2026, 7, 15, 15, tzinfo=timezone.utc))) is None


def test_fact_bank_crud_and_reapproval_on_change(api, trails):
    c, h = api["client"], api["headers"]
    bad = c.post("/api/admin/trekly-posts/facts", json={"text": "x", "source_url": "http://insecure.example"}, headers=h)
    assert bad.status_code == 422
    made = c.post("/api/admin/trekly-posts/facts", json={
        "text": "A fact.", "source_url": "https://parks.canada.ca/a", "trail_id": str(trails["Lake Low"]),
        "approved": True,
    }, headers=h)
    assert made.status_code == 201, made.text
    fact = made.json()
    assert fact["approved"] is True and fact["trail"]["name"] == "Lake Low"
    changed = c.patch(f"/api/admin/trekly-posts/facts/{fact['id']}", json={"text": "A changed fact."}, headers=h)
    assert changed.json()["approved"] is False  # needs approving again
    approved = c.patch(f"/api/admin/trekly-posts/facts/{fact['id']}", json={"approved": True}, headers=h)
    assert approved.json()["approved"] is True
    assert len(c.get("/api/admin/trekly-posts/facts", headers=h).json()) == 2  # plus the fixture's
    assert c.delete(f"/api/admin/trekly-posts/facts/{fact['id']}", headers=h).status_code == 204


def test_the_seed_facts_are_all_unapproved_and_sourced():
    import json

    from scripts.trekly_posts import SEED_PATH

    facts = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert len(facts) >= 20
    assert len({f["key"] for f in facts}) == len(facts)
    for fact in facts:
        assert fact["source_url"].startswith("https://")
        assert 0 < len(fact["text"]) <= 400
        assert "approved" not in fact
