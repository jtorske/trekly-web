"""The Activity feed as one blended, ranked list (GET /api/activity).

There are no tabs: everyone gets one feed, built here for each request.

Who may appear is decided first, by the rules in app/activity.py
(readable_where: feed sharing on, a listed public profile, the section the
post draws on shown, not hidden or held by moderation, plus the viewer's own
posts), and then by blocks: a post never shows between two hikers when either
has blocked the other. Private profiles never post to the feed at all, not
even to approved followers (app/activity.py). Only then is the list arranged:

1. "Fresh" posts from people you follow (FOLLOWED_FRESH_DAYS) and your own
   (OWN_FRESH_DAYS), newest first, lead the feed. One suggested post goes in
   after every SUGGEST_EVERY of them, never more than MAX_NON_FOLLOWED_RUN
   non-followed posts in a row while followed ones remain.
2. Once those run out, a "You're all caught up" divider (only when at least
   one followed post was shown), then everything else, best first.
   Suggested posts are ranked by `relevance`: the trail is one you've hiked
   or saved, it's in a park on your radar, it's in your home province (or
   its author shows that province), its high fives, and how recent it is.
   Older posts from people you follow join that ranking with a boost;
   your own older posts rank on recency and high fives alone.
3. @trekly posts are mixed in at most one in every TREKLY_GAP entries.
4. Demo accounts' posts come only after every real hiker's post.
5. "Trekly picks" (app/picks.py) close the feed, and are mixed in early
   while the feed is quiet, so it's never empty.

Two posts by the same author never sit back to back when another author is
available. The arrangement is deterministic for a given moment: the cursor
carries the moment the first page was built (`as_of`) and an offset, and
later pages ignore posts made after it, so a post never shows twice in one
visit. New followed posts after `as_of` are counted by `new_since` for the
page's "New posts" pill.

Nothing here reveals more than the post itself does: relevance uses the
post's own trail, the author's province only when they show it, and the
viewer's own private preferences (radar parks), which never leave the API.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.account_labels import labels_for
from app.activity import folded_where, readable_query, visible_where, _joined
from app.models.account import Profile, SavedTrail
from app.models.activity import ActivityPost, ActivityReaction
from app.models.hike_log import HikeLog
from app.models.preferences import ProfilePreferences
from app.models.privacy import ProfileSettings
from app.models.social import Block, Follow
from app.models.trail import Trail
from app.preferences import PARK_BY_REGION

POOL_SIZE = 500
FOLLOWED_FRESH_DAYS = 14
OWN_FRESH_DAYS = 3
SUGGEST_EVERY = 3
MAX_NON_FOLLOWED_RUN = 2
TREKLY_GAP = 8
# The first @trekly post may come this many entries in.
TREKLY_FIRST = 3
# How far down the ranking to look for a different author than the last.
AUTHOR_LOOKAHEAD = 12
# While the feed is quiet, a pick after every this many entries.
PICK_EVERY = 5
FOLLOW_BOOST = 3.0
RECENCY_WEIGHT = 4.0
RECENCY_HALF_LIFE_DAYS = 3.0
# A slower fade too, so a months-old post sinks below last week's.
SLOW_RECENCY_WEIGHT = 2.0
SLOW_RECENCY_HALF_LIFE_DAYS = 30.0

Reason = Literal["own", "following", "suggested", "trekly", "demo"]


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@dataclass
class Candidate:
    id: UUID
    user_id: UUID
    created_at: datetime
    reason: Reason
    trail_id: UUID | None = None
    park_name: str | None = None
    trail_province: str | None = None
    # Only when the author shows their home province.
    author_province: str | None = None
    high_fives: int = 0
    score: float = 0.0


@dataclass
class Reader:
    """What the ranking knows about the viewer (nothing, for a guest)."""

    id: UUID | None = None
    following: set[UUID] = field(default_factory=set)
    hiked: set[UUID] = field(default_factory=set)
    saved: set[UUID] = field(default_factory=set)
    parks: set[str] = field(default_factory=set)
    province: str | None = None
    blocked: set[UUID] = field(default_factory=set)


@dataclass(frozen=True)
class Entry:
    """One slot in the feed: a post, the caught-up divider, or a pick (its index)."""

    type: Literal["post", "caught_up", "pick"]
    post: Candidate | None = None
    pick: int | None = None


# ------------------------------------------------------------------ ranking


def relevance(c: Candidate, reader: Reader, now: datetime) -> float:
    """Higher first. Your own posts rank on recency and high fives alone:
    they'd always match "trails you've hiked"."""
    score = 0.0
    if c.reason == "own":
        pass
    elif c.trail_id is not None:
        if c.trail_id in reader.hiked:
            score += 3.0
        elif c.trail_id in reader.saved:
            score += 2.5
    if c.reason != "own":
        if c.park_name and c.park_name in reader.parks:
            score += 2.0
        if reader.province and reader.province in (c.trail_province, c.author_province):
            score += 1.5
    score += math.log1p(max(c.high_fives, 0))
    age_days = max((now - _aware(c.created_at)).total_seconds(), 0) / 86400
    score += RECENCY_WEIGHT * 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
    score += SLOW_RECENCY_WEIGHT * 0.5 ** (age_days / SLOW_RECENCY_HALF_LIFE_DAYS)
    if c.reason == "following":
        score += FOLLOW_BOOST
    return score


