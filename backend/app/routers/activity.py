"""The Activity page: a feed of what hikers have recently done.

GET /api/activity is open to guests. Signed in, each post also says whether
you high-fived it and whether it's yours, and "From my province" works once
you've set a home province. Posts come and go by the rules in
app/activity.py; nothing is cached, so a privacy change applies to the
next request.

Every response is built from the models below, so only declared fields
leave the API: never a user id, email, the hike's created date, or the
date of a hike whose owner hides dates.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.activity import MILESTONES, UNPOSTED_CATEGORIES, is_visible, province_where, visible_query
from app.auth import CurrentUser, TokenVerifier, bearer_scheme, get_current_user, get_verifier_dependency
from app.database import get_db
from app.milestones import MilestoneBadgeOut, badge_out
from app.models.account import Profile
from app.models.activity import ActivityPost, ActivityReaction
from app.models.hike_log import HikeLog
from app.points_config import RANKS
from app.routers.availability import get_today
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/activity", tags=["activity"])

PAGE_SIZE = 20
NO_STORE = {"Cache-Control": "no-store"}


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


class ActivityPostOut(BaseModel):
    id: UUID
    kind: Literal["hike", "milestone", "rank"]
    author: ActivityAuthor
    # When it was posted; None when the owner hides their hike dates.
    posted_at: datetime | None
    hike: ActivityHike | None = None
    milestone: MilestoneBadgeOut | None = None
    rank: ActivityRank | None = None
    high_fives: int
    # Signed in only: you high-fived it / it's your own post.
    high_fived: bool = False
    mine: bool = False


class ActivityPage(BaseModel):
    items: list[ActivityPostOut]
    # Pass back as `cursor` for the next page; None at the end.
    next_cursor: str | None
    # Signed in with a home province: "From my province" can be offered.
    province: str | None = None


class HighFiveOut(BaseModel):
    high_fives: int
    high_fived: bool


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


def _rank(level: int) -> ActivityRank | None:
    if not 1 <= level <= len(RANKS):
        return None
    return ActivityRank(level=level, title=RANKS[level - 1][1])


def _out(post, profile, settings, log, counts, mine_ids, viewer) -> ActivityPostOut | None:
    hide_dates = bool(settings.hide_hike_dates)
    out = ActivityPostOut(
        id=post.id,
        kind=post.kind,
        author=ActivityAuthor(username=profile.username, display_name=profile.display_name,
                              avatar_path=profile.avatar_path),
        posted_at=None if hide_dates else post.created_at,
        high_fives=counts.get(post.id, 0),
        high_fived=post.id in mine_ids,
        mine=viewer is not None and post.user_id == viewer.id,
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
        milestone = MILESTONES.get(post.milestone)
        # Retired from the milestone list, or a kind that's never posted.
        if milestone is None or milestone.category in UNPOSTED_CATEGORIES:
            return None
        out.milestone = badge_out(milestone)
    else:
        out.rank = _rank(post.rank_level)
        if out.rank is None:
            return None
    return out


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

    query = visible_query(today).options(joinedload(HikeLog.trail))
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

    post_ids = [post.id for post, *_ in rows]
    counts = _counts(db, post_ids)
    mine_ids = set(db.scalars(
        select(ActivityReaction.post_id).where(ActivityReaction.user_id == viewer.id,
                                               ActivityReaction.post_id.in_(post_ids))
    )) if viewer and post_ids else set()
    items = [
        item for item in (_out(post, profile, settings, log, counts, mine_ids, viewer)
                          for post, profile, settings, log in rows)
        if item is not None
    ]
    return ActivityPage(
        items=items,
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
    """Owners can delete any of their posts, shown or not. The hike itself stays in the journal."""
    post = db.get(ActivityPost, post_id)
    if post is None or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
