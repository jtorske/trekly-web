"""People search (GET /api/search/hikers) and "Hikers you might know"
(GET /api/me/suggested-hikers). Signed-in users only; guests can still
search trails (POST /api/trails/search).

The rules are in app/hiker_search.py and the database functions it calls.
Nothing is cached, so a privacy change applies to the very next search.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import follows
from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.follows import FollowState
from app.hiker_search import (
    MAX_PAGE_SIZE, MAX_QUERY, MIN_QUERY, PAGE_SIZE, SUGGESTIONS, DatabaseHikerFinder, HikerCard, HikerFinder,
    SearchLimiter, cards, normalize_query,
)
from app.points import user_rank
from app.routers.public_profiles import PublicRank
from app.routers.signup_email import get_client_ip

router = APIRouter(prefix="/api", tags=["search"])

NO_STORE = {"Cache-Control": "no-store"}
_finder = DatabaseHikerFinder()
_limiter = SearchLimiter()


def get_hiker_finder() -> HikerFinder:
    """Overridden in tests (the real one needs Postgres)."""
    return _finder


def get_search_limiter() -> SearchLimiter:
    """Overridden in tests."""
    return _limiter


class HikerOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    is_private: bool
    # The viewer's follow state toward them.
    follow: FollowState
    # Only when they show it and the viewer may see their profile.
    rank: PublicRank | None = None
    home_province: str | None = None
    # Trails you've both hiked; only while their journal is visible to you.
    common_trails: int | None = None
    # Suggestions only: from your home province (which they show).
    same_province: bool = False


class HikerPage(BaseModel):
    items: list[HikerOut]
    next_offset: int | None


class Suggestions(BaseModel):
    items: list[HikerOut]


def _out(db: Session, viewer_id: UUID, found: list[HikerCard]) -> list[HikerOut]:
    states = follows.states(db, viewer_id, [card.profile.id for card in found])
    items = []
    for card in found:
        rank = None
        if card.show_rank:
            _, level = user_rank(db, card.profile.id)
            rank = PublicRank(level=level.level, title=level.title)
        items.append(HikerOut(
            username=card.profile.username,
            display_name=card.profile.display_name,
            avatar_path=card.profile.avatar_path,
            is_private=bool(card.is_private),
            follow=states.get(card.profile.id) or "none",
            rank=rank,
            home_province=card.profile.home_province if card.show_province else None,
            common_trails=card.common_trails,
            same_province=card.same_province is True,
        ))
    return items


@router.get("/search/hikers", response_model=HikerPage)
def search_hikers(
    response: Response,
    q: str = Query(..., max_length=MAX_QUERY),
    offset: int = Query(0, ge=0, le=1000),
    limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    finder: HikerFinder = Depends(get_hiker_finder),
    limiter: SearchLimiter = Depends(get_search_limiter),
    client_ip: str = Depends(get_client_ip),
):
    term = normalize_query(q)
    if len(term) < MIN_QUERY:
        raise HTTPException(status_code=422, detail=f"Type at least {MIN_QUERY} characters to search.")
    wait = limiter.check(user.id, client_ip)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="That's a lot of searches. Wait a moment, then try again.",
            headers={"Retry-After": str(int(wait + 0.999))},
        )
    response.headers.update(NO_STORE)
    hits = finder.search(db, user.id, term, limit + 1, offset)
    more = len(hits) > limit
    hits = hits[:limit]
    found = cards(db, user.id, [(hit.user_id, hit.opened, hit.common_trails, False) for hit in hits])
    return HikerPage(items=_out(db, user.id, found), next_offset=offset + limit if more else None)


@router.get("/me/suggested-hikers", response_model=Suggestions)
def suggested_hikers(
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    finder: HikerFinder = Depends(get_hiker_finder),
):
    response.headers.update(NO_STORE)
    hits = finder.suggest(db, user.id, SUGGESTIONS)
    # Suggestions are all community members: public, journal shown.
    found = cards(db, user.id, [(hit.user_id, True, hit.common_trails, True) for hit in hits])
    return Suggestions(items=_out(db, user.id, found))
