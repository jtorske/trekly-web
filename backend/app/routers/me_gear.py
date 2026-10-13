"""The signed-in user's personal gear inventory.

Every query is filtered by the user id taken from the verified access token;
ids in the URL or body are never trusted for ownership. Another user's item
id returns 404 — the same as a missing one — so ids can't be probed.
"""

import re
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import get_current_user_id
from app.catalog.normalize import grams_from, ml_from
from app.catalog.presenters import effective_weight, gear_item_out
from app.catalog.specs import validate_specs
from app.database import get_db
from app.models.catalog import (
    CatalogCategory,
    CatalogProduct,
    CatalogProductVariant,
)
from app.models.user_gear import UserGearItem
from app.schemas.gear import (
    CollectionSummary,
    GearCollectionOut,
    UserGearCreate,
    UserGearItemOut,
    UserGearUpdate,
)

router = APIRouter(prefix="/api/me/gear", tags=["my gear"])

IMAGE_NAME = re.compile(r"^[0-9a-f-]{36}\.(?:jpg|jpeg|png|webp)$")


def _item_query(user_id: UUID):
    return (
        select(UserGearItem)
        .where(UserGearItem.user_id == user_id)
        .options(
            joinedload(UserGearItem.category).joinedload(CatalogCategory.parent),
            joinedload(UserGearItem.variant),
            joinedload(UserGearItem.product).options(
                joinedload(CatalogProduct.brand),
                joinedload(CatalogProduct.category).joinedload(CatalogCategory.parent),
                selectinload(CatalogProduct.variants),
                selectinload(CatalogProduct.images),
            ),
        )
    )


def _get_owned(db: Session, user_id: UUID, item_id: UUID) -> UserGearItem:
    item = db.scalar(_item_query(user_id).where(UserGearItem.id == item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Gear item not found")
    return item


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _resolve_category(db: Session, slug: str) -> CatalogCategory:
    category = db.scalar(select(CatalogCategory).where(CatalogCategory.slug == slug))
    if category is None:
        raise _invalid(f"Unknown category '{slug}'")
    return category


def _apply(db: Session, user_id: UUID, item: UserGearItem, data: dict) -> None:
    """Apply validated request fields to an item, enforcing cross-field rules."""
    if "product_id" in data or "variant_id" in data:
        product_id = data.get("product_id", item.product_id)
        variant_id = data.get("variant_id", item.variant_id if "product_id" not in data else None)
        if product_id is None:
            if variant_id is not None:
                raise _invalid("A variant needs a catalogue product.")
            item.product = None
            item.variant = None
        else:
            product = db.get(CatalogProduct, product_id)
            if product is None:
                raise _invalid("That catalogue product doesn't exist.")
            variant = None
            if variant_id is not None:
                variant = db.get(CatalogProductVariant, variant_id)
                if variant is None or variant.product_id != product.id:
                    raise _invalid("That size or variant doesn't belong to the product.")
            item.product = product
            item.variant = variant
            item.category = product.category

    for field in ("custom_name", "custom_brand", "custom_model", "notes", "condition"):
        if field in data:
            setattr(item, field, data[field])

    if item.product is not None and (item.custom_brand or item.custom_model):
        raise _invalid("Brand and model come from the catalogue product; remove them or add a custom item.")
    if item.product is None:
        if not item.custom_name:
            raise _invalid("Give your item a name, or choose a catalogue product.")
        category_slug = data.get("category")
        if category_slug:
            item.category = _resolve_category(db, category_slug)
        elif item.category is None:
            raise _invalid("Choose a category for your item.")
    elif item.custom_name:
        # Catalogue items take their name from the product.
        item.custom_name = None

    if "quantity" in data and data["quantity"] is not None:
        item.quantity = data["quantity"]

    if "weight_override" in data:
        override = data["weight_override"]
        if override is None:
            item.weight_override_g, item.weight_override_unit = None, None
        else:
            item.weight_override_g = grams_from(override["value"], override["unit"])
            item.weight_override_unit = override["unit"]

    if "capacity_override" in data:
        override = data["capacity_override"]
        item.capacity_override_ml = (
            None if override is None else ml_from(override["value"], override["unit"])
        )

    if "custom_specs" in data and data["custom_specs"] is not None:
        try:
            item.custom_specs = validate_specs(item.category.slug, data["custom_specs"])
        except ValueError as error:
            raise _invalid(str(error)) from error

    if "image_path" in data:
        path = data["image_path"]
        if path is not None:
            folder, _, name = path.partition("/")
            if folder != str(user_id) or not IMAGE_NAME.match(name):
                raise _invalid("Photos must be uploaded to your own gear-photos folder.")
        item.image_path = path


def _summary(items: list[UserGearItem]) -> CollectionSummary:
    known = Decimal(0)
    missing = 0
    for item in items:
        grams, _ = effective_weight(item)
        if grams is None:
            missing += 1
        else:
            known += grams * item.quantity
    top_slugs = {(item.category.parent or item.category).slug for item in items}
    return CollectionSummary(
        item_count=len(items),
        total_quantity=sum(item.quantity for item in items),
        known_weight_g=float(known),
        items_missing_weight=missing,
        weight_is_complete=missing == 0,
        categories_with_items=sorted(top_slugs),
    )


@router.get("", response_model=GearCollectionOut)
def list_my_gear(
    user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    items = db.scalars(_item_query(user_id).order_by(UserGearItem.created_at)).unique().all()
    return GearCollectionOut(items=[gear_item_out(item) for item in items], summary=_summary(items))


@router.post("", response_model=UserGearItemOut, status_code=status.HTTP_201_CREATED)
def add_my_gear(
    payload: UserGearCreate,
    response: Response,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if payload.client_request_id is not None:
        existing = db.scalar(
            _item_query(user_id).where(UserGearItem.client_request_id == payload.client_request_id)
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return gear_item_out(existing)

    item = UserGearItem(user_id=user_id, client_request_id=payload.client_request_id)
    data = payload.model_dump(exclude={"client_request_id"})
    if payload.product_id is None:
        if not payload.category:
            raise _invalid("Choose a category for your item.")
        data["product_id"] = None
    _apply(db, user_id, item, data)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # A concurrent retry with the same client_request_id won the race.
        existing = db.scalar(
            _item_query(user_id).where(UserGearItem.client_request_id == payload.client_request_id)
        ) if payload.client_request_id else None
        if existing is None:
            raise _invalid("That item couldn't be saved.") from error
        response.status_code = status.HTTP_200_OK
        return gear_item_out(existing)
    return gear_item_out(_get_owned(db, user_id, item.id))


@router.patch("/{item_id}", response_model=UserGearItemOut)
def update_my_gear(
    item_id: UUID,
    payload: UserGearUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = _get_owned(db, user_id, item_id)
    data = payload.model_dump(exclude_unset=True)
    if "quantity" in data and data["quantity"] is None:
        raise _invalid("Quantity can't be empty.")
    _apply(db, user_id, item, data)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _invalid("That change couldn't be saved.") from error
    db.expire_all()
    return gear_item_out(_get_owned(db, user_id, item_id))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_gear(
    item_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = _get_owned(db, user_id, item_id)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
