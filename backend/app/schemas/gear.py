"""Request/response models for the gear catalogue and personal inventory APIs."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

WeightUnit = Literal["g", "kg", "oz", "lb"]
VolumeUnit = Literal["ml", "l", "fl_oz", "cu_in"]
Condition = Literal["new", "good", "worn", "needs_repair", "retired"]
ValueSource = Literal["override", "variant", "product"]


class SpecRow(BaseModel):
    key: str
    label: str
    value: float | int | str | bool
    unit: str | None = None


class SubcategoryOut(BaseModel):
    slug: str
    name: str
    icon_key: str


class CategoryOut(BaseModel):
    slug: str
    name: str
    icon_key: str
    description: str | None
    subcategories: list[SubcategoryOut]


class CategoryRef(BaseModel):
    slug: str
    name: str
    icon_key: str
    top_slug: str
    top_name: str


class BrandRef(BaseModel):
    id: UUID
    slug: str
    name: str


class BrandOut(BrandRef):
    product_count: int


class ImageOut(BaseModel):
    url: str
    alt_text: str
    license: str
    attribution: str
    source_url: str


class VariantOut(BaseModel):
    id: UUID
    name: str
    sku: str | None
    status: str
    weight_g: float | None
    weight_basis: str | None
    capacity_ml: float | None
    specs: list[SpecRow]


class ProductSummaryOut(BaseModel):
    id: UUID
    brand: BrandRef
    name: str
    display_name: str
    category: CategoryRef
    status: str
    weight_g: float | None
    weight_basis: str | None
    weight_range_g: tuple[float, float] | None
    capacity_ml: float | None
    variant_count: int
    key_specs: list[SpecRow]
    image: ImageOut | None


class SourceRef(BaseModel):
    name: str
    url: str | None
    verified_at: datetime | None


class ProductDetailOut(ProductSummaryOut):
    model_number: str | None
    model_year: str | None
    official_url: str | None
    verified_at: datetime | None
    aliases: list[str]
    specs: list[SpecRow]
    variants: list[VariantOut]
    sources: list[SourceRef]


class ProductPage(BaseModel):
    items: list[ProductSummaryOut]
    total: int
    next_cursor: str | None


class MeasurementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal = Field(ge=0, le=Decimal("1000000"))
    unit: str


class WeightIn(MeasurementIn):
    unit: WeightUnit


class CapacityIn(MeasurementIn):
    value: Decimal = Field(gt=0, le=Decimal("1000000"))
    unit: VolumeUnit


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class UserGearBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    variant_id: UUID | None = None
    category: str | None = Field(default=None, max_length=60)
    custom_name: str | None = Field(default=None, max_length=120)
    custom_brand: str | None = Field(default=None, max_length=80)
    custom_model: str | None = Field(default=None, max_length=80)
    quantity: int = Field(default=1, ge=1, le=99)
    weight_override: WeightIn | None = None
    capacity_override: CapacityIn | None = None
    custom_specs: dict = Field(default_factory=dict, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
    condition: Condition | None = None
    image_path: str | None = Field(default=None, max_length=200)

    _clean = field_validator("custom_name", "custom_brand", "custom_model", mode="before")(
        lambda value: _clean_optional_text(value) if isinstance(value, str) else value
    )

    @field_validator("notes", mode="before")
    @classmethod
    def _clean_notes(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class UserGearCreate(UserGearBase):
    # Generated once per "add" dialog by the client; retries with the same id
    # return the already-created item instead of a duplicate.
    client_request_id: UUID | None = None


class UserGearUpdate(UserGearBase):
    """Partial update: only fields present in the request body are changed.
    Send null to clear an optional field."""

    quantity: int | None = Field(default=None, ge=1, le=99)
    custom_specs: dict | None = Field(default=None, max_length=20)


class WeightOut(BaseModel):
    effective_g: float | None
    source: ValueSource | None
    manufacturer_g: float | None
    manufacturer_basis: str | None
    override_g: float | None
    override_unit: WeightUnit | None


class CapacityOut(BaseModel):
    effective_ml: float | None
    source: ValueSource | None
    manufacturer_ml: float | None
    override_ml: float | None


class UserGearItemOut(BaseModel):
    id: UUID
    kind: Literal["catalog", "custom"]
    display_name: str
    brand_name: str | None
    category: CategoryRef
    product: ProductSummaryOut | None
    variant: VariantOut | None
    custom_name: str | None
    custom_brand: str | None
    custom_model: str | None
    quantity: int
    weight: WeightOut
    capacity: CapacityOut
    custom_specs: list[SpecRow]
    notes: str | None
    condition: Condition | None
    image_path: str | None
    created_at: datetime
    updated_at: datetime


class CollectionSummary(BaseModel):
    item_count: int
    total_quantity: int
    # Sum of effective weight × quantity over items whose weight is known.
    known_weight_g: float
    items_missing_weight: int
    weight_is_complete: bool
    categories_with_items: list[str]


class GearCollectionOut(BaseModel):
    items: list[UserGearItemOut]
    summary: CollectionSummary
