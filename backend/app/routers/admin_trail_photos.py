"""Trail photo review: pick a candidate, reject them all, or upload your own.

Every route requires a signed-in user listed in PHOTO_ADMIN_USER_IDS; the
check runs here on the backend for every request (the frontend only hides
the page). Candidates come from the search script's output file
(PHOTO_CANDIDATES_PATH) and are looked up by id on the server, so a client
can't supply its own image URL, photographer or license.

Publishing resizes to WebP (app/trail_photos.py), uploads under new names,
then swaps the trail's photo row; the old files are deleted only after the
new row is committed, so a trail is never left pointing at missing files.
"""

import json
import logging
import os
from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.config import PHOTO_CANDIDATES_PATH, TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT, photo_admin_user_ids
from app.database import get_db
from app.models.account import Profile
from app.models.trail import Trail
from app.models.trail_photo import TrailPhoto, TrailPhotoReview
from app.schemas.trail import TrailListItemOut, TrailPhotoOut
from app.trail_photos import (
    MAX_SOURCE_BYTES,
    PhotoError,
    PhotoStorage,
    ProcessedPhoto,
    StorageError,
    fetch_image,
    new_paths,
    process_image,
    storage_from_env,
)

router = APIRouter(prefix="/api/admin/trail-photos", tags=["trail photo admin"])
log = logging.getLogger(__name__)

UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ---------------------------------------------------------------- dependencies

def require_photo_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if str(user.id).lower() not in photo_admin_user_ids():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account can't manage trail photos.")
    return user


def get_photo_storage(_admin: CurrentUser = Depends(require_photo_admin)) -> PhotoStorage:
    storage = storage_from_env()
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo storage isn't configured on the server (SUPABASE_SERVICE_ROLE_KEY).",
        )
    return storage


def get_image_fetcher():
    return fetch_image


# ---------------------------------------------------------------- candidates

@lru_cache(maxsize=4)
def _load_candidates(path: str, mtime: float) -> dict[tuple[str, str | None], dict]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return {(t["name"], t.get("province_code")): t for t in data.get("trails", [])}


def candidates_by_trail() -> dict[tuple[str, str | None], dict]:
    """The search output keyed by (name, province_code), the trails' unique key."""
    try:
        mtime = os.path.getmtime(PHOTO_CANDIDATES_PATH)
    except OSError:
        return {}
    return _load_candidates(PHOTO_CANDIDATES_PATH, mtime)


class CandidateOut(BaseModel):
    id: str
    source: str
    origin: str | None = None
    confidence: str
    title: str
    preview_url: str
    image_url: str
    width: int
    height: int
    photographer: str
    license: str
    license_url: str | None = None
    source_url: str
    distance_m: int | None = None
    # Below the 1600px search minimum: found by the 1024px fallback.
    low_res: bool = False


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: str
    candidate_id: str | None = None


class ReviewTrailOut(BaseModel):
    trail: TrailListItemOut
    destination: str | None = None
    best_confidence: str | None = None
    # What the page selects first: a high/medium candidate, else none (topo).
    default_choice: str | None = None
    candidates: list[CandidateOut] = []
    review: ReviewOut | None = None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=120)


def _trail_or_404(db: Session, trail_id: UUID) -> Trail:
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    return trail


def _candidate(trail: Trail, candidate_id: str) -> dict:
    entry = candidates_by_trail().get((trail.name, trail.province_code)) or {}
    for candidate in entry.get("candidates", []):
        if candidate["id"] == candidate_id:
            return candidate
    raise HTTPException(status_code=404, detail="No candidate with that id for this trail.")


# ---------------------------------------------------------------- publishing

def _record_review(db: Session, trail_id: UUID, decision: str, candidate_id: str | None, admin: CurrentUser):
    review = db.get(TrailPhotoReview, trail_id) or TrailPhotoReview(trail_id=trail_id)
    review.decision, review.candidate_id, review.reviewed_by = decision, candidate_id, admin.id
    db.add(review)


def _delete_quietly(storage: PhotoStorage, paths: list[str]) -> None:
    try:
        storage.delete(paths)
    except StorageError as error:
        # The message carries only the HTTP status (see PhotoStorage).
        log.warning("Couldn't delete replaced trail photo files %s: %s", paths, error)


def _publish(db: Session, storage: PhotoStorage, trail: Trail, photo: ProcessedPhoto, credit: dict,
             decision: str, admin: CurrentUser) -> TrailPhoto:
    hero_path, thumb_path = new_paths(trail.id)
    try:
        storage.upload(hero_path, photo.hero)
        storage.upload(thumb_path, photo.thumb)
    except StorageError as error:
        _delete_quietly(storage, [hero_path])
        raise HTTPException(status_code=502, detail="Couldn't upload the photo to storage. Try again.") from error

    row = db.get(TrailPhoto, trail.id)
    old_paths = [row.hero_path, row.thumb_path] if row else []
    row = row or TrailPhoto(trail_id=trail.id)
    for key, value in credit.items():
        setattr(row, key, value)
    row.hero_path, row.thumb_path = hero_path, thumb_path
    row.hero_width, row.hero_height = photo.hero_width, photo.hero_height
    row.approved_by = admin.id
    db.add(row)
    _record_review(db, trail.id, decision, credit.get("candidate_id"), admin)
    try:
        db.commit()
    except Exception:
        db.rollback()
        _delete_quietly(storage, [hero_path, thumb_path])
        raise
    _delete_quietly(storage, old_paths)
    db.refresh(row)
    return row


