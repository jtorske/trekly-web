import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base

TERRAIN_DIFFICULTIES = ("easy", "moderate", "difficult", "extreme")


class Trail(Base):
    __tablename__ = "trails"
    __table_args__ = (
        CheckConstraint(
            "terrain_difficulty in ('easy','moderate','difficult','extreme')",
            name="trails_terrain_difficulty_check",
        ),
        CheckConstraint("length(country_code) = 2", name="trails_country_code_check"),
        CheckConstraint("popularity_rank >= 1", name="trails_popularity_rank_check"),
        UniqueConstraint("name", "province_code", name="trails_name_province_key"),
        Index("trails_country_rank_idx", "country_code", "popularity_rank"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    region = Column(Text, nullable=False)
    # ISO 3166-1 alpha-2 country and the ISO 3166-2 subdivision suffix
    # (e.g. "CA" / "AB").
    country_code = Column(Text, nullable=False)
    province_code = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    elevation_gain_m = Column(Integer)
    max_elevation_m = Column(Integer)
    terrain_difficulty = Column(Text, nullable=False)
    typical_duration_nights = Column(Integer)
    climate_zone = Column(Text)
    description = Column(Text)
    # Catalogue ordering. popularity_source says where the score came from
    # ('editorial' today; a blend with saved_trails counts later), so ranks can
    # be recomputed without another schema change. Null for retired trails.
    popularity_rank = Column(Integer)
    popularity_score = Column(Numeric(6, 4))
    popularity_source = Column(Text)
    popularity_updated_at = Column(DateTime(timezone=True))
    # Set when a trail drops out of the catalogue. Retired trails are never
    # deleted, so bookmarks, seasonal conditions and campsites keep working.
    retired_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
