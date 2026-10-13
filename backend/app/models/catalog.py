"""Shared gear catalogue: brands, products, variants, images and provenance.

Catalogue rows are shared reference data — every user's inventory can point
at the same product. They are written only by the ingestion pipeline
(app/catalog/pipeline.py), never by end users. Personal inventory lives in
user_gear_items (app/models/user_gear.py).

Canonical units: mass in grams, volume in millilitres, lengths in centimetres,
temperatures in °C. Values that aren't reliably known stay NULL.
"""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# JSONB on Postgres, plain JSON elsewhere (the SQLite test database).
JsonType = JSON().with_variant(JSONB(), "postgresql")

PRODUCT_STATUSES = ("active", "discontinued")
WEIGHT_BASES = ("minimum", "trail", "packaged", "average", "claimed")
SOURCE_KINDS = ("manufacturer", "licensed_feed", "manual")
RUN_STATUSES = ("running", "succeeded", "partial", "failed")


def _timestamps():
    return (
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )


class CatalogCategory(Base):
    """Two-level taxonomy: top-level flat-lay categories and their subcategories."""

    __tablename__ = "catalog_categories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    slug = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    parent_id = Column(Uuid, ForeignKey("catalog_categories.id", ondelete="RESTRICT"))
    sort_order = Column(Integer, nullable=False, default=0)
    icon_key = Column(Text, nullable=False)
    description = Column(Text)

    parent = relationship("CatalogCategory", remote_side=[id], back_populates="children")
    children = relationship("CatalogCategory", back_populates="parent")


class CatalogBrand(Base):
    __tablename__ = "catalog_brands"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    slug = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    website_url = Column(Text)
    created_at, updated_at = _timestamps()

    aliases = relationship("CatalogBrandAlias", back_populates="brand", cascade="all, delete-orphan")


class CatalogBrandAlias(Base):
    __tablename__ = "catalog_brand_aliases"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    brand_id = Column(Uuid, ForeignKey("catalog_brands.id", ondelete="CASCADE"), nullable=False)
    alias = Column(Text, nullable=False)
    # Normalized (lowercase, accent-free, punctuation-free) — unique across all
    # brands so "Arcteryx" can never resolve to two different brands.
    alias_normalized = Column(Text, nullable=False, unique=True)

    brand = relationship("CatalogBrand", back_populates="aliases")


