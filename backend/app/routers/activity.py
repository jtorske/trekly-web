"""The Activity page: a feed of what hikers have recently done.

GET /api/activity is open to guests: one blended feed (no tabs), arranged by
app/feed.py: posts from people you follow first, then suggestions ranked for
you, @trekly posts mixed in, demo accounts last and "Trekly picks" so it's
never empty. Signed in, each post also says whether you high-fived it,
whether it's yours and whether you follow its author, and why it's in your
feed (`reason`). Posts come and go by the rules in app/activity.py (and
blocks, app/feed.py); nothing is cached, so a privacy change applies to the
next request. Your own posts that others can't see come back to you alone,
flagged only_you. The milestones and rank a hike earned ride inside that
hike's post (`earned`).

Who high-fived lists hikers the reader may see (public profiles, ones they
follow); private profiles and blocked hikers are only a count.
Trending trails are counts across everyone, never who.

Every response is built from the models below, so only declared fields
leave the API: never a user id, email, the hike's created date, or the
date of a hike whose owner hides dates.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import and_, exists, false, func, or_, select, true, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import follows
from app.account_labels import AccountLabelName, labels_for, may_interact, real_user
from app.picks import SPARSE_BELOW, PickKind, picks, real_posts_this_week
from app.trail_photos import public_photo_url
from app.activity import (
    MILESTONES, UNPOSTED_CATEGORIES, activity_open, backfill_posts, can_share, past_hikes_waiting, share_past_hikes,
    folded_where, is_visible, readable_query,
)
from app import feed as blend
from app.comments import CommentOut, blocked_either_way, is_blocked, previews
from app.auth import CurrentUser, TokenVerifier, bearer_scheme, get_current_user, get_verifier_dependency
from app.database import get_db
from app.follows import FollowState
from app.milestone_dates import BadgeDates
from app.milestones import MilestoneBadgeOut, badge_out
from app.moderation import review_state, withheld_items
from app.notifications import notify, retract
from app.models.account import Profile, SavedTrail
from app.models.activity import ActivityPost, ActivityReaction
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileSettings
from app.models.social import Follow
from app.models.trail import Trail
from app.points_config import RANKS
from app.privacy import Visibility, ensure_settings, visibility
from app.routers.availability import get_today
from app.routers.trails import live_trails
from app.schemas.trail import TrailListItemOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])
# A profile's Activity tab (/u/{username}), and the owner's own view of theirs (/profile).
profile_router = APIRouter(prefix="/api/profiles", tags=["activity"])
me_router = APIRouter(prefix="/api/me/activity", tags=["activity"])

PAGE_SIZE = 20
NO_STORE = {"Cache-Control": "no-store"}
TRENDING_DAYS = 7
TRENDING_SIZE = 5
HIGH_FIVERS_SHOWN = 20


class ActivityHiker(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    # "official": the Trekly account ("Trekly team" badge); "demo": a demo
    # hiker ("Demo account" badge). None for everyone else.
    label: AccountLabelName | None = None


class ActivityAuthor(ActivityHiker):
    # Signed in, and not your own post: whether you follow them.
    follow: FollowState | None = None


class ActivityHike(BaseModel):
    trail: TrailListItemOut
    # None when the owner hides their hike dates, or it's from before they joined.
    hiked_on: date | None
    note: str | None
    # In the hike-photos bucket; visible to anyone while the journal is public.
    photo_path: str | None
    verified: bool


class ActivityRank(BaseModel):
    level: int
    title: str


class ActivityEarned(BaseModel):
    """A milestone or rank a hike earned, folded into that hike's post."""

    kind: Literal["milestone", "rank"]
    milestone: MilestoneBadgeOut | None = None
    rank: ActivityRank | None = None


class ActivityAnnouncement(BaseModel):
    """A post from the official Trekly account."""

    body: str
    trail: TrailListItemOut | None = None
    # Public URL in the trail-photos bucket.
    photo_url: str | None = None
    # The official page an automatic post quotes or cites (a Parks Canada
    # bulletin, a fact's source), with its label and date.
    source_url: str | None = None
    source_label: str | None = None
    source_date: date | None = None


FeedReason = Literal["own", "following", "suggested", "trekly", "demo"]


