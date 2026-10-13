"""A user's personal gear inventory.

Each row is one piece of equipment the user owns. It either references a
shared catalogue product (optionally a specific variant) or describes a custom
item the catalogue doesn't have. Catalogue data is never copied here — only
user-specific facts: quantity, their own weight override, notes, condition.

Ownership: user_id is the Supabase auth user. The API scopes every query to
the authenticated user, and Postgres row-level security enforces the same
rule for any direct Supabase access (see migration c3d4e5f6a7b8).
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.catalog import JsonType

CONDITIONS = ("new", "good", "worn", "needs_repair", "retired")
WEIGHT_UNITS = ("g", "kg", "oz", "lb")
MAX_QUANTITY = 99


class UserGearItem(Base):
    __tablename__ = "user_gear_items"
    __table_args__ = (
        CheckConstraint(
            "product_id is not null or (custom_name is not null and length(trim(custom_name)) > 0)",
            name="user_gear_items_product_or_custom_check",
        ),
        CheckConstraint(
            "variant_id is null or product_id is not null",
            name="user_gear_items_variant_requires_product_check",
        ),
        CheckConstraint(
            f"quantity between 1 and {MAX_QUANTITY}", name="user_gear_items_quantity_check"
        ),
        CheckConstraint(
            "weight_override_g is null or weight_override_g >= 0",
            name="user_gear_items_weight_override_check",
        ),
        CheckConstraint(
            "weight_override_unit is null or weight_override_unit in ('g','kg','oz','lb')",
            name="user_gear_items_weight_unit_check",
        ),
        CheckConstraint(
            "capacity_override_ml is null or capacity_override_ml > 0",
            name="user_gear_items_capacity_override_check",
        ),
        CheckConstraint(
            "condition is null or condition in ('new','good','worn','needs_repair','retired')",
            name="user_gear_items_condition_check",
        ),
        # Retried "add" requests carry the same client_request_id, so a
        # double-click or network retry can't create two rows.
        UniqueConstraint("user_id", "client_request_id", name="user_gear_items_client_request_key"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False, index=True)
    # RESTRICT: catalogue products are retired (status = discontinued), never
    # deleted, so a user's inventory never loses the product it points at.
    product_id = Column(Uuid, ForeignKey("catalog_products.id", ondelete="RESTRICT"))
    variant_id = Column(Uuid, ForeignKey("catalog_product_variants.id", ondelete="RESTRICT"))
    category_id = Column(
        Uuid, ForeignKey("catalog_categories.id", ondelete="RESTRICT"), nullable=False
    )
    custom_name = Column(Text)
    custom_brand = Column(Text)
    custom_model = Column(Text)
    quantity = Column(Integer, nullable=False, default=1)
    weight_override_g = Column(Numeric(12, 3))
    weight_override_unit = Column(Text)
    capacity_override_ml = Column(Numeric(12, 1))
    custom_specs = Column(JsonType, nullable=False, default=dict)
    notes = Column(Text)
    condition = Column(Text)
    image_path = Column(Text)
    client_request_id = Column(Uuid)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    product = relationship("CatalogProduct")
    variant = relationship("CatalogProductVariant")
    category = relationship("CatalogCategory")
