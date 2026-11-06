"""Importing a LighterPack list into the signed-in user's gear.

Two steps, so nothing is added until the user has seen every match:

    POST /api/me/gear/import/lighterpack          {csv}  -> proposed matches (saves nothing)
    POST /api/me/gear/import/lighterpack/confirm  {import_id, items} -> adds the confirmed items

The confirm request carries what the user settled on for each item: a
catalogue product (the proposed match, an alternative, or one they searched
for) or a custom item with its LighterPack name and weight. Every item gets a
client_request_id derived from the import id and its row, so retrying a
confirm adds nothing twice. All items are added in one transaction: one bad
item adds none.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import get_current_user_id
from app.catalog.normalize import grams_from, normalize_text
from app.catalog.presenters import product_summary
from app.database import get_db
from app.gear_import.lighterpack import MAX_NAME, MAX_NOTES, ImportFileError, Match, Product, match_rows, parse_csv
from app.models.catalog import CatalogBrand, CatalogCategory, CatalogProduct
from app.models.user_gear import UserGearItem
from app.routers.me_gear import _apply, _invalid
from app.schemas.gear import Carry, ProductSummaryOut, WeightIn

router = APIRouter(prefix="/api/me/gear/import", tags=["my gear"])

# About 3,000 items' worth of CSV; a LighterPack list is far smaller.
MAX_CSV_CHARS = 500_000
MAX_CONFIRM_ITEMS = 500
# A LighterPack weight this close to the catalogue's is the catalogue's;
# further off, it's what the user's own scale says and is kept as theirs.
SAME_WEIGHT = Decimal("0.05")


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv: str = Field(min_length=1, max_length=MAX_CSV_CHARS)


class WeightOut(BaseModel):
    value: float
    unit: Literal["g", "kg", "oz", "lb"]


class CandidateOut(BaseModel):
    product: ProductSummaryOut
    confidence: Literal["high", "medium", "low"]
    score: float


class PreviewRow(BaseModel):
    index: int
    name: str
    lighterpack_category: str
    description: str
    quantity: int
    weight: WeightOut | None
    carry: Carry | None
    # The best catalogue product, when one is likely enough to propose.
    match: CandidateOut | None
    alternatives: list[CandidateOut]
    # Subcategory slug for adding it as a custom item.
    category: str
    # Proposed for import: everything but food and fuel (consumables).
    include: bool


class PreviewOut(BaseModel):
    rows: list[PreviewRow]
    matched: int
    unmatched: int


class ConfirmItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, lt=10_000)
    # A catalogue product, or None for a custom item.
    product_id: UUID | None = None
    name: str | None = Field(default=None, max_length=MAX_NAME)
    category: str | None = Field(default=None, max_length=60)
    quantity: int = Field(default=1, ge=1, le=99)
    weight: WeightIn | None = None
    carry: Carry | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Generated once per import by the client.
    import_id: UUID
    items: list[ConfirmItem] = Field(min_length=1, max_length=MAX_CONFIRM_ITEMS)


class ConfirmOut(BaseModel):
    added: int
    # Already added by an earlier try of the same import.
    already_added: int


def _catalogue(db: Session) -> tuple[list[Product], dict[UUID, CatalogProduct]]:
    rows = db.scalars(
        select(CatalogProduct)
        .options(
            joinedload(CatalogProduct.brand).selectinload(CatalogBrand.aliases),
            joinedload(CatalogProduct.category).joinedload(CatalogCategory.parent),
            selectinload(CatalogProduct.variants),
            selectinload(CatalogProduct.images),
            selectinload(CatalogProduct.aliases),
        )
    ).unique().all()
    products = []
    for row in rows:
        names = {normalize_text(row.name), *(alias.alias_normalized for alias in row.aliases)}
        brand_names = {normalize_text(row.brand.name), *(alias.alias_normalized for alias in row.brand.aliases)}
        weights = [w for w in (row.weight_g, *(v.weight_g for v in row.variants)) if w is not None]
        products.append(Product(
            id=row.id,
            brand=row.brand.name,
            brand_names=tuple(sorted(n for n in brand_names if n)),
            name=row.name,
            names=tuple(sorted(n for n in names if n)),
            category=row.category.slug,
            weights_g=tuple(Decimal(w) for w in weights),
        ))
    return products, {row.id: row for row in rows}


def _row_out(match: Match, by_id: dict[UUID, CatalogProduct]) -> PreviewRow:
    def candidate(c) -> CandidateOut:
        return CandidateOut(product=product_summary(by_id[c.product.id]), confidence=c.confidence, score=c.score)

    row = match.row
    return PreviewRow(
        index=row.index,
        name=row.name,
        lighterpack_category=row.category,
        description=row.description,
        quantity=row.quantity,
        weight=WeightOut(value=float(row.weight_value), unit=row.weight_unit) if row.weight_value is not None else None,
        carry=row.carry,
        match=candidate(match.best) if match.best else None,
        alternatives=[candidate(c) for c in match.alternatives],
        category=match.category,
        include=not row.consumable,
    )


@router.post("/lighterpack", response_model=PreviewOut)
def preview_lighterpack(
    payload: PreviewIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Read the export and propose a match for each item. Saves nothing."""
    try:
        rows = parse_csv(payload.csv)
    except ImportFileError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    products, by_id = _catalogue(db)
    out = [_row_out(match, by_id) for match in match_rows(rows, products)]
    matched = sum(1 for row in out if row.match)
    return PreviewOut(rows=out, matched=matched, unmatched=len(out) - matched)