class ActivityPostOut(BaseModel):
    id: UUID
    kind: Literal["hike", "milestone", "rank", "announcement"]
    author: ActivityAuthor
    # When it was posted; None when the owner hides their hike dates.
    posted_at: datetime | None
    # Its author changed the hike's note, photo or date since posting ("Edited"),
    # and when (None while they hide their hike dates).
    edited: bool = False
    edited_at: datetime | None = None
    hike: ActivityHike | None = None
    announcement: ActivityAnnouncement | None = None
    milestone: MilestoneBadgeOut | None = None
    rank: ActivityRank | None = None
    # A hike post: the milestones, then the rank, that hike earned.
    earned: list[ActivityEarned] = []
    high_fives: int
    # Signed in only: you high-fived it / it's your own post / it's yours and
    # nobody else can see it (sharing off, private profile, hidden journal…).
    high_fived: bool = False
    mine: bool = False
    only_you: bool = False
    # Yours, and never shared (whatever your settings): see app/activity.py backfill_posts.
    unshared: bool = False
    # Your own post only: held for review ("pending") or removed by a
    # moderator ("hidden"), wholly or its note or photo. Nobody else sees it.
    review: Literal["pending", "hidden"] | None = None
    # The Activity feed only: why it's in your feed. "suggested" posts get a
    # "Suggested for you" line and a Follow button.
    reason: FeedReason | None = None
    # Comments this reader can see, and the newest few (oldest first; app/comments.py).
    comment_count: int = 0
    comments: list[CommentOut] = []
    # Its author turned comments off: no box, "Comments are off".
    comments_off: bool = False
    # Signed in and comments are on (posting checks the rest).
    can_comment: bool = False


class TopPost(BaseModel):
    id: UUID
    # What it's about: a trail, a badge or a rank name.
    title: str
    high_fives: int


class ActivitySummary(BaseModel):
    """The owner's own Activity tab only: what their posts have received."""

    high_fives: int
    # Their most high-fived post (the newest of any tie); None until one has a high five.
    top_post: TopPost | None = None


class ProfileActivityPage(BaseModel):
    items: list[ActivityPostOut]
    # Pass back as `cursor` for the next page; None at the end.
    next_cursor: str | None
    # How many posts in all; on the first page only (None when a cursor is passed).
    total: int | None = None
    # The owner's view only: whether others can see their posts right now.
    sharing: bool | None = None
    # The owner's first page only: how many never-shared hikes the one-time
    # "Share your past hikes?" prompt offers to share (0: don't ask; None: not the owner).
    past_hikes: int | None = None
    # The owner's first page only: high fives received and their top post.
    summary: ActivitySummary | None = None


class PastHikesIn(BaseModel):
    share: bool


class PastHikesOut(BaseModel):
    shared: int


class FeedHiker(BaseModel):
    """A hiker the "Follow hikers to see their hikes here" card suggests
    (the same fields as people search, app/routers/hiker_search.py)."""

    username: str
    display_name: str | None
    avatar_path: str | None
    is_private: bool
    follow: FollowState
    rank: ActivityRank | None = None
    home_province: str | None = None
    common_trails: int | None = None
    same_province: bool = False


class PickOut(BaseModel):
    kind: PickKind
    title: str
    text: str
    trail: TrailListItemOut


class FeedEntryOut(BaseModel):
    """One slot in the feed, in order: a post (in `items`), the "You're all
    caught up" divider, or a "Trekly pick"."""

    type: Literal["post", "caught_up", "pick"]
    post_id: UUID | None = None
    pick: PickOut | None = None


class ActivityPage(BaseModel):
    # This page's posts, in feed order.
    items: list[ActivityPostOut]
    # The page in order, posts by id, with the divider and picks between them.
    entries: list[FeedEntryOut]
    # Pass back as `cursor` for the next page; None at the end.
    next_cursor: str | None
    # When the feed was arranged; GET /api/activity/new counts posts since.
    as_of: datetime
    # Signed in and following someone.
    follows_anyone: bool = False
    # The first page, signed in and following nobody: up to three hikers to follow.
    suggested_hikers: list[FeedHiker] | None = None


class NewPostsOut(BaseModel):
    # Posts from people you follow since `since`, that the feed would show.
    count: int


class HighFiveOut(BaseModel):
    high_fives: int
    high_fived: bool


class HighFiver(ActivityHiker):
    # Signed in, and not you: whether you follow them (the list's Follow button).
    follow: FollowState | None = None
    is_private: bool = False


class HighFiversOut(BaseModel):
    high_fives: int
    # Newest first: hikers this reader may see (a public profile, one they
    # follow, or themselves), never anyone blocked either way.
    hikers: list[HighFiver]
    # The rest ("and 2 others"): private profiles, blocked hikers, and anyone
    # past the list's length.
    others: int


class TrendingTrailOut(BaseModel):
    trail: TrailListItemOut
    # Logged or saved in the last week; False tops the list up with popular trails.
    this_week: bool


