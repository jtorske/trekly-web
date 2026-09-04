import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class GearRule(Base):
    __tablename__ = "gear_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gear_item_id = Column(
        UUID(as_uuid=True), ForeignKey("gear_items.id", ondelete="CASCADE"), nullable=False
    )
    condition_terrain = Column(Text)
    condition_season = Column(Text)
    condition_min_nights = Column(Integer)
    condition_min_temp_c = Column(Numeric(4, 1))
    condition_max_temp_c = Column(Numeric(4, 1))
    quantity_per_person = Column(Numeric(4, 2))
    quantity_formula = Column(Text)
    # Region/climate gating so items like bear spray don't get recommended
    # everywhere: matches trails.climate_zone when set.
    condition_climate_zone = Column(Text)
    # Wind/rain-specific gating for exposed terrain (coastal, alpine ridges).
    condition_requires_high_precip = Column(Boolean)
    condition_requires_high_wind = Column(Boolean)