def _newest_first(items: Iterable[Candidate]) -> list[Candidate]:
    return sorted(items, key=lambda c: (_aware(c.created_at), c.id), reverse=True)


def _best_first(items: Iterable[Candidate]) -> list[Candidate]:
    return sorted(items, key=lambda c: (-c.score, -_aware(c.created_at).timestamp(), str(c.id)))


class _Builder:
    def __init__(self) -> None:
        self.out: list[Entry] = []
        self.last_author: UUID | None = None
        self.since_trekly = TREKLY_GAP - TREKLY_FIRST
        self.non_followed_run = 0
        self.trekly_shown = False

    def add(self, c: Candidate) -> None:
        self.out.append(Entry("post", post=c))
        self.last_author = c.user_id
        self.since_trekly = 0 if c.reason == "trekly" else self.since_trekly + 1
        self.trekly_shown = self.trekly_shown or c.reason == "trekly"
        followed = c.reason in ("following", "own")
        self.non_followed_run = 0 if followed else self.non_followed_run + 1

    def divider(self) -> None:
        self.out.append(Entry("caught_up"))

    def trekly_due(self, trekly: list[Candidate]) -> bool:
        return bool(trekly) and self.since_trekly >= TREKLY_GAP - 1

    def take(self, queue: list[Candidate]) -> Candidate:
        """The first in `queue` by someone other than the last author (within
        AUTHOR_LOOKAHEAD), else simply the first."""
        for index, c in enumerate(queue[:AUTHOR_LOOKAHEAD]):
            if c.user_id != self.last_author:
                return queue.pop(index)
        return queue.pop(0)

    def other_author_in(self, queue: list[Candidate]) -> bool:
        return any(c.user_id != self.last_author for c in queue[:AUTHOR_LOOKAHEAD])


def arrange(candidates: list[Candidate], reader: Reader, as_of: datetime, picks: int = 0,
            sparse: bool = False) -> list[Entry]:
    """The whole feed for this reader at `as_of`, in order (see the module doc)."""
    as_of = _aware(as_of)
    for c in candidates:
        c.score = relevance(c, reader, as_of)
    followed_cut = as_of - timedelta(days=FOLLOWED_FRESH_DAYS)
    own_cut = as_of - timedelta(days=OWN_FRESH_DAYS)

    def fresh(c: Candidate) -> bool:
        when = _aware(c.created_at)
        return (c.reason == "following" and when >= followed_cut) or (c.reason == "own" and when >= own_cut)

    lead = _newest_first(c for c in candidates if fresh(c))
    lead_ids = {c.id for c in lead}
    suggested = _best_first(c for c in candidates if c.reason == "suggested")
    older = [c for c in candidates if c.reason in ("following", "own") and c.id not in lead_ids]
    trekly = _newest_first(c for c in candidates if c.reason == "trekly")
    demo = _best_first(c for c in candidates if c.reason == "demo")

    b = _Builder()
    # 1. Fresh followed and own posts, with suggestions mixed in.
    followed_shown = 0
    since_suggestion = 0
    while lead:
        room = b.non_followed_run < MAX_NON_FOLLOWED_RUN
        if room and b.trekly_due(trekly):
            b.add(trekly.pop(0))
            continue
        if room and suggested and since_suggestion >= SUGGEST_EVERY:
            b.add(b.take(suggested))
            since_suggestion = 0
            continue
        if room and suggested and not b.other_author_in(lead) and b.other_author_in(suggested):
            # Rather than the same author twice, a suggestion between.
            b.add(b.take(suggested))
            since_suggestion = 0
            continue
        post = b.take(lead)
        followed_shown += post.reason == "following"
        since_suggestion += 1
        b.add(post)
    if followed_shown:
        b.divider()

    # 2. Everything else from real hikers, best first.
    rest = _best_first([*suggested, *older])
    while rest:
        if b.trekly_due(trekly):
            b.add(trekly.pop(0))
            continue
        b.add(b.take(rest))
    # 3. Demo accounts' posts, only after every real hiker's.
    while demo:
        if b.trekly_due(trekly):
            b.add(trekly.pop(0))
            continue
        b.add(b.take(demo))
    # Whatever @trekly posts are left go in only while the spacing allows,
    # but a short feed still gets its first one.
    if trekly and (b.trekly_due(trekly) or not b.trekly_shown):
        b.add(trekly.pop(0))

    # 4. Picks: early on while it's quiet, and to close the feed.
    out = b.out
    if picks:
        queue = list(range(picks))
        if sparse:
            mixed: list[Entry] = []
            for index, entry in enumerate(out):
                mixed.append(entry)
                if (index + 1) % PICK_EVERY == 0 and queue:
                    mixed.append(Entry("pick", pick=queue.pop(0)))
            out = mixed
        out = [*out, *(Entry("pick", pick=n) for n in queue)]
    return out