class TrendingOut(BaseModel):
    trails: list[TrendingTrailOut]


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: TokenVerifier = Depends(get_verifier_dependency),
) -> CurrentUser | None:
    """The signed-in user, or None for a guest. A bad token is still a 401,
    so an expired session isn't silently treated as a guest."""
    if credentials is None:
        return None
    return get_current_user(credentials, verifier)


def _cursor(post: ActivityPost) -> str:
    return f"{post.created_at.isoformat()}~{post.id}"


def _parse_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        when, _, post_id = cursor.partition("~")
        return datetime.fromisoformat(when), UUID(post_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="That page link isn't valid.") from error


def _counts(db: Session, post_ids: list[UUID]) -> dict[UUID, int]:
    if not post_ids:
        return {}
    rows = db.execute(
        select(ActivityReaction.post_id, func.count())
        .where(ActivityReaction.post_id.in_(post_ids))
        .group_by(ActivityReaction.post_id)
    )
    return {post_id: count for post_id, count in rows}


def _rank(level: int | None) -> ActivityRank | None:
    if level is None or not 1 <= level <= len(RANKS):
        return None
    return ActivityRank(level=level, title=RANKS[level - 1][1])


def _author(profile: Profile) -> ActivityAuthor:
    return ActivityAuthor(username=profile.username or "", display_name=profile.display_name,
                          avatar_path=profile.avatar_path)


def _milestone(post: ActivityPost, hide_dates: bool, badge_dates: BadgeDates | None) -> MilestoneBadgeOut | None:
    milestone = MILESTONES.get(post.milestone)
    # Retired from the milestone list, or a kind that's never posted.
    if milestone is None or milestone.category in UNPOSTED_CATEGORIES:
        return None
    # When they earned it, as their journal says; none while they hide dates.
    earned_on, earned_with = None, None
    if not hide_dates and badge_dates is not None:
        earned_on, earned_with = badge_dates(post.user_id, milestone.id)
    return badge_out(milestone, earned_on, earned_with)


def _earned(post: ActivityPost, hide_dates: bool, badge_dates: BadgeDates | None) -> ActivityEarned | None:
    if post.kind == "milestone":
        milestone = _milestone(post, hide_dates, badge_dates)
        return ActivityEarned(kind="milestone", milestone=milestone) if milestone else None
    rank = _rank(post.rank_level)
    return ActivityEarned(kind="rank", rank=rank) if rank else None


def _out(post, profile, settings, log, public, counts, mine_ids, viewer, badge_dates=None) -> ActivityPostOut | None:
    hide_dates = bool(settings.hide_hike_dates)
    mine = viewer is not None and post.user_id == viewer.id
    out = ActivityPostOut(
        id=post.id,
        kind=post.kind,
        author=_author(profile),
        posted_at=None if hide_dates else post.created_at,
        high_fives=counts.get(post.id, 0),
        high_fived=post.id in mine_ids,
        mine=mine,
        only_you=mine and not public,
        unshared=mine and bool(post.owner_only),
        edited=post.edited_at is not None,
        edited_at=None if hide_dates else post.edited_at,
    )
    if post.kind == "hike":
        out.hike = ActivityHike(
            trail=TrailListItemOut.model_validate(log.trail),
            hiked_on=None if hide_dates else log.hiked_on,
            note=log.note,
            photo_path=log.photo_path,
            verified=bool(log.verified),
        )
    elif post.kind == "announcement":
        if not post.body:
            return None
        live = post.trail is not None and post.trail.retired_at is None
        out.announcement = ActivityAnnouncement(
            body=post.body,
            trail=TrailListItemOut.model_validate(post.trail) if live else None,
            photo_url=public_photo_url(post.photo_path) if post.photo_path else None,
            source_url=post.source_url,
            source_label=post.source_label,
            source_date=post.source_date,
        )
    elif post.kind == "milestone":
        out.milestone = _milestone(post, hide_dates, badge_dates)
        if out.milestone is None:
            return None
    else:
        out.rank = _rank(post.rank_level)
        if out.rank is None:
            return None
    return out


def _fold_earned(db: Session, kept: list, today: date, viewer_id: UUID | None, badge_dates: BadgeDates) -> None:
    """Fills each hike post's `earned` with what that hike earned, as this
    reader may see it: a rank hidden from others stays out of a public post."""
    hikes = {row[0].hike_log_id: (item, row[4]) for item, row in kept if item.kind == "hike"}
    if not hikes:
        return
    children = db.execute(
        readable_query(today, viewer_id)
        .where(ActivityPost.kind != "hike", ActivityPost.hike_log_id.in_(list(hikes)))
        .order_by(ActivityPost.created_at, ActivityPost.milestone)
    ).all()
    for post, _profile, settings, _log, public in children:
        item, hike_public = hikes[post.hike_log_id]
        if hike_public and not public:
            continue
        earned = _earned(post, bool(settings.hide_hike_dates), badge_dates)
        if earned is not None:
            item.earned.append(earned)


