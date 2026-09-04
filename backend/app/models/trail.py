import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, Numeric, Text
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
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    region = Column(Text, nullable=False)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    elevation_gain_m = Column(Integer)
    max_elevation_m = Column(Integer)
    terrain_difficulty = Column(Text, nullable=False)
    typical_duration_nights = Column(Integer)
    climate_zone = Column(Text)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
