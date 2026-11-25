"""One generator per post type. Each reads real data and returns a Candidate
(the template text plus the facts behind it), or None when there's nothing
true and useful to say today.

Rules every generator keeps:
- Only catalogue data, anonymous totals, approved facts and official bulletins.
  No post names or points at a person: activity counts need several different
  hikers, and demo and official accounts never count (app/account_labels.py).
- A trail posted about (or waiting in a draft) within the cooldown is skipped
  (`GenContext.excluded_trails`). Conditions posts are the exception: an
  official closure is posted whatever was said about the trail lately.
- `dedupe_key` names what the post is about, so the same thing is never
  drafted twice, however many times the run happens.
"""

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.orm import Session

from app.account_labels import official_id, real_user
from app.models.account import SavedTrail
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app import season as season_rules
from app.models.trail import Trail
from app.trail_winter import activities_phrase
from app.models.trail_photo import TrailPhoto
from app.models.trekly_post import TreklyFact, TreklyPostDraft
from app.routers.trails import live_trails
from app.trekly_posts import conditions as conditions_source
from app.trekly_posts.config import PostsConfig

ROUTE_LABELS = {"out_and_back": "out and back", "loop": "loop", "point_to_point": "one way"}
ACTIVE_STATUSES = ("draft", "scheduled", "published")
CONDITIONS_NOTICE = "Check official conditions before you go."


@dataclass(frozen=True)
class Candidate:
    post_type: str
    dedupe_key: str
    template_body: str
    data: dict
    trail_id: UUID | None = None
    fact_id: UUID | None = None
    source_url: str | None = None
    source_label: str | None = None
    source_date: date | None = None


@dataclass
class GenContext:
    db: Session
    config: PostsConfig
    today: date
    now: datetime
    fetch: Callable[[str], str] = conditions_source.fetch_page
    notes: list[str] = field(default_factory=list)
    _excluded: set | None = None

    @property
    def excluded_trails(self) -> set:
        """Trails posted about by @trekly, or in a live draft, within the cooldown."""
        if self._excluded is None:
            since = self.now - timedelta(days=self.config.pacing.trail_cooldown_days)
            drafted = self.db.scalars(
                select(TreklyPostDraft.trail_id).where(
                    TreklyPostDraft.trail_id.is_not(None), TreklyPostDraft.status.in_(ACTIVE_STATUSES),
                    or_(TreklyPostDraft.created_at >= since, TreklyPostDraft.published_at >= since),
                )
            ).all()
            official = official_id(self.db)
            posted = self.db.scalars(
                select(ActivityPost.trail_id).where(
                    ActivityPost.user_id == official, ActivityPost.trail_id.is_not(None),
                    ActivityPost.created_at >= since,
                )
            ).all() if official else []
            self._excluded = set(drafted) | set(posted)
        return self._excluded

    def key_used(self, key: str) -> bool:
        return self.db.scalar(select(TreklyPostDraft.id).where(TreklyPostDraft.dedupe_key == key)) is not None


def _num(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:,}" if isinstance(value, int) and value >= 10000 else str(value)


def place_of(trail: Trail) -> str:
    return trail.park_name or trail.region


def trail_data(trail: Trail) -> dict:
    data = {
        "trail_name": trail.name,
        "place": place_of(trail),
        "province": trail.province_code,
        "difficulty": trail.terrain_difficulty,
    }
    if trail.distance_km is not None:
        data["distance_km"] = _num(trail.distance_km)
        data["route"] = ROUTE_LABELS.get(trail.route_type or "", "")
    if trail.elevation_gain_m is not None:
        data["elevation_gain_m"] = _num(trail.elevation_gain_m)
    if trail.max_elevation_m is not None:
        data["max_elevation_m"] = _num(trail.max_elevation_m)
    data["must_mention"] = [trail.name]
    return {k: v for k, v in data.items() if v not in (None, "")}


def stats_sentence(trail: Trail) -> str:
    parts = []
    if trail.distance_km is not None:
        route = ROUTE_LABELS.get(trail.route_type or "")
        parts.append(f"{_num(trail.distance_km)} km {route}" if route else f"{_num(trail.distance_km)} km")
    if trail.elevation_gain_m is not None:
        parts.append(f"{_num(trail.elevation_gain_m)} m of elevation gain")
    parts.append(f"rated {trail.terrain_difficulty}")
    text = ", ".join(parts)
    return text[0].upper() + text[1:] + "."