def _keeps_own_weight(product: CatalogProduct, weight: WeightIn) -> bool:
    if product.weight_g is None:
        return True
    grams = grams_from(weight.value, weight.unit)
    return abs(grams - product.weight_g) > product.weight_g * SAME_WEIGHT


@router.post("/lighterpack/confirm", response_model=ConfirmOut, status_code=status.HTTP_201_CREATED)
def confirm_lighterpack(
    payload: ConfirmIn,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if len({item.index for item in payload.items}) != len(payload.items):
        raise _invalid("Each item can only be imported once.")
    request_ids = {item.index: uuid5(payload.import_id, f"lighterpack:{item.index}") for item in payload.items}
    done = set(db.scalars(
        select(UserGearItem.client_request_id).where(
            UserGearItem.user_id == user_id, UserGearItem.client_request_id.in_(request_ids.values())
        )
    ))
    added = 0
    for item in payload.items:
        if request_ids[item.index] in done:
            continue
        data: dict = {"quantity": item.quantity, "carry": item.carry, "notes": item.notes}
        if item.product_id is not None:
            product = db.get(CatalogProduct, item.product_id)
            if product is None:
                raise _invalid(f"Item {item.index + 1}: that catalogue product doesn't exist.")
            data["product_id"] = product.id
            if item.weight is not None and _keeps_own_weight(product, item.weight):
                data["weight_override"] = item.weight.model_dump()
        else:
            name = " ".join((item.name or "").split())
            if not name:
                raise _invalid(f"Item {item.index + 1}: give it a name.")
            if not item.category:
                raise _invalid(f"Item {item.index + 1}: choose a category.")
            data.update(product_id=None, custom_name=name, category=item.category)
            if item.weight is not None:
                data["weight_override"] = item.weight.model_dump()
        gear = UserGearItem(user_id=user_id, client_request_id=request_ids[item.index])
        try:
            _apply(db, user_id, gear, data)
        except HTTPException as error:
            db.rollback()
            raise _invalid(f"Item {item.index + 1}: {error.detail}") from error
        db.add(gear)
        added += 1
    try:
        db.commit()
    except IntegrityError as error:
        # A concurrent retry of the same import got there first.
        db.rollback()
        raise HTTPException(status_code=409, detail="This import is already being added. Refresh your gear.") from error
    return ConfirmOut(added=added, already_added=len(done))
