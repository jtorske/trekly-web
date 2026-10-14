"""The signed-in user's named gear setups."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user_id
from app.catalog.presenters import effective_weight, gear_item_out
from app.database import get_db
from app.models.setup import MAX_ITEMS_PER_SETUP, MAX_SETUPS_PER_USER, GearSetup, GearSetupItem
from app.models.user_gear import UserGearItem
from app.routers.me_gear import _item_query
from app.schemas.gear import UserGearItemOut

router = APIRouter(prefix="/api/me/setups", tags=["my gear setups"])


class SetupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    item_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ITEMS_PER_SETUP)

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def _clean_description(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class SetupUpdate(SetupIn):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    item_ids: list[UUID] | None = Field(default=None, max_length=MAX_ITEMS_PER_SETUP)


class SetupOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    items: list[UserGearItemOut]
    item_count: int
    known_weight_g: float
    items_missing_weight: int
    created_at: datetime
    updated_at: datetime


def _load(db: Session, user_id: UUID, setup_id: UUID | None = None):
    stmt = (
        select(GearSetup)
        .where(GearSetup.user_id == user_id)
        .options(selectinload(GearSetup.entries))
        .order_by(GearSetup.created_at)
    )
    if setup_id is not None:
        stmt = stmt.where(GearSetup.id == setup_id)
    return db.scalars(stmt).all()


def _out(db: Session, user_id: UUID, setup: GearSetup) -> SetupOut:
    ids = [entry.gear_item_id for entry in setup.entries]
    items = (
        {item.id: item for item in db.scalars(_item_query(user_id).where(UserGearItem.id.in_(ids))).unique()}
        if ids
        else {}
    )
    ordered = [items[item_id] for item_id in ids if item_id in items]
    known = Decimal(0)
    missing = 0
    for item in ordered:
        grams, _ = effective_weight(item)
        if grams is None:
            missing += 1
        else:
            known += grams * item.quantity
    return SetupOut(
        id=setup.id,
        name=setup.name,
        description=setup.description,
        items=[gear_item_out(item) for item in ordered],
        item_count=len(ordered),
        known_weight_g=float(known),
        items_missing_weight=missing,
        created_at=setup.created_at,
        updated_at=setup.updated_at,
    )


def _check_name(db: Session, user_id: UUID, name: str, exclude: UUID | None = None) -> None:
    stmt = select(GearSetup.id).where(
        GearSetup.user_id == user_id, func.lower(GearSetup.name) == name.lower()
    )
    if exclude is not None:
        stmt = stmt.where(GearSetup.id != exclude)
    if db.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail="You already have a setup with that name.")


def _set_items(db: Session, user_id: UUID, setup: GearSetup, item_ids: list[UUID]) -> None:
    unique_ids = list(dict.fromkeys(item_ids))
    if unique_ids:
        owned = set(
            db.scalars(
                select(UserGearItem.id).where(
                    UserGearItem.user_id == user_id, UserGearItem.id.in_(unique_ids)
                )
            )
        )
        if len(owned) != len(unique_ids):
            # Same answer whether the item is someone else's or doesn't exist.
            raise HTTPException(status_code=422, detail="Setups can only include gear you own.")
    setup.entries = [
        GearSetupItem(gear_item_id=item_id, position=index) for index, item_id in enumerate(unique_ids)
    ]


@router.get("", response_model=list[SetupOut])
def list_setups(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return [_out(db, user_id, setup) for setup in _load(db, user_id)]


@router.post("", response_model=SetupOut, status_code=status.HTTP_201_CREATED)
def create_setup(
    payload: SetupIn, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    count = db.scalar(select(func.count()).select_from(GearSetup).where(GearSetup.user_id == user_id))
    if (count or 0) >= MAX_SETUPS_PER_USER:
        raise HTTPException(status_code=422, detail=f"You can have up to {MAX_SETUPS_PER_USER} setups.")
    _check_name(db, user_id, payload.name)
    setup = GearSetup(user_id=user_id, name=payload.name, description=payload.description)
    _set_items(db, user_id, setup, payload.item_ids)
    db.add(setup)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already have a setup with that name.") from error
    return _out(db, user_id, _load(db, user_id, setup.id)[0])


@router.patch("/{setup_id}", response_model=SetupOut)
def update_setup(
    setup_id: UUID,
    payload: SetupUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    found = _load(db, user_id, setup_id)
    if not found:
        raise HTTPException(status_code=404, detail="Setup not found")
    setup = found[0]
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        if not data["name"]:
            raise HTTPException(status_code=422, detail="Give your setup a name.")
        _check_name(db, user_id, data["name"], exclude=setup.id)
        setup.name = data["name"]
    if "description" in data:
        setup.description = data["description"]
    if data.get("item_ids") is not None:
        _set_items(db, user_id, setup, data["item_ids"])
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already have a setup with that name.") from error
    db.expire_all()
    return _out(db, user_id, _load(db, user_id, setup_id)[0])


@router.delete("/{setup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setup(
    setup_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Deletes only the grouping; the gear items stay in the inventory."""
    found = _load(db, user_id, setup_id)
    if not found:
        raise HTTPException(status_code=404, detail="Setup not found")
    db.delete(found[0])
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
