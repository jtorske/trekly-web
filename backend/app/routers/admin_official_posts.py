"""Posting as the official Trekly account (/admin/posts).

Admins write short announcements that appear in the Activity feed from
@trekly, with an optional linked trail and photo. The account itself is
made by scripts/official_account.py; until it exists, posting is refused.

A photo is uploaded first (PUT /photo, the raw image as the body, like
/admin/photos), re-encoded with no metadata and stored under posts/ in the
public trail-photos bucket; the post then names it. Posting and deleting are
audited. A photo whose post is deleted goes with it.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.account_labels import official_id
from app.admin_access import audit, require_admin
from app.auth import CurrentUser
from app.database import get_db
from app.models.account import Profile
from app.models.activity import MAX_ANNOUNCEMENT, ActivityPost
from app.models.trail import Trail
from app.routers.admin_trail_photos import UPLOAD_TYPES, get_photo_storage
from app.routers.trails import live_trails
from app.schemas.trail import TrailListItemOut
from app.trail_photos import (
    MAX_SOURCE_BYTES, POST_PHOTO_PREFIX, PhotoError, PhotoStorage, StorageError, new_post_photo_path,
    process_post_photo, public_photo_url,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/official-posts", tags=["admin"], dependencies=[Depends(require_admin)])


class OfficialAccountOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None


class OfficialPostOut(BaseModel):
    id: UUID
    body: str
    trail: TrailListItemOut | None
    photo_url: str | None
    created_at: datetime
    hidden: bool


class OfficialPostsOut(BaseModel):
    # None until scripts/official_account.py has made the account.
    account: OfficialAccountOut | None
    posts: list[OfficialPostOut]


class OfficialPostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_ANNOUNCEMENT)
    trail_id: UUID | None = None
    # From PUT /photo.
    photo_path: str | None = Field(default=None, max_length=120)

    @field_validator("body", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("photo_path")
    @classmethod
    def _ours(cls, value):
        if value is not None and (not value.startswith(POST_PHOTO_PREFIX) or "/" in value[len(POST_PHOTO_PREFIX):]
                                  or not value.endswith(".webp")):
            raise ValueError("That photo wasn't uploaded here.")
        return value


class PhotoOut(BaseModel):
    photo_path: str
    photo_url: str
    width: int
    height: int


def _official(db: Session) -> Profile:
    user_id = official_id(db)
    profile = db.get(Profile, user_id) if user_id else None
    if profile is None or not profile.username:
        raise HTTPException(status_code=409, detail="The Trekly account hasn't been set up yet "
                                                    "(scripts/official_account.py).")
    return profile


def _out(post: ActivityPost) -> OfficialPostOut:
    return OfficialPostOut(
        id=post.id,
        body=post.body or "",
        trail=TrailListItemOut.model_validate(post.trail) if post.trail else None,
        photo_url=public_photo_url(post.photo_path) if post.photo_path else None,
        created_at=post.created_at,
        hidden=post.hidden_at is not None,
    )


@router.get("", response_model=OfficialPostsOut)
def list_posts(response: Response, db: Session = Depends(get_db), limit: int = Query(default=50, ge=1, le=200)):
    response.headers["Cache-Control"] = "no-store"
    user_id = official_id(db)
    profile = db.get(Profile, user_id) if user_id else None
    if profile is None:
        return OfficialPostsOut(account=None, posts=[])
    posts = db.scalars(
        select(ActivityPost).options(joinedload(ActivityPost.trail))
        .where(ActivityPost.user_id == profile.id, ActivityPost.kind == "announcement")
        .order_by(ActivityPost.created_at.desc()).limit(limit)
    ).all()
    return OfficialPostsOut(
        account=OfficialAccountOut(username=profile.username or "", display_name=profile.display_name,
                                   avatar_path=profile.avatar_path),
        posts=[_out(post) for post in posts],
    )


@router.put("/photo", response_model=PhotoOut)
async def upload_photo(request: Request, storage: PhotoStorage = Depends(get_photo_storage)):
    """The post's photo as the raw request body (JPEG, PNG or WebP)."""
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="Use a JPEG, PNG or WebP image.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="That image is over 40 MB.")

    def work() -> PhotoOut:
        try:
            webp, width, height = process_post_photo(bytes(data))
        except PhotoError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        path = new_post_photo_path()
        try:
            storage.upload(path, webp)
        except StorageError as error:
            raise HTTPException(status_code=502, detail="Couldn't upload the photo to storage. Try again.") from error
        return PhotoOut(photo_path=path, photo_url=public_photo_url(path), width=width, height=height)

    return await run_in_threadpool(work)


@router.delete("/photo", status_code=status.HTTP_204_NO_CONTENT)
def discard_photo(
    path: str = Query(max_length=120),
    storage: PhotoStorage = Depends(get_photo_storage),
    db: Session = Depends(get_db),
):
    """A photo picked for a post that wasn't sent. Refused once a post uses it."""
    OfficialPostIn(body="x", photo_path=path)  # same shape check
    if db.scalar(select(ActivityPost.id).where(ActivityPost.photo_path == path)) is not None:
        raise HTTPException(status_code=409, detail="A post uses that photo; delete the post instead.")
    _delete_quietly(storage, path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=OfficialPostOut, status_code=status.HTTP_201_CREATED)
def create_post(payload: OfficialPostIn, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    account = _official(db)
    if payload.trail_id is not None and db.scalar(
        select(Trail.id).where(Trail.id == payload.trail_id, *live_trails())
    ) is None:
        raise HTTPException(status_code=422, detail="That trail isn't in the catalogue.")
    post = ActivityPost(
        user_id=account.id, kind="announcement", body=payload.body, trail_id=payload.trail_id,
        photo_path=payload.photo_path, created_at=datetime.now(timezone.utc),
    )
    db.add(post)
    db.flush()
    audit(db, admin, "official_post", post_id=str(post.id), body=payload.body[:120])
    db.commit()
    db.refresh(post)
    return _out(post)


def _delete_quietly(storage: PhotoStorage, path: str | None) -> None:
    if not path:
        return
    try:
        storage.delete([path])
    except StorageError:
        log.warning("Couldn't delete a post photo from storage")


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: UUID,
    admin: CurrentUser = Depends(require_admin),
    storage: PhotoStorage = Depends(get_photo_storage),
    db: Session = Depends(get_db),
):
    post = db.get(ActivityPost, post_id)
    if post is None or post.kind != "announcement" or post.user_id != official_id(db):
        raise HTTPException(status_code=404, detail="Post not found")
    photo = post.photo_path
    audit(db, admin, "delete_official_post", post_id=str(post.id), body=(post.body or "")[:120])
    db.delete(post)
    db.commit()
    _delete_quietly(storage, photo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
