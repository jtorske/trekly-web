"""The credited hero photo for a trail, and the review decision behind it.

One current photo per trail (see migration dfc16ffa2de3). Only the backend
writes these rows, after checking the caller is a photo admin; the processed
files live in the public trail-photos Storage bucket.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base

PHOTO_SOURCES = ("commons", "openverse", "owner")
REVIEW_DECISIONS = ("approved", "rejected", "uploaded")


class TrailPhoto(Base):
    __tablename__ = "trail_photos"
    __table_args__ = (
        CheckConstraint("source in ('commons','openverse','owner')", name="trail_photos_source_check"),
        CheckConstraint(
            "source = 'owner' or (license is not null and source_url is not null)",
            name="trail_photos_credit_check",
        ),
    )

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    # 'commons' / 'openverse' (a reviewed candidate) or 'owner' (uploaded by the site owner).
    source = Column(Text, nullable=False)
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
