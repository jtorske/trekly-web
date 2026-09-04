import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class TrailSeasonalCondition(Base):
    __tablename__ = "trail_seasonal_conditions"
    __table_args__ = (
        CheckConstraint(
            "season in ('spring','summer','fall','winter')",
            name="trail_seasonal_conditions_season_check",
        ),
        CheckConstraint(
            "precip_likelihood in ('low','moderate','high')",
            name="precip_likelihood_check",
        ),
        UniqueConstraint("trail_id", "season", name="trail_seasonal_conditions_trail_season_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trail_id = Column(UUID(as_uuid=True), ForeignKey("trails.id"), nullable=False)
    season = Column(Text, nullable=False)
    avg_low_c = Column(Numeric(4, 1), nullable=False)
    avg_high_c = Column(Numeric(4, 1), nullable=False)
    precip_likelihood = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Whether this trail/season combo is prone to sustained high winds
    # (e.g. exposed coastal or alpine ridge terrain) — drives wind-specific
    # gear rules (extra-secure stakes, etc.) independent of precipitation.
    high_wind = Column(Boolean)
