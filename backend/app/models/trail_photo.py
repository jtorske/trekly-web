"""The credited hero photo for a trail, and the review decision behind it.

One current photo per trail (see migration dfc16ffa2de3). Only the backend
writes these rows, after checking the caller is a photo admin; the processed
files live in the public trail-photos Storage bucket.
"""

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base
from app.models.catalog import JsonType

PHOTO_SOURCES = ("commons", "openverse", "pixabay", "pexels", "owner")
# What an approved photo shows (from its candidate's confidence); null for the owner's own.
PHOTO_SCOPES = ("trail", "nearby", "park")
# Candidate confidence -> photo scope. Older searches stored park-level matches as low / off_topic.
SCOPE_BY_CONFIDENCE = {"high": "trail", "medium": "nearby", "park": "park", "low": "park", "off_topic": "park"}
REVIEW_DECISIONS = ("approved", "rejected", "uploaded")


class TrailPhoto(Base):
    __tablename__ = "trail_photos"
    __table_args__ = (
        CheckConstraint("source in ('commons','openverse','pixabay','pexels','owner')", name="trail_photos_source_check"),
        CheckConstraint("scope is null or scope in ('trail','nearby','park')", name="trail_photos_scope_check"),
        CheckConstraint(
            "source = 'owner' or (license is not null and source_url is not null)",
            name="trail_photos_credit_check",
        ),
    )

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    # 'commons' / 'openverse' / 'pixabay' / 'pexels' (a reviewed candidate) or 'owner' (uploaded by the site owner).
    source = Column(Text, nullable=False)
    # 'trail' / 'nearby' / 'park': a 'park' photo's credit names the park (migration b9e4d2a7c1f6).
    scope = Column(Text)
    # Where the photo was first published: "Wikimedia Commons", "Flickr", ...
    origin = Column(Text)
    candidate_id = Column(Text)
    photographer = Column(Text, nullable=False)
    # Null for the owner's own photos, which are credited by name only.
    license = Column(Text)
    license_url = Column(Text)
    source_url = Column(Text)
    # `{trail_id}/{uuid}-hero.webp` / `-thumb.webp` in the trail-photos bucket.
    hero_path = Column(Text, nullable=False)
    thumb_path = Column(Text, nullable=False)
    hero_width = Column(Integer, nullable=False)
    hero_height = Column(Integer, nullable=False)
    approved_by = Column(Uuid, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrailPhotoReview(Base):
    __tablename__ = "trail_photo_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision in ('approved','rejected','uploaded')", name="trail_photo_reviews_decision_check"
        ),
    )

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    decision = Column(Text, nullable=False)
    candidate_id = Column(Text)
    reviewed_by = Column(Uuid, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrailPhotoCandidates(Base):
    """A trail's search results for the review page (migration aa84e0d9e26b),
    loaded by scripts/load_photo_candidates.py."""

    __tablename__ = "trail_photo_candidates"

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    destination = Column(Text)
    best_confidence = Column(Text)
    # Preselected candidate id; null starts the trail on the topo fallback.
    default_choice = Column(Text)
    low_res = Column(Boolean, nullable=False, default=False)
    # The top candidates, best first, as written by scripts/find_trail_photos.py.
    candidates = Column(JsonType, nullable=False)
    searched_on = Column(Date)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrailRouteMap(Base):
    """A generated picture of the trail's stored route on the topo style
    (scripts/route_maps.py), shown when the trail has no photo."""

    __tablename__ = "trail_route_maps"

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    # `{trail_id}/route-map-{hash}-hero.webp` / `-thumb.webp` in the trail-photos bucket.
    hero_path = Column(Text, nullable=False)
    thumb_path = Column(Text, nullable=False)
    hero_width = Column(Integer, nullable=False)
    hero_height = Column(Integer, nullable=False)
    # The route and drawing settings it was made from; unchanged means no redraw.
    route_hash = Column(Text, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
