"""Named gear setups: a user's own grouping of gear they use together.

A setup ("Ultralight 2-Night Kit") references items from the user's own
inventory — it never copies them, so editing an item updates every setup it
appears in, and removing an item from the inventory removes it from setups.
Setups are private to their owner, like the rest of a user's data.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

MAX_SETUPS_PER_USER = 50
MAX_ITEMS_PER_SETUP = 60


class GearSetup(Base):
    __tablename__ = "gear_setups"
    __table_args__ = (
        CheckConstraint("length(trim(name)) between 1 and 80", name="gear_setups_name_length_check"),
        CheckConstraint(
            "description is null or length(description) <= 500",
            name="gear_setups_description_length_check",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entries = relationship(
        "GearSetupItem",
        back_populates="setup",
        cascade="all, delete-orphan",
        order_by="GearSetupItem.position",
    )


class GearSetupItem(Base):
    __tablename__ = "gear_setup_items"

    setup_id = Column(Uuid, ForeignKey("gear_setups.id", ondelete="CASCADE"), primary_key=True)
    gear_item_id = Column(
        Uuid, ForeignKey("user_gear_items.id", ondelete="CASCADE"), primary_key=True
    )
    position = Column(Integer, nullable=False, default=0)

    setup = relationship("GearSetup", back_populates="entries")
    gear_item = relationship("UserGearItem")