class CatalogProduct(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="catalog_products_brand_slug_key"),
        CheckConstraint(
            "status in ('active','discontinued')", name="catalog_products_status_check"
        ),
        CheckConstraint(
            "weight_basis is null or weight_basis in "
            "('minimum','trail','packaged','average','claimed')",
            name="catalog_products_weight_basis_check",
        ),
        CheckConstraint("weight_g is null or weight_g > 0", name="catalog_products_weight_check"),
        CheckConstraint(
            "capacity_ml is null or capacity_ml > 0", name="catalog_products_capacity_check"
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    brand_id = Column(Uuid, ForeignKey("catalog_brands.id", ondelete="RESTRICT"), nullable=False)
    category_id = Column(
        Uuid, ForeignKey("catalog_categories.id", ondelete="RESTRICT"), nullable=False
    )
    slug = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    model_number = Column(Text)
    model_year = Column(Text)
    status = Column(Text, nullable=False, default="active")
    discontinued_at = Column(DateTime(timezone=True))
    weight_g = Column(Numeric(12, 3))
    weight_basis = Column(Text)
    capacity_ml = Column(Numeric(12, 1))
    specs = Column(JsonType, nullable=False, default=dict)
    official_url = Column(Text)
    # Denormalized, normalized text of brand + aliases + name + model number,
    # rebuilt by the pipeline; indexed with pg_trgm for typo-tolerant search.
    search_text = Column(Text, nullable=False, default="")
    verified_at = Column(DateTime(timezone=True))
    created_at, updated_at = _timestamps()

    brand = relationship("CatalogBrand")
    category = relationship("CatalogCategory")
    aliases = relationship(
        "CatalogProductAlias", back_populates="product", cascade="all, delete-orphan"
    )
    variants = relationship(
        "CatalogProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="CatalogProductVariant.sort_order",
    )
    images = relationship(
        "CatalogProductImage", back_populates="product", cascade="all, delete-orphan"
    )
    sources = relationship(
        "CatalogProductSource", back_populates="product", cascade="all, delete-orphan"
    )


class CatalogProductAlias(Base):
    __tablename__ = "catalog_product_aliases"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "alias_normalized", name="catalog_product_aliases_product_alias_key"
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id = Column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    alias = Column(Text, nullable=False)
    alias_normalized = Column(Text, nullable=False)

    product = relationship("CatalogProduct", back_populates="aliases")


class CatalogProductVariant(Base):
    """Sizes, lengths or generations of one product, each with its own specs."""

    __tablename__ = "catalog_product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "slug", name="catalog_product_variants_product_slug_key"),
        CheckConstraint(
            "status in ('active','discontinued')", name="catalog_product_variants_status_check"
        ),
        CheckConstraint(
            "weight_basis is null or weight_basis in "
            "('minimum','trail','packaged','average','claimed')",
            name="catalog_product_variants_weight_basis_check",
        ),
        CheckConstraint(
            "weight_g is null or weight_g > 0", name="catalog_product_variants_weight_check"
        ),
        CheckConstraint(
            "capacity_ml is null or capacity_ml > 0",
            name="catalog_product_variants_capacity_check",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id = Column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    slug = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    sku = Column(Text)
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False, default="active")
    weight_g = Column(Numeric(12, 3))
    weight_basis = Column(Text)
    capacity_ml = Column(Numeric(12, 1))
    specs = Column(JsonType, nullable=False, default=dict)
    created_at, updated_at = _timestamps()

    product = relationship("CatalogProduct", back_populates="variants")


class CatalogProductImage(Base):
    """Product imagery with auditable licensing. Only approved rows are served."""

    __tablename__ = "catalog_product_images"
    __table_args__ = (
        UniqueConstraint("product_id", "url", name="catalog_product_images_product_url_key"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id = Column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    url = Column(Text, nullable=False)
    alt_text = Column(Text, nullable=False)
    license = Column(Text, nullable=False)
    attribution = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    approved = Column(Boolean, nullable=False, default=False)
    created_at, updated_at = _timestamps()

    product = relationship("CatalogProduct", back_populates="images")


class CatalogSource(Base):
    __tablename__ = "catalog_sources"
    __table_args__ = (
        CheckConstraint(
            "kind in ('manufacturer','licensed_feed','manual')", name="catalog_sources_kind_check"
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    slug = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    homepage_url = Column(Text)
    terms_url = Column(Text)
    terms_notes = Column(Text)
    created_at, updated_at = _timestamps()


class CatalogProductSource(Base):
    """Provenance: which source record a product came from, and when it was checked.

    (source_id, source_record_id) is the stable identifier that makes imports
    idempotent — re-running a feed updates the same product instead of
    creating a duplicate.
    """

    __tablename__ = "catalog_product_sources"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "source_record_id", name="catalog_product_sources_source_record_key"
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id = Column(
        Uuid, ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    source_id = Column(Uuid, ForeignKey("catalog_sources.id", ondelete="RESTRICT"), nullable=False)
    source_record_id = Column(Text, nullable=False)
    source_url = Column(Text)
    verified_at = Column(DateTime(timezone=True))
    content_hash = Column(Text, nullable=False)
    last_seen_run_id = Column(Uuid, ForeignKey("catalog_ingestion_runs.id", ondelete="SET NULL"))
    created_at, updated_at = _timestamps()

    product = relationship("CatalogProduct", back_populates="sources")
    source = relationship("CatalogSource")


class CatalogIngestionRun(Base):
    __tablename__ = "catalog_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('running','succeeded','partial','failed')",
            name="catalog_ingestion_runs_status_check",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id = Column(Uuid, ForeignKey("catalog_sources.id", ondelete="RESTRICT"), nullable=False)
    status = Column(Text, nullable=False, default="running")
    dry_run = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    counts = Column(JsonType, nullable=False, default=dict)
    errors = Column(JsonType, nullable=False, default=list)

    source = relationship("CatalogSource")