@router.get("/trending", response_model=TrendingOut)
def trending(db: Session = Depends(get_db), limit: int = Query(default=TRENDING_SIZE, ge=1, le=10)):
    """Trails most logged or saved in the last week (each log or save counts
    once), topped up with the most popular trails when the week was quiet.
    Only real hikers count: demo and official accounts are left out."""
    return TrendingOut(trails=trending_trails(db, limit))


def trending_trails(db: Session, limit: int) -> list[TrendingTrailOut]:
    since = datetime.now().astimezone() - timedelta(days=TRENDING_DAYS)
    recent = union_all(
        select(HikeLog.trail_id.label("trail_id")).where(HikeLog.created_at >= since, real_user(HikeLog.user_id)),
        select(SavedTrail.trail_id.label("trail_id")).where(SavedTrail.created_at >= since,
                                                            real_user(SavedTrail.user_id)),
    ).subquery()
    counts = select(recent.c.trail_id, func.count().label("n")).group_by(recent.c.trail_id).subquery()
    hot = db.scalars(
        select(Trail).join(counts, counts.c.trail_id == Trail.id).where(*live_trails())
        .order_by(counts.c.n.desc(), Trail.popularity_rank, Trail.name).limit(limit)
    ).all()
    out = [TrendingTrailOut(trail=TrailListItemOut.model_validate(trail), this_week=True) for trail in hot]
    if len(out) < limit:
        taken = [trail.id for trail in hot]
        fill = db.scalars(
            select(Trail).where(*live_trails(), Trail.id.not_in(taken) if taken else true())
            .order_by(Trail.popularity_rank, Trail.name).limit(limit - len(out))
        ).all()
        out += [TrendingTrailOut(trail=TrailListItemOut.model_validate(trail), this_week=False) for trail in fill]
    return out


class PicksOut(BaseModel):
    # True while real hikers shared fewer than ~10 posts this week: show the picks.
    sparse: bool
    picks: list[PickOut]


@router.get("/picks", response_model=PicksOut)
def feed_picks(response: Response, db: Session = Depends(get_db), today: date = Depends(get_today)):
    """"Trekly picks" for a quiet feed (app/picks.py). Empty once it isn't quiet."""
    response.headers.update(NO_STORE)
    if real_posts_this_week(db, today) >= SPARSE_BELOW:
        return PicksOut(sparse=False, picks=[])
    chosen = picks(db, today, trending_trails(db, 1), live_trails())
    return PicksOut(sparse=True, picks=[
        PickOut(kind=p.kind, title=p.title, text=p.text, trail=TrailListItemOut.model_validate(p.trail))
        for p in chosen
    ])


def _cards(today: date, viewer_id: UUID | None):
    """Posts as this reader sees them as cards: what anyone may see plus their
    own, with milestones and ranks folded into the hike that earned them."""
    return readable_query(today, viewer_id).where(~folded_where(today, viewer_id))


def _page(db: Session, query, cursor: str | None, limit: int, viewer: CurrentUser | None,
          today: date) -> tuple[list[ActivityPostOut], str | None]:
    """One page of cards, newest first, and the cursor for the next."""
    query = query.options(joinedload(HikeLog.trail), joinedload(ActivityPost.trail))
    if cursor:
        when, post_id = _parse_cursor(cursor)
        query = query.where(or_(
            ActivityPost.created_at < when,
            and_(ActivityPost.created_at == when, ActivityPost.id < post_id),
        ))
    rows = db.execute(
        query.order_by(ActivityPost.created_at.desc(), ActivityPost.id.desc()).limit(limit + 1)
    ).unique().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return _hydrate(db, rows, viewer, today), (_cursor(rows[-1][0]) if more else None)


