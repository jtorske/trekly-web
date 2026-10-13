"""The provider-neutral catalogue record every ingestion source maps into.

Providers (app/catalog/providers) turn their raw format into dicts of this
shape; `CatalogRecord` validates them, and `normalize_record` converts units
to canonical form. Anything not reliably known is simply omitted — there are
no defaults that invent a weight, capacity or spec.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalog.normalize import (
    MeasurementError,
    grams_from,
    ml_from,
    normalize_text,
    parse_weight_text,
    slugify,
)
from app.catalog.specs import validate_specs
from app.catalog.taxonomy import SUBCATEGORY_TO_TOP

WeightBasis = Literal["minimum", "trail", "packaged", "average", "claimed"]
Status = Literal["active", "discontinued"]

RECORD_ID_PATTERN = r"^[a-z0-9][a-z0-9:._/-]{1,199}$"


class WeightIn(BaseModel):
    """Either a published string ("1 lb 2 oz") or a value + unit."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    value: Decimal | None = None
    unit: Literal["g", "kg", "oz", "lb"] | None = None
    basis: WeightBasis | None = None

    @model_validator(mode="after")
    def _one_form(self):
        if bool(self.text) == (self.value is not None):
            raise ValueError("weight needs exactly one of 'text' or 'value'+'unit'")
        if self.value is not None and self.unit is None:
            raise ValueError("weight 'value' needs a 'unit'")
        return self

    def grams(self) -> Decimal:
        try:
            grams = parse_weight_text(self.text) if self.text else grams_from(self.value, self.unit)
        except MeasurementError as error:
            raise ValueError(str(error)) from error
        if grams <= 0:
            raise ValueError("weight must be greater than zero")
        return grams


class CapacityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    unit: Literal["ml", "l", "fl_oz", "cu_in"]

    def millilitres(self) -> Decimal:
        try:
            return ml_from(self.value, self.unit)
        except MeasurementError as error:
            raise ValueError(str(error)) from error


class VariantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    sku: str | None = Field(default=None, max_length=80)
    status: Status = "active"
    weight: WeightIn | None = None
    capacity: CapacityIn | None = None
    specs: dict = Field(default_factory=dict)


class ImageRecord(BaseModel):
    """Imagery is only ingested with a licence and attribution, and only
    served once a reviewer has set approved: true."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(pattern=r"^https://")
    alt_text: str = Field(min_length=3)
    license: str = Field(min_length=2)
    attribution: str = Field(min_length=2)
    source_url: str = Field(pattern=r"^https://")
    approved: bool = False


class CatalogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: str = Field(pattern=RECORD_ID_PATTERN)
    brand: str = Field(min_length=1, max_length=80)
    brand_aliases: list[str] = Field(default_factory=list)
    brand_website: str | None = Field(default=None, pattern=r"^https://")
    name: str = Field(min_length=1, max_length=160)
    category: str
    aliases: list[str] = Field(default_factory=list)
    model_number: str | None = Field(default=None, max_length=80)
    model_year: str | None = Field(default=None, max_length=20)
    status: Status = "active"
    official_url: str | None = Field(default=None, pattern=r"^https://")
    source_url: str = Field(pattern=r"^https://")
    verified_at: date
    weight: WeightIn | None = None
    capacity: CapacityIn | None = None
    specs: dict = Field(default_factory=dict)
    variants: list[VariantRecord] = Field(default_factory=list)
    images: list[ImageRecord] = Field(default_factory=list)

    @field_validator("brand", "name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if not normalize_text(value):
            raise ValueError("must contain letters or numbers")
        return value

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in SUBCATEGORY_TO_TOP:
            raise ValueError(f"unknown subcategory '{value}'")
        return value

    @field_validator("verified_at")
    @classmethod
    def _not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("verified_at cannot be in the future")
        return value

    @model_validator(mode="after")
    def _validate_nested(self):
        self.specs = validate_specs(self.category, self.specs)
        seen: set[str] = set()
        for variant in self.variants:
            slug = slugify(variant.name)
            if slug in seen:
                raise ValueError(f"duplicate variant '{variant.name}'")
            seen.add(slug)
            variant.specs = validate_specs(self.category, variant.specs)
        return self


@dataclass
class NormalizedVariant:
    slug: str
    name: str
    sku: str | None
    status: str
    sort_order: int
    weight_g: Decimal | None
    weight_basis: str | None
    capacity_ml: Decimal | None
    specs: dict


@dataclass
class NormalizedRecord:
    record: CatalogRecord
    product_slug: str
    weight_g: Decimal | None
    weight_basis: str | None
    capacity_ml: Decimal | None
    specs: dict
    variants: list[NormalizedVariant] = field(default_factory=list)
    content_hash: str = ""


def normalize_record(record: CatalogRecord) -> NormalizedRecord:
    specs = dict(record.specs)
    if record.weight and record.weight.text:
        specs.setdefault("published_weight", record.weight.text)

    variants = []
    for index, variant in enumerate(record.variants):
        variant_specs = dict(variant.specs)
        if variant.weight and variant.weight.text:
            variant_specs.setdefault("published_weight", variant.weight.text)
        variants.append(
            NormalizedVariant(
                slug=slugify(variant.name),
                name=variant.name,
                sku=variant.sku,
                status=variant.status,
                sort_order=index,
                weight_g=variant.weight.grams() if variant.weight else None,
                weight_basis=variant.weight.basis if variant.weight else None,
                capacity_ml=variant.capacity.millilitres() if variant.capacity else None,
                specs=variant_specs,
            )
        )

    normalized = NormalizedRecord(
        record=record,
        product_slug=slugify(record.name),
        weight_g=record.weight.grams() if record.weight else None,
        weight_basis=record.weight.basis if record.weight else None,
        capacity_ml=record.capacity.millilitres() if record.capacity else None,
        specs=specs,
        variants=variants,
    )
    normalized.content_hash = hashlib.sha256(
        json.dumps(record.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    return normalized