def winter_stats(trail: Trail) -> str:
    """The stats line for a winter post: a partial winter route says where it
    ends instead of quoting the summer distance and gain."""
    if trail.winter_route_ends:
        return f"Winter route: {trail.winter_route_ends}"
    return stats_sentence(trail)


def _live(db: Session):
    return select(Trail).where(*live_trails())


def _iso_week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


# --- Trending ----------------------------------------------------------------

def trending(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("trending")
    key = f"trending:{_iso_week(ctx.today)}"
    if ctx.key_used(key):
        return None
    since = ctx.now - timedelta(days=7)
    recent = union_all(
        select(HikeLog.trail_id.label("trail_id"), HikeLog.user_id.label("user_id"))
        .where(HikeLog.created_at >= since, real_user(HikeLog.user_id)),
        select(SavedTrail.trail_id.label("trail_id"), SavedTrail.user_id.label("user_id"))
        .where(SavedTrail.created_at >= since, real_user(SavedTrail.user_id)),
    ).subquery()
    counts = (
        select(recent.c.trail_id, func.count().label("n"), func.count(func.distinct(recent.c.user_id)).label("hikers"))
        .group_by(recent.c.trail_id).subquery()
    )
    rows = ctx.db.execute(
        select(Trail, counts.c.n, counts.c.hikers).join(counts, counts.c.trail_id == Trail.id)
        .where(*live_trails()).order_by(counts.c.n.desc(), Trail.popularity_rank, Trail.name).limit(10)
    ).all()
    min_hikers = int(cfg.get("min_hikers", 3))
    for trail, _n, hikers in rows:
        if hikers < min_hikers:
            # Ordered by activity, so a quieter trail can't be "the" trending one.
            return None
        if trail.id in ctx.excluded_trails:
            continue
        data = trail_data(trail) | {"window_days": 7}
        body = (f"Trending this week: {trail.name} in {place_of(trail)} is one of the most logged and saved trails "
                f"on Trekly over the last 7 days. {stats_sentence(trail)}")
        return Candidate("trending", key, body, data, trail_id=trail.id)
    return None


# --- Trail spotlight ---------------------------------------------------------

def _in_window(day: date, window) -> bool:
    (m1, d1), (m2, d2) = window
    return (m1, d1) <= (day.month, day.day) <= (m2, d2)


def spotlight(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("spotlight")
    key = f"spotlight:{ctx.today.isoformat()}"
    if ctx.key_used(key):
        return None
    trails = [t for t in ctx.db.scalars(_live(ctx.db).order_by(Trail.popularity_rank, Trail.name)).all()
              if t.id not in ctx.excluded_trails]
    if not trails:
        return None
    pick = ctx.today.toordinal()

    # Winter (app/season.py): only trails the parks list for winter use, and
    # spotlights are always reviewed before they go out (ALWAYS_REVIEWED).
    if season_rules.by_date(ctx.today) == "winter":
        options = [t for t in trails if t.winter_activities]
        if not options:
            return None
        trail = options[pick % len(options)]
        body = (f"Trail spotlight: a winter pick. {trail.name} in {place_of(trail)} is listed for "
                f"{activities_phrase(trail.winter_activities)} in winter. {winter_stats(trail)} "
                "Check trail conditions and the avalanche forecast before you go.")
        return Candidate("spotlight", key, body,
                         trail_data(trail) | {"reason": "winter", "winter_activities": list(trail.winter_activities)},
                         trail_id=trail.id)
    # Summer: winter-only roads and ski tracks aren't spotlighted.
    trails = [t for t in trails if not t.is_winter_only]
    if not trails:
        return None

    larch = cfg.get("larch_window")
    if larch and _in_window(ctx.today, larch):
        options = [t for t in trails if "larch" in (t.tags or [])]
        if options:
            trail = options[pick % len(options)]
            body = (f"Trail spotlight: it's larch season, and {trail.name} in {place_of(trail)} is one of the "
                    f"larch trails in the catalogue. {stats_sentence(trail)}")
            return Candidate("spotlight", key, body, trail_data(trail) | {"reason": "larch season"},
                             trail_id=trail.id)

    low_max = int(cfg.get("low_elevation_max_m", 1800))
    if any(_in_window(ctx.today, w) for w in cfg.get("shoulder_windows", [])):
        options = [t for t in trails if t.max_elevation_m is not None and t.max_elevation_m <= low_max]
        if options:
            trail = options[pick % len(options)]
            body = (f"Trail spotlight: {trail.name} in {place_of(trail)} tops out at "
                    f"{_num(trail.max_elevation_m)} m, a lower-elevation pick for the shoulder season. "
                    f"{stats_sentence(trail)}")
            return Candidate("spotlight", key, body, trail_data(trail) | {"reason": "shoulder season"},
                             trail_id=trail.id)

    options = trails[:25]
    trail = options[pick % len(options)]
    body = (f"Trail spotlight: {trail.name} in {place_of(trail)}, one of the most popular trails in the "
            f"Trekly catalogue. {stats_sentence(trail)}")
    return Candidate("spotlight", key, body, trail_data(trail) | {"reason": "popular"}, trail_id=trail.id)


# --- New on Trekly -----------------------------------------------------------

def _site_url(path: str) -> str | None:
    base = os.getenv("APP_URL", "").rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


def new_on_trekly(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("new_on_trekly")
    for feature in ctx.config.features:
        key = f"feature:{feature.id}"
        if not ctx.key_used(key):
            url = _site_url(feature.url) if feature.url else None
            return Candidate("new_on_trekly", key, f"New on Trekly: {feature.text}", {"feature": feature.text},
                             source_url=url, source_label="Open it on Trekly" if url else None)

    since = ctx.now - timedelta(days=int(cfg.get("lookback_days", 14)))
    for trail in ctx.db.scalars(_live(ctx.db).where(Trail.created_at >= since).order_by(Trail.created_at)).all():
        key = f"new_trail:{trail.id}"
        if trail.id in ctx.excluded_trails or ctx.key_used(key):
            continue
        body = f"New on Trekly: {trail.name} in {place_of(trail)} just joined the catalogue. {stats_sentence(trail)}"
        return Candidate("new_on_trekly", key, body, trail_data(trail) | {"news": "new trail"}, trail_id=trail.id)

    photos = ctx.db.execute(
        select(Trail, TrailPhoto.hero_path).join(TrailPhoto, TrailPhoto.trail_id == Trail.id)
        .where(*live_trails(), TrailPhoto.created_at >= since).order_by(TrailPhoto.created_at)
    ).all()
    for trail, hero in photos:
        key = f"new_photo:{trail.id}:{hero}"
        if trail.id in ctx.excluded_trails or ctx.key_used(key):
            continue
        body = f"New on Trekly: a fresh photo of {trail.name} in {place_of(trail)}. {stats_sentence(trail)}"
        return Candidate("new_on_trekly", key, body, trail_data(trail) | {"news": "new photo"}, trail_id=trail.id)
    return None


# --- Community roundup -------------------------------------------------------

def roundup(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("roundup")
    key = f"roundup:{_iso_week(ctx.today)}"
    if ctx.key_used(key):
        return None
    since = ctx.now - timedelta(days=7)
    hikes, hikers, trails = ctx.db.execute(
        select(func.count(), func.count(func.distinct(HikeLog.user_id)), func.count(func.distinct(HikeLog.trail_id)))
        .where(HikeLog.created_at >= since, real_user(HikeLog.user_id),
               or_(HikeLog.hiked_on.is_(None), HikeLog.hiked_on <= ctx.today))
    ).one()
    if hikers < int(cfg.get("min_hikers", 5)) or hikes < int(cfg.get("min_hikes", 8)):
        return None
    trail_word = "trail" if trails == 1 else "different trails"
    body = (f"Community roundup: hikers logged {hikes} hikes on {trails} {trail_word} on Trekly over the last "
            f"7 days. Nice work, everyone.")
    # Totals only: nothing about who.
    return Candidate("roundup", key, body, {"hikes_logged": hikes, "trails": trails, "window_days": 7})


# --- Fun fact ----------------------------------------------------------------

def _source_label(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return f"Source: {host}" if host else "Source"


def fun_fact(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("fun_fact")
    key_prefix = f"fact-day:{ctx.today.isoformat()}"
    if ctx.db.scalar(select(TreklyPostDraft.id).where(TreklyPostDraft.dedupe_key.like(f"{key_prefix}:%"))):
        return None
    since = ctx.now - timedelta(days=int(cfg.get("fact_cooldown_days", 180)))
    recently = select(TreklyPostDraft.fact_id).where(
        TreklyPostDraft.fact_id.is_not(None), TreklyPostDraft.status.in_(ACTIVE_STATUSES),
        TreklyPostDraft.created_at >= since,
    )
    facts = ctx.db.scalars(
        select(TreklyFact).where(TreklyFact.approved.is_(True), TreklyFact.id.not_in(recently))
        .order_by(TreklyFact.created_at, TreklyFact.id)
    ).all()
    for fact in facts:
        if fact.trail_id is not None and fact.trail_id in ctx.excluded_trails:
            continue
        data = {"fact": fact.text, "source_url": fact.source_url}
        return Candidate("fun_fact", f"{key_prefix}:{fact.id}", f"Fun fact: {fact.text}", data,
                         trail_id=fact.trail_id, fact_id=fact.id, source_url=fact.source_url,
                         source_label=_source_label(fact.source_url))
    return None


# --- Conditions and warnings -------------------------------------------------

def _trail_named_in(ctx: GenContext, park: str, title: str) -> Trail | None:
    lowered = title.lower()
    for trail in ctx.db.scalars(_live(ctx.db).where(Trail.park_name == park).order_by(Trail.popularity_rank)).all():
        names = [trail.name] + [part.strip() for sep in (" / ", " via ", " to ") for part in trail.name.split(sep)]
        if any(len(name) >= 6 and name.lower() in lowered for name in names):
            return trail
    return None


def conditions_body(bulletin: conditions_source.Bulletin) -> str:
    issued = f"{bulletin.issued_on:%B} {bulletin.issued_on.day}, {bulletin.issued_on.year}"
    return (f'Parks Canada bulletin for {bulletin.park}, issued {issued}: "{bulletin.title}" '
            f"Copied from the official version on parks.canada.ca. {CONDITIONS_NOTICE}")


def conditions(ctx: GenContext) -> Candidate | None:
    cfg = ctx.config.type("conditions")
    bulletins, errors = conditions_source.fetch_bulletins(cfg.get("sources", []), fetch=ctx.fetch)
    ctx.notes += [f"conditions: couldn't read {e}" for e in errors]
    oldest = ctx.today - timedelta(days=int(cfg.get("max_age_days", 3)))
    keywords = cfg.get("keywords", [])
    fresh = sorted(
        (b for b in bulletins
         if oldest <= b.issued_on <= ctx.today and conditions_source.matches(b, keywords)),
        key=lambda b: (b.issued_on, b.url), reverse=True,
    )
    for bulletin in fresh:
        key = f"conditions:{bulletin.url.rstrip('/').rsplit('/', 1)[-1].lower()}"
        if ctx.key_used(key):
            continue
        body = conditions_body(bulletin)
        if len(body) > 500:
            continue
        trail = _trail_named_in(ctx, bulletin.park, bulletin.title)
        data = {"park": bulletin.park, "title": bulletin.title, "issued_on": bulletin.issued_on.isoformat(),
                "url": bulletin.url, "source_page": bulletin.source_page}
        return Candidate("conditions", key, body, data, trail_id=trail.id if trail else None,
                         source_url=bulletin.url, source_label="Read the bulletin on parks.canada.ca",
                         source_date=bulletin.issued_on)
    return None


GENERATORS: dict[str, Callable[[GenContext], Candidate | None]] = {
    "conditions": conditions,
    "trending": trending,
    "spotlight": spotlight,
    "new_on_trekly": new_on_trekly,
    "roundup": roundup,
    "fun_fact": fun_fact,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