def _hydrate(db: Session, rows: list, viewer: CurrentUser | None, today: date) -> list[ActivityPostOut]:
    """Cards for rows of readable_query, in their order (dropping any that can't show)."""
    post_ids = [row[0].id for row in rows]
    counts = _counts(db, post_ids)
    mine_ids = set(db.scalars(
        select(ActivityReaction.post_id).where(ActivityReaction.user_id == viewer.id,
                                               ActivityReaction.post_id.in_(post_ids))
    )) if viewer and post_ids else set()
    badge_dates = BadgeDates(db)
    kept = [
        (item, row) for item, row in ((_out(*row, counts, mine_ids, viewer, badge_dates), row) for row in rows)
        if item is not None
    ]
    _fold_earned(db, kept, today, viewer.id if viewer else None, badge_dates)
    _overlay_reviews(db, kept)
    talk = previews(db, [row[0] for _, row in kept], viewer.id if viewer else None)
    for item, row in kept:
        found = talk.get(item.id)
        if found is not None:
            item.comment_count, item.comments = found.count, found.preview
        item.comments_off = bool(row[0].comments_off)
        item.can_comment = viewer is not None and not item.comments_off
    labels = labels_for(db, (row[0].user_id for _, row in kept))
    for item, row in kept:
        item.author.label = labels.get(row[0].user_id)
    # Signed in: whether you follow each author (not on your own posts).
    if viewer is not None:
        states = follows.states(db, viewer.id, {row[0].user_id for _, row in kept})
        for item, row in kept:
            if not item.mine:
                item.author.follow = states.get(row[0].user_id, "none")
    return [item for item, _ in kept]


def _overlay_reviews(db: Session, kept: list) -> None:
    """On the reader's own posts: anything moderation is holding back,
    shown back to them with its review state."""
    own = [(item, row) for item, row in kept if item.mine]
    if not own:
        return
    logs = {row[0].hike_log_id for _, row in own if row[0].hike_log_id}
    held = withheld_items(db, ("post", "hike_note", "hike_photo"), [*(row[0].id for _, row in own), *logs])
    for item, row in own:
        post = row[0]
        post_item = held.get(("post", post.id))
        note_item = held.get(("hike_note", post.hike_log_id))
        photo_item = held.get(("hike_photo", post.hike_log_id))
        state = review_state(post_item, note_item, photo_item)
        if state is None and post.hidden_at is not None:
            state = "hidden"  # hidden by an admin from the old Reports page
        item.review = state
        if item.hike is not None:
            if item.hike.note is None and (note_item or (post_item and post_item.text)):
                item.hike.note = (note_item or post_item).text
            if item.hike.photo_path is None and (photo_item or (post_item and post_item.photo_path)):
                item.hike.photo_path = (photo_item or post_item).photo_path
        if state is not None:
            item.only_you = True


def _count(db: Session, query) -> int:
    """How many cards a listing query holds in all."""
    return db.scalar(select(func.count()).select_from(query.with_only_columns(ActivityPost.id).subquery())) or 0


def _feed_picks(db: Session, today: date) -> tuple[list[PickOut], bool]:
    """The picks the feed closes with, and whether it's quiet (mix them in early)."""
    sparse = real_posts_this_week(db, today) < SPARSE_BELOW
    chosen = picks(db, today, trending_trails(db, 1), live_trails())
    return [
        PickOut(kind=p.kind, title=p.title, text=p.text, trail=TrailListItemOut.model_validate(p.trail))
        for p in chosen
    ], sparse


SUGGESTED_HIKERS = 3


def _suggested_hikers(db: Session, viewer: CurrentUser, entries: list[blend.Entry],
                      finder) -> list[FeedHiker]:
    """For someone who follows nobody: "Hikers you might know" first, then the
    authors of the feed's top suggested posts (public, real hikers), leaving
    out anyone they follow or asked to."""
    from app.hiker_search import cards
    from app.routers.hiker_search import _out

    picked: list[tuple[UUID, bool, int | None, bool]] = []
    try:
        with db.begin_nested():
            for hit in finder.suggest(db, viewer.id, SUGGESTED_HIKERS):
                picked.append((hit.user_id, True, hit.common_trails, True))
    except Exception:  # noqa: BLE001 - the suggestions are optional (and Postgres-only)
        logger.warning("suggest_hikers failed for the feed", exc_info=True)
        picked = []
    taken = {entry[0] for entry in picked}
    states = follows.states(db, viewer.id, [e.post.user_id for e in entries if e.post is not None])
    for entry in entries:
        if len(picked) >= SUGGESTED_HIKERS:
            break
        post = entry.post
        if post is None or post.reason != "suggested" or post.user_id in taken or post.user_id in states:
            continue
        taken.add(post.user_id)
        picked.append((post.user_id, True, None, False))
    found = cards(db, viewer.id, picked[:SUGGESTED_HIKERS])
    return [FeedHiker(**hiker.model_dump()) for hiker in _out(db, viewer.id, found)]


def get_feed_finder():
    """The finder for "Hikers you might know" (overridden in tests)."""
    from app.routers.hiker_search import get_hiker_finder

    return get_hiker_finder()


