"""Follow, unfollow, follow requests, and followers / following lists.

The rules are in app/follows.py. Every response is built from the models
below: a person is only ever their username, display name and photo, plus
the viewer's own follow state toward them. Nothing is cached.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app import follows
from app.account_labels import AccountLabelName, labels_for, may_interact
from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.follows import FollowState
from app.models.account import Profile
from app.models.privacy import ProfileSettings
from app.models.social import Follow
from app.routers.activity import optional_user
from app.routers.public_profiles import find_listed

router = APIRouter(prefix="/api", tags=["follows"])

PAGE_SIZE = 30
NO_STORE = {"Cache-Control": "no-store"}


class PersonOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    # "official" / "demo" badge (app/account_labels.py); None for everyone else.
    label: AccountLabelName | None = None
    is_private: bool
    # The viewer's follow state toward them; None for a guest, or for the viewer themselves.
    follow: FollowState | None = None


class PeoplePage(BaseModel):
    items: list[PersonOut]
    next_cursor: str | None


class FollowOut(BaseModel):
    follow: FollowState
    followers_count: int


def _require_username(db: Session, user: CurrentUser) -> Profile:
    profile = db.get(Profile, user.id)
    if profile is None or not profile.username:
        raise HTTPException(status_code=409, detail="Choose a username before you follow anyone.")
    return profile


def _by_username(db: Session, username: str) -> Profile:
    """Any profile by username (listed or not), for cleaning up your own lists."""
    profile = db.scalar(select(Profile).where(Profile.username == username.strip().lower()))
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_where(q: str | None):
    """Username starts with q, or the display name contains it (case-insensitive)."""
    if not q or not q.strip():
        return None
    term = _escape_like(q.strip().lstrip("@").lower())
    if not term:
        return None
    return or_(
        Profile.username.like(f"{term}%", escape="\\"),
        func.lower(Profile.display_name).like(f"%{term}%", escape="\\"),
    )


def _cursor(when: datetime, user_id: UUID) -> str:
    return f"{when.isoformat()}~{user_id}"


def _parse_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        when, _, user_id = cursor.partition("~")
        return datetime.fromisoformat(when), UUID(user_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="That page link isn't valid.") from error


def people_out(db: Session, viewer_id: UUID | None, profiles: list[Profile]) -> list[PersonOut]:
    ids = [p.id for p in profiles]
    private = set(db.scalars(
        select(ProfileSettings.user_id).where(ProfileSettings.user_id.in_(ids), ProfileSettings.is_private)
    )) if ids else set()
    known = set(db.scalars(select(ProfileSettings.user_id).where(ProfileSettings.user_id.in_(ids)))) if ids else set()
    viewer_states = follows.states(db, viewer_id, ids)
    labels = labels_for(db, ids)
    return [
        PersonOut(
            username=p.username,
            display_name=p.display_name,
            avatar_path=p.avatar_path,
            label=labels.get(p.id),
            # Missing settings count as private, as everywhere else.
            is_private=p.id in private or p.id not in known,
            follow=None if viewer_id is None or p.id == viewer_id else viewer_states.get(p.id, "none"),
        )
        for p in profiles
    ]


def _page(db: Session, viewer_id: UUID | None, *, owner_col, other_col, owner_id: UUID, status_value: str,
          q: str | None, cursor: str | None, limit: int, when_col=None) -> PeoplePage:
    when_col = when_col if when_col is not None else Follow.accepted_at
    query = (
        select(Profile, when_col)
        .join(Follow, other_col == Profile.id)
        .where(owner_col == owner_id, Follow.status == status_value, follows.listed_where(other_col))
    )
    matching = search_where(q)
    if matching is not None:
        query = query.where(matching)
    if cursor:
        when, user_id = _parse_cursor(cursor)
        query = query.where(or_(when_col < when, and_(when_col == when, Profile.id < user_id)))
    rows = db.execute(query.order_by(when_col.desc(), Profile.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return PeoplePage(
        items=people_out(db, viewer_id, [profile for profile, _ in rows]),
        next_cursor=_cursor(rows[-1][1], rows[-1][0].id) if more else None,
    )


# ------------------------------------------------------------ follow / unfollow


@router.put("/profiles/{username}/follow", response_model=FollowOut)
def follow_profile(username: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Follow a public profile, or ask to follow a private one. Idempotent."""
    _require_username(db, user)
    owner, seen = find_listed(db, username)
    if owner.id == user.id:
        raise HTTPException(status_code=422, detail="You can't follow yourself.")
    if not may_interact(db, user.id, owner.id):
        raise HTTPException(status_code=403, detail="Demo accounts only interact with other demo accounts.")
    new_state, _ = follows.follow(db, user.id, owner, seen)
    db.commit()
    return FollowOut(follow=new_state, followers_count=follows.follower_count(db, owner.id))