def _remove_photo(db: Session, storage: PhotoStorage, trail_id: UUID) -> None:
    row = db.get(TrailPhoto, trail_id)
    if row is None:
        return
    paths = [row.hero_path, row.thumb_path]
    db.delete(row)
    db.flush()
    # Deleted once the caller commits; a failed delete only leaves unreferenced files.
    db.info.setdefault("delete_after_commit", []).extend(paths)


def _commit_removals(db: Session, storage: PhotoStorage) -> None:
    db.commit()
    _delete_quietly(storage, db.info.pop("delete_after_commit", []))


# ---------------------------------------------------------------- routes

@router.get("/me")
def whoami(_admin: CurrentUser = Depends(require_photo_admin)):
    """200 for photo admins (the page uses it to decide whether to render)."""
    return {"admin": True}


@router.get("", response_model=list[ReviewTrailOut])
def review_list(_admin: CurrentUser = Depends(require_photo_admin), db: Session = Depends(get_db)):
    trails = (
        db.query(Trail)
        .filter(
            Trail.retired_at.is_(None),
            Trail.country_code.in_(TRAIL_CATALOG_COUNTRIES),
            Trail.popularity_rank.is_not(None),
            Trail.popularity_rank <= TRAIL_CATALOG_LIMIT,
        )
        .order_by(Trail.popularity_rank, Trail.name)
        .all()
    )
    reviews = {r.trail_id: r for r in db.query(TrailPhotoReview).all()}
    found = candidates_by_trail()
    out = []
    for trail in trails:
        entry = found.get((trail.name, trail.province_code)) or {}
        out.append(ReviewTrailOut(
            trail=TrailListItemOut.model_validate(trail),
            destination=entry.get("destination"),
            best_confidence=entry.get("best_confidence"),
            default_choice=entry.get("default_choice"),
            candidates=[CandidateOut.model_validate(c) for c in entry.get("candidates", [])],
            review=ReviewOut.model_validate(reviews[trail.id]) if trail.id in reviews else None,
        ))
    return out


@router.post("/{trail_id}/approve", response_model=TrailPhotoOut)
def approve(
    trail_id: UUID,
    body: ApproveIn,
    admin: CurrentUser = Depends(require_photo_admin),
    storage: PhotoStorage = Depends(get_photo_storage),
    fetch=Depends(get_image_fetcher),
    db: Session = Depends(get_db),
):
    trail = _trail_or_404(db, trail_id)
    candidate = _candidate(trail, body.candidate_id)
    try:
        photo = process_image(fetch(candidate["image_url"]))
    except PhotoError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    credit = {
        "source": candidate["source"],
        "origin": candidate.get("origin"),
        "candidate_id": candidate["id"],
        "photographer": candidate["photographer"][:200],
        "license": candidate["license"][:80],
        "license_url": candidate.get("license_url"),
        "source_url": candidate["source_url"],
    }
    return _publish(db, storage, trail, photo, credit, "approved", admin)


@router.post("/{trail_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject(
    trail_id: UUID,
    admin: CurrentUser = Depends(require_photo_admin),
    storage: PhotoStorage = Depends(get_photo_storage),
    db: Session = Depends(get_db),
):
    """No candidate is good enough: the trail shows the topo fallback. A photo
    you uploaded yourself is kept; remove it with DELETE /photo."""
    trail = _trail_or_404(db, trail_id)
    current = db.get(TrailPhoto, trail.id)
    if current is not None and current.source != "owner":
        _remove_photo(db, storage, trail.id)
    _record_review(db, trail.id, "rejected", None, admin)
    _commit_removals(db, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{trail_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
def remove_photo(
    trail_id: UUID,
    _admin: CurrentUser = Depends(require_photo_admin),
    storage: PhotoStorage = Depends(get_photo_storage),
    db: Session = Depends(get_db),
):
    _trail_or_404(db, trail_id)
    _remove_photo(db, storage, trail_id)
    db.query(TrailPhotoReview).filter(TrailPhotoReview.trail_id == trail_id).delete()
    _commit_removals(db, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{trail_id}/upload", response_model=TrailPhotoOut)
async def upload_own(
    trail_id: UUID,
    request: Request,
    admin: CurrentUser = Depends(require_photo_admin),
    storage: PhotoStorage = Depends(get_photo_storage),
    db: Session = Depends(get_db),
):
    """Your own photo for any trail, as the raw request body (JPEG, PNG or
    WebP), credited to your profile's display name."""
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="Use a JPEG, PNG or WebP image.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="That image is over 40 MB.")

    def work():
        trail = _trail_or_404(db, trail_id)
        profile = db.get(Profile, admin.id)
        name = (profile.display_name or profile.username) if profile else None
        if not name:
            raise HTTPException(status_code=400, detail="Add a display name to your profile first; it's used for the photo credit.")
        try:
            photo = process_image(bytes(data))
        except PhotoError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        credit = {"source": "owner", "origin": None, "candidate_id": None, "photographer": name[:200],
                  "license": None, "license_url": None, "source_url": None}
        return _publish(db, storage, trail, photo, credit, "uploaded", admin)

    return await run_in_threadpool(work)