@router.get("", response_model=ActivityPage)
def feed(
    response: Response,
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    finder=Depends(get_feed_finder),
):
    """One page of the blended feed (app/feed.py). The first page fixes the
    moment it was arranged (`as_of`); later pages, by cursor, arrange the same
    posts the same way, so nothing repeats."""
    response.headers.update(NO_STORE)
    viewer_id = viewer.id if viewer else None
    if cursor:
        try:
            as_of, offset = blend.parse_cursor(cursor)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="That page link isn't valid.") from error
    else:
        as_of, offset = datetime.now(timezone.utc), 0
    reader = blend.reader_for(db, viewer_id)
    pool = blend.candidates(db, today, reader, as_of)
    pick_cards, sparse = _feed_picks(db, today)
    entries = blend.arrange(pool, reader, as_of, picks=len(pick_cards), sparse=sparse)
    window = entries[offset:offset + limit]

    ids = [entry.post.id for entry in window if entry.post is not None]
    rows = db.execute(
        readable_query(today, viewer_id).where(ActivityPost.id.in_(ids))
        .options(joinedload(HikeLog.trail), joinedload(ActivityPost.trail))
    ).unique().all() if ids else []
    by_id = {row[0].id: row for row in rows}
    items = _hydrate(db, [by_id[i] for i in ids if i in by_id], viewer, today)
    reasons = {entry.post.id: entry.post.reason for entry in window if entry.post is not None}
    for item in items:
        item.reason = reasons.get(item.id)
    shown = {item.id for item in items}
    out = []
    for entry in window:
        if entry.type == "post":
            if entry.post.id in shown:
                out.append(FeedEntryOut(type="post", post_id=entry.post.id))
        elif entry.type == "pick":
            out.append(FeedEntryOut(type="pick", pick=pick_cards[entry.pick]))
        else:
            out.append(FeedEntryOut(type="caught_up"))

    end = offset + limit
    hikers = None
    if viewer is not None and offset == 0 and not reader.following:
        # Optional: a failure here leaves the box empty, never fails the feed.
        try:
            with db.begin_nested():
                hikers = _suggested_hikers(db, viewer, entries, finder)
        except Exception:  # noqa: BLE001
            logger.exception("suggested hikers failed; feed served without them")
            hikers = []
    return ActivityPage(
        items=items,
        entries=out,
        next_cursor=blend.make_cursor(as_of, end) if end < len(entries) else None,
        as_of=as_of,
        follows_anyone=bool(reader.following),
        suggested_hikers=hikers,
    )


