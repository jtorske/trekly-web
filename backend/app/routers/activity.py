"""The Activity page: a feed of what hikers have recently done.

GET /api/activity is open to guests. Signed in, each post also says whether
you high-fived it and whether it's yours, and "From my province" works once
you've set a home province. Posts come and go by the rules in
app/activity.py; nothing is cached, so a privacy change applies to the
next request. Your own posts that others can't see come back to you alone,
flagged only_you. The milestones and rank a hike earned ride inside that
hike's post (`earned`).

Who high-fived lists only hikers with a public profile; the rest are a count.
Trending trails are counts across everyone, never who.

Every response is built from the models below, so only declared fields
leave the API: never a user id, email, the hike's created date, or the
date of a hike whose owner hides dates.
"""

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import and_, exists, func, or_, select, true, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.activity import (
    MILESTONES, UNPOSTED_CATEGORIES, folded_where, is_visible, province_where, readable_query,
)
from app.auth import CurrentUser, TokenVerifier, bearer_scheme, get_current_user, get_verifier_dependency
from app.database import get_db
from app.milestone_dates import BadgeDates
from app.milestones import MilestoneBadgeOut, badge_out
from app.models.account import Profile, SavedTrail
from app.models.activity import ActivityPost, ActivityReaction
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileSettings
from app.models.trail import Trail
from app.points_config import RANKS
from app.routers.availability import get_today
from app.routers.trails import live_trails
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/activity", tags=["activity"])

PAGE_SIZE = 20
NO_STORE = {"Cache-Control": "no-store"}
TRENDING_DAYS = 7
TRENDING_SIZE = 5
HIGH_FIVERS_SHOWN = 20


class ActivityAuthor(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None


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


class ActivityPostOut(BaseModel):
    id: UUID
    kind: Literal["hike", "milestone", "rank"]
    author: ActivityAuthor
    # When it was posted; None when the owner hides their hike dates.
    posted_at: datetime | None
    hike: ActivityHike | None = None
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


class ActivityPage(BaseModel):
    items: list[ActivityPostOut]
    # Pass back as `cursor` for the next page; None at the end.
    next_cursor: str | None
    # Signed in with a home province: "From my province" can be offered.
    province: str | None = None


class HighFiveOut(BaseModel):
    high_fives: int
    high_fived: bool


class HighFiversOut(BaseModel):
    high_fives: int
    # Newest first; only hikers whose profile is public.
    hikers: list[ActivityAuthor]
    # The rest: private profiles, and anyone past the list's length.
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
    )
    if post.kind == "hike":
        out.hike = ActivityHike(
            trail=TrailListItemOut.model_validate(log.trail),
            hiked_on=None if hide_dates else log.hiked_on,
            note=log.note,
            photo_path=log.photo_path,
            verified=bool(log.verified),
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
    once), topped up with the most popular trails when the week was quiet."""
    since = datetime.now().astimezone() - timedelta(days=TRENDING_DAYS)
    recent = union_all(
        select(HikeLog.trail_id.label("trail_id")).where(HikeLog.created_at >= since),
        select(SavedTrail.trail_id.label("trail_id")).where(SavedTrail.created_at >= since),
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
    return TrendingOut(trails=out)


@router.get("", response_model=ActivityPage)
def feed(
    response: Response,
    scope: Literal["everyone", "province"] = "everyone",
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    response.headers.update(NO_STORE)
    viewer_profile = db.get(Profile, viewer.id) if viewer else None
    province = viewer_profile.home_province if viewer_profile else None
    viewer_id = viewer.id if viewer else None

    query = (
        readable_query(today, viewer_id)
        .where(~folded_where(today, viewer_id))
        .options(joinedload(HikeLog.trail))
    )
    if scope == "province":
        query = query.where(province_where(province))
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
    _fold_earned(db, kept, today, viewer_id, badge_dates)
    return ActivityPage(
        items=[item for item, _ in kept],
        next_cursor=_cursor(rows[-1][0]) if more else None,
        province=province,
    )


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
    """Who high-fived a post anyone can see (or your own): hikers with a public
    profile by name, newest first; everyone else only in the count."""
    response.headers.update(NO_STORE)
    post = db.get(ActivityPost, post_id)
    own = post is not None and viewer is not None and post.user_id == viewer.id and post.hidden_at is None
    if post is None or not (own or is_visible(db, post_id, today)):
        raise HTTPException(status_code=404, detail="Post not found")
    total = db.scalar(
        select(func.count()).select_from(ActivityReaction).where(ActivityReaction.post_id == post_id)
    ) or 0
    hikers = db.scalars(
        select(Profile)
        .join(ActivityReaction, ActivityReaction.user_id == Profile.id)
        .join(ProfileSettings, ProfileSettings.user_id == Profile.id)
        .where(
            ActivityReaction.post_id == post_id,
            Profile.username.is_not(None),
            ~ProfileSettings.is_private,
            ~exists().where(ProfileModeration.user_id == Profile.id),
        )
        .order_by(ActivityReaction.created_at.desc(), Profile.username)
        .limit(HIGH_FIVERS_SHOWN)
    ).all()
    return HighFiversOut(high_fives=total, hikers=[_author(p) for p in hikers], others=total - len(hikers))


@router.put("/{post_id}/high-five", response_model=HighFiveOut)
def high_five(
    post_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Idempotent: a second high five from the same person changes nothing."""
    _visible_or_404(db, post_id, today)
    if db.get(ActivityReaction, (post_id, user.id)) is None:
        db.add(ActivityReaction(post_id=post_id, user_id=user.id, created_at=datetime.now().astimezone()))
        try:
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
        for child in db.scalars(select(ActivityPost).where(
            ActivityPost.user_id == user.id,
            ActivityPost.kind != "hike",
            ActivityPost.hike_log_id == post.hike_log_id,
        )):
            db.delete(child)
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