# ------------------------------------------------------------------ the database


def reader_for(db: Session, viewer_id: UUID | None) -> Reader:
    if viewer_id is None:
        return Reader()
    profile = db.get(Profile, viewer_id)
    prefs = db.get(ProfilePreferences, viewer_id)
    blocked = set(db.scalars(select(Block.blocked_id).where(Block.blocker_id == viewer_id)))
    blocked |= set(db.scalars(select(Block.blocker_id).where(Block.blocked_id == viewer_id)))
    return Reader(
        id=viewer_id,
        following=set(db.scalars(select(Follow.followee_id).where(
            Follow.follower_id == viewer_id, Follow.status == "accepted"))),
        hiked=set(db.scalars(select(HikeLog.trail_id).where(HikeLog.user_id == viewer_id))),
        saved=set(db.scalars(select(SavedTrail.trail_id).where(SavedTrail.user_id == viewer_id))),
        parks={PARK_BY_REGION[slug] for slug in (prefs.favourite_regions if prefs else None) or ()
               if slug in PARK_BY_REGION},
        province=profile.home_province if profile else None,
        blocked=blocked,
    )


def feed_query(today: date, reader: Reader):
    """The feed's cards for this reader: readable (app/activity.py), not folded
    into a hike post, and nobody blocked either way."""
    query = readable_query(today, reader.id).where(~folded_where(today, reader.id))
    if reader.blocked:
        query = query.where(ActivityPost.user_id.not_in(reader.blocked))
    return query


def candidates(db: Session, today: date, reader: Reader, as_of: datetime) -> list[Candidate]:
    """The newest POOL_SIZE cards up to `as_of`, with what the ranking needs."""
    trail_id = func.coalesce(HikeLog.trail_id, ActivityPost.trail_id)
    rows = db.execute(
        feed_query(today, reader)
        .where(ActivityPost.created_at <= as_of)
        .with_only_columns(
            ActivityPost.id, ActivityPost.user_id, ActivityPost.created_at, trail_id.label("trail_id"),
            Profile.home_province, ProfileSettings.show_home_province,
        )
        .order_by(ActivityPost.created_at.desc(), ActivityPost.id.desc())
        .limit(POOL_SIZE)
    ).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    counts = dict(db.execute(
        select(ActivityReaction.post_id, func.count()).where(ActivityReaction.post_id.in_(ids))
        .group_by(ActivityReaction.post_id)
    ).all())
    trail_ids = {row.trail_id for row in rows if row.trail_id is not None}
    trails = {
        t.id: (t.park_name, t.province_code)
        for t in db.execute(select(Trail.id, Trail.park_name, Trail.province_code).where(Trail.id.in_(trail_ids)))
    } if trail_ids else {}
    labels = labels_for(db, (row.user_id for row in rows))
    out = []
    for row in rows:
        label = labels.get(row.user_id)
        if row.user_id == reader.id:
            reason: Reason = "own"
        elif label == "official":
            reason = "trekly"
        elif label == "demo":
            reason = "demo"
        elif row.user_id in reader.following:
            reason = "following"
        else:
            reason = "suggested"
        park, province = trails.get(row.trail_id, (None, None))
        out.append(Candidate(
            id=row.id, user_id=row.user_id, created_at=row.created_at, reason=reason, trail_id=row.trail_id,
            park_name=park, trail_province=province,
            author_province=row.home_province if row.show_home_province else None,
            high_fives=counts.get(row.id, 0),
        ))
    return out


def new_since(db: Session, today: date, reader: Reader, since: datetime) -> int:
    """Followed hikers' posts made after `since` that the feed would show now
    (others can see them: never the viewer's own)."""
    if not reader.following:
        return 0
    query = (
        _joined().where(visible_where(today), ~folded_where(today, reader.id))
        .where(ActivityPost.user_id.in_(reader.following), ActivityPost.created_at > since)
    )
    if reader.blocked:
        query = query.where(ActivityPost.user_id.not_in(reader.blocked))
    sub = query.with_only_columns(ActivityPost.id).subquery()
    return db.scalar(select(func.count()).select_from(sub)) or 0


# ------------------------------------------------------------------ cursors


def make_cursor(as_of: datetime, offset: int) -> str:
    return f"{_aware(as_of).isoformat()}~{offset}"


def parse_cursor(cursor: str) -> tuple[datetime, int]:
    """(as_of, offset); ValueError when it isn't one of ours."""
    when, sep, offset = cursor.rpartition("~")
    if not sep:
        raise ValueError(cursor)
    position = int(offset)
    if position < 0:
        raise ValueError(cursor)
    return _aware(datetime.fromisoformat(when)), position