@router.delete("/profiles/{username}/follow", response_model=FollowOut)
def unfollow_profile(username: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Unfollow, or cancel a request. Works on any account you follow, listed or not."""
    owner = _by_username(db, username)
    follows.unfollow(db, user.id, owner.id)
    db.commit()
    return FollowOut(follow="none", followers_count=follows.follower_count(db, owner.id))


# ------------------------------------------------------------ the lists


def _list(db: Session, viewer: CurrentUser | None, username: str, which: Literal["followers", "following"],
          q: str | None, cursor: str | None, limit: int) -> PeoplePage:
    viewer_id = viewer.id if viewer else None
    owner, seen = find_listed(db, username, viewer_id)
    if not follows.lists_open(viewer_id, owner, seen):
        raise HTTPException(status_code=403, detail="This list is private.")
    if which == "followers":
        return _page(db, viewer_id, owner_col=Follow.followee_id, other_col=Follow.follower_id, owner_id=owner.id,
                     status_value="accepted", q=q, cursor=cursor, limit=limit)
    return _page(db, viewer_id, owner_col=Follow.follower_id, other_col=Follow.followee_id, owner_id=owner.id,
                 status_value="accepted", q=q, cursor=cursor, limit=limit)


@router.get("/profiles/{username}/followers", response_model=PeoplePage)
def list_followers(
    username: str,
    response: Response,
    q: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    return _list(db, viewer, username, "followers", q, cursor, limit)


@router.get("/profiles/{username}/following", response_model=PeoplePage)
def list_following(
    username: str,
    response: Response,
    q: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    viewer: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    return _list(db, viewer, username, "following", q, cursor, limit)


# ------------------------------------------------------------ the owner's side


@router.get("/me/follow-requests", response_model=PeoplePage)
def list_requests(
    response: Response,
    q: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    return _page(db, user.id, owner_col=Follow.followee_id, other_col=Follow.follower_id, owner_id=user.id,
                 status_value="pending", q=q, cursor=cursor, limit=limit, when_col=Follow.created_at)


@router.post("/me/follow-requests/{username}", response_model=PersonOut)
def approve_request(username: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    follower = _by_username(db, username)
    if not follows.approve(db, user.id, follower.id):
        raise HTTPException(status_code=404, detail="That request isn't there any more.")
    db.commit()
    return people_out(db, user.id, [follower])[0]


@router.delete("/me/follow-requests/{username}", status_code=status.HTTP_204_NO_CONTENT)
def decline_request(username: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Decline quietly: they see "Follow" again, nothing more."""
    follower = _by_username(db, username)
    if follows.decline(db, user.id, follower.id):
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/followers/{username}", status_code=status.HTTP_204_NO_CONTENT)
def remove_follower(username: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove someone from your followers. They aren't told; they can follow again
    (or, for a private profile, ask again)."""
    follower = _by_username(db, username)
    follows.unfollow(db, follower.id, user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