@router.get("/new", response_model=NewPostsOut)
def new_posts(
    response: Response,
    since: datetime = Query(...),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """How many posts from people you follow arrived after `since` (the
    page's `as_of`), for the "New posts" pill. Guests: always 0."""
    response.headers.update(NO_STORE)
    if viewer is None:
        return NewPostsOut(count=0)
    reader = blend.reader_for(db, viewer.id)
    since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    return NewPostsOut(count=blend.new_since(db, today, reader, since))


def _visible_or_404(db: Session, post_id: UUID, today: date) -> None:
    if not is_visible(db, post_id, today):
        raise HTTPException(status_code=404, detail="Post not found")


def _high_five_out(db: Session, post_id: UUID, user_id: UUID) -> HighFiveOut:
    count = db.scalar(select(func.count()).select_from(ActivityReaction).where(ActivityReaction.post_id == post_id))
    mine = db.get(ActivityReaction, (post_id, user_id)) is not None
    return HighFiveOut(high_fives=count or 0, high_fived=mine)


@router.get("/{post_id}/high-fives", response_model=HighFiversOut)
def high_fivers(
    post_id: UUID,
    response: Response,
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Who high-fived a post anyone can see (or your own), newest first: hikers
    with a public profile, ones you follow and you yourself by name, with your
    follow state toward each; private profiles and anyone blocked either way
    only in the count. Never between you and a post's author who blocked you
    (or whom you blocked)."""
    response.headers.update(NO_STORE)
    post = db.get(ActivityPost, post_id)
    own = post is not None and viewer is not None and post.user_id == viewer.id and post.hidden_at is None
    blocked = post is not None and viewer is not None and not own and is_blocked(db, post.user_id, viewer.id)
    if post is None or blocked or not (own or is_visible(db, post_id, today)):
        raise HTTPException(status_code=404, detail="Post not found")
    total = db.scalar(
        select(func.count()).select_from(ActivityReaction).where(ActivityReaction.post_id == post_id)
    ) or 0
    viewer_id = viewer.id if viewer else None
    seen = ~ProfileSettings.is_private
    if viewer_id is not None:
        followed = exists().where(Follow.follower_id == viewer_id, Follow.followee_id == Profile.id,
                                  Follow.status == "accepted")
        seen = and_(or_(seen, followed, Profile.id == viewer_id), ~blocked_either_way(Profile.id, viewer_id))
    rows = db.execute(
        select(Profile, ProfileSettings.is_private)
        .join(ActivityReaction, ActivityReaction.user_id == Profile.id)
        .join(ProfileSettings, ProfileSettings.user_id == Profile.id)
        .where(
            ActivityReaction.post_id == post_id,
            Profile.username.is_not(None),
            ~exists().where(ProfileModeration.user_id == Profile.id),
            seen,
        )
        .order_by(ActivityReaction.created_at.desc(), Profile.username)
        .limit(HIGH_FIVERS_SHOWN)
    ).all()
    labels = labels_for(db, (p.id for p, _ in rows))
    states = follows.states(db, viewer_id, [p.id for p, _ in rows if p.id != viewer_id]) if viewer_id else {}
    out = [
        HighFiver(**_author(p).model_dump(include={"username", "display_name", "avatar_path"}),
                  label=labels.get(p.id), is_private=bool(private),
                  follow=None if viewer_id is None or p.id == viewer_id else states.get(p.id, "none"))
        for p, private in rows
    ]
    return HighFiversOut(high_fives=total, hikers=out, others=total - len(out))


@router.get("/{post_id}", response_model=ActivityPostOut)
def one_post(
    post_id: UUID,
    response: Response,
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """One post's own page (/activity/{id}), by the feed's rules: anyone may
    see it, or it's yours; never between blocked hikers. A milestone or rank
    folded into its hike shows as that hike."""
    response.headers.update(NO_STORE)
    viewer_id = viewer.id if viewer else None
    query = readable_query(today, viewer_id).where(ActivityPost.id == post_id)
    if viewer_id is not None:
        query = query.where(~blocked_either_way(ActivityPost.user_id, viewer_id))
    row = db.execute(query.options(joinedload(HikeLog.trail), joinedload(ActivityPost.trail))).unique().first()
    if row is not None and db.scalar(select(exists(
        _cards(today, viewer_id).where(ActivityPost.id == post_id).with_only_columns(ActivityPost.id)
    ))) is False:
        # Folded into its hike: show that.
        hike = db.execute(
            readable_query(today, viewer_id)
            .where(ActivityPost.kind == "hike", ActivityPost.hike_log_id == row[0].hike_log_id)
            .options(joinedload(HikeLog.trail), joinedload(ActivityPost.trail))
        ).unique().first()
        row = hike or row
    items = _hydrate(db, [row], viewer, today) if row is not None else []
    if not items:
        raise HTTPException(status_code=404, detail="Post not found")
    return items[0]


@router.put("/{post_id}/high-five", response_model=HighFiveOut)
def high_five(
    post_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Idempotent: a second high five from the same person changes nothing.
    A demo account may high-five only another demo account's post."""
    _visible_or_404(db, post_id, today)
    if not may_interact(db, user.id, db.get(ActivityPost, post_id).user_id):
        raise HTTPException(status_code=403, detail="Demo accounts only interact with other demo accounts.")
    if db.get(ActivityReaction, (post_id, user.id)) is None:
        db.add(ActivityReaction(post_id=post_id, user_id=user.id, created_at=datetime.now().astimezone()))
        try:
            db.flush()
            notify(db, db.get(ActivityPost, post_id).user_id, user.id, "high_five", post_id)
            db.commit()
        except IntegrityError:
            db.rollback()  # a concurrent request got there first
    return _high_five_out(db, post_id, user.id)


@router.delete("/{post_id}/high-five", response_model=HighFiveOut)
def undo_high_five(
    post_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    _visible_or_404(db, post_id, today)
    row = db.get(ActivityReaction, (post_id, user.id))
    if row is not None:
        db.delete(row)
        retract(db, db.get(ActivityPost, post_id).user_id, user.id, "high_five", post_id)
        db.commit()
    return _high_five_out(db, post_id, user.id)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: UUID, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Owners can delete any of their posts, shown or not. A hike post takes
    the milestones and rank folded into it along with it. The hike stays in
    the journal, and the badges stay earned."""
    post = db.get(ActivityPost, post_id)
    if post is None or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.kind == "hike":
        # Off the feed for good: the profile's backfill won't post it again.
        log = db.get(HikeLog, post.hike_log_id)
        if log is not None:
            log.unshared = True
        for child in db.scalars(select(ActivityPost).where(
            ActivityPost.user_id == user.id,
            ActivityPost.kind != "hike",
            ActivityPost.hike_log_id == post.hike_log_id,
        )):
            db.delete(child)
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------- a profile's Activity tab


def _profile_cards(profile: Profile, today: date, viewer_id: UUID | None):
    return _cards(today, viewer_id).where(ActivityPost.user_id == profile.id)


def profile_activity_count(db: Session, profile: Profile, seen: Visibility, today: date) -> int | None:
    """The Activity tab's count for visitors, or None when there's no tab for them."""
    if not activity_open(seen):
        return None
    return _count(db, _profile_cards(profile, today, None))


@profile_router.get("/{username}/activity", response_model=ProfileActivityPage)
def profile_activity(
    username: str,
    response: Response,
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """The Activity tab on /u/{username}: their posts as the feed shows them,
    by the feed's own rules. 404 unless the tab is open to visitors (a public
    profile with sharing on; app/activity.py activity_open). The owner here
    sees what the feed shows them: their posts, marked "only you" where so."""
    response.headers.update(NO_STORE)
    profile = db.scalar(select(Profile).where(Profile.username == username.strip().lower()))
    seen = visibility(db, profile) if profile is not None else None
    if seen is None or not seen.listed or not activity_open(seen):
        raise HTTPException(status_code=404, detail="No activity to show")
    if viewer is not None and viewer.id != profile.id and db.scalar(select(blocked_either_way(profile.id, viewer.id))):
        raise HTTPException(status_code=404, detail="No activity to show")
    query = _profile_cards(profile, today, viewer.id if viewer else None)
    items, next_cursor = _page(db, query, cursor, limit, viewer, today)
    total = None if cursor else _count(db, _profile_cards(profile, today, None))
    return ProfileActivityPage(items=items, next_cursor=next_cursor, total=total)


@me_router.get("", response_model=ProfileActivityPage)
def my_activity(
    response: Response,
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """The owner's Activity tab on /profile: all their posts, shown to others
    or not (those are marked only_you). `sharing`: whether others can see them."""
    response.headers.update(NO_STORE)
    if cursor is None:
        # Hikes that never posted (sharing was off, onboarding, past hikes) post now.
        backfill_posts(db, user.id, today)
    query = _cards(today, user.id).where(ActivityPost.user_id == user.id)
    items, next_cursor = _page(db, query, cursor, limit, user, today)
    sharing = can_share(db, user.id)
    settings = db.get(ProfileSettings, user.id)
    ask = cursor is None and sharing and settings is not None and settings.past_hikes_answered_at is None
    return ProfileActivityPage(
        items=items,
        next_cursor=next_cursor,
        total=None if cursor else _count(db, query),
        sharing=sharing,
        past_hikes=past_hikes_waiting(db, user.id) if ask else 0,
        summary=None if cursor else _summary(db, user.id),
    )


def _summary(db: Session, user_id: UUID) -> ActivitySummary:
    """High fives on all their posts, and the post with the most (by anyone,
    whoever can see it now: it's their own count)."""
    from app.routers.notifications import _post_title

    counts = (
        select(ActivityReaction.post_id, func.count().label("n"))
        .join(ActivityPost, ActivityPost.id == ActivityReaction.post_id)
        .where(ActivityPost.user_id == user_id)
        .group_by(ActivityReaction.post_id)
        .subquery()
    )
    total = db.scalar(select(func.coalesce(func.sum(counts.c.n), 0))) or 0
    top = db.execute(
        select(ActivityPost, counts.c.n)
        .join(counts, counts.c.post_id == ActivityPost.id)
        .options(joinedload(ActivityPost.hike_log).joinedload(HikeLog.trail))
        .order_by(counts.c.n.desc(), ActivityPost.created_at.desc())
        .limit(1)
    ).first()
    return ActivitySummary(
        high_fives=int(total),
        top_post=TopPost(id=top[0].id, title=_post_title(top[0]), high_fives=top[1]) if top else None,
    )


@me_router.post("/past-hikes", response_model=PastHikesOut)
def answer_past_hikes(
    payload: PastHikesIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The one-time "Share your past hikes?" prompt: yes shares every hike that
    only the owner sees (except those they unshared), with what each earned;
    either answer puts the prompt away for good."""
    settings = ensure_settings(db, user.id)
    settings.past_hikes_answered_at = datetime.now(timezone.utc)
    db.commit()
    return PastHikesOut(shared=share_past_hikes(db, user.id) if payload.share else 0)
