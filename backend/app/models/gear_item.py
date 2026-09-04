import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, Integer, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

GEAR_ITEM_CATEGORIES = (
    "shelter",
    "sleep",
    "kitchen",
    "clothing",
    "navigation",
    "first_aid",
    "essentials",
    "safety",
    "other",
)


class GearItem(Base):
    __tablename__ = "gear_items"
    __table_args__ = (
        CheckConstraint(
            "category = ANY (ARRAY["
            + ",".join(f"'{c}'::text" for c in GEAR_ITEM_CATEGORIES)
            + "])",
            name="gear_items_category_check",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    is_shareable = Column(Boolean)
    weight_g = Column(Integer)
