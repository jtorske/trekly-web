"""Public, read-only gear catalogue endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.catalog.normalize import normalize_text
from app.catalog.presenters import product_detail, product_summary
from app.catalog.search import (
    InvalidCursor,
    UnknownFilter,
    category_ids,
    decode_cursor,
    encode_cursor,
    search_products,
)
from app.database import get_db
from app.models.catalog import (
    CatalogBrand,
    CatalogBrandAlias,
    CatalogCategory,
    CatalogProduct,
    CatalogProductSource,
    CatalogProductVariant,
)
from app.models.user_gear import UserGearItem
from app.schemas.gear import (
    BrandOut,
    CategoryOut,
    ProductDetailOut,
    ProductPage,
    ProductSummaryOut,
    SubcategoryOut,
)

router = APIRouter(prefix="/api/gear", tags=["gear catalogue"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    categories = db.scalars(
        select(CatalogCategory).order_by(CatalogCategory.sort_order, CatalogCategory.name)
    ).all()
    children: dict = {}
    for category in categories:
        if category.parent_id is not None:
            children.setdefault(category.parent_id, []).append(category)
    return [
        CategoryOut(
            slug=category.slug,
            name=category.name,
            icon_key=category.icon_key,
            description=category.description,
            subcategories=[
                SubcategoryOut(slug=child.slug, name=child.name, icon_key=child.icon_key)
                for child in children.get(category.id, [])
            ],
        )
        for category in categories
        if category.parent_id is None
    ]


@router.get("/brands", response_model=list[BrandOut])
def list_brands(
    q: str = Query("", max_length=80),
    category: str | None = Query(None, max_length=400),
    db: Session = Depends(get_db),
):
    """Brands that have at least one product, optionally filtered by name/alias and category."""
    stmt = (
        select(CatalogBrand, func.count(CatalogProduct.id))
        .join(CatalogProduct, CatalogProduct.brand_id == CatalogBrand.id)
        .group_by(CatalogBrand.id)
        .order_by(CatalogBrand.name)
    )
    if category:
        try:
            stmt = stmt.where(CatalogProduct.category_id.in_(category_ids(db, category)))
        except UnknownFilter as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    normalized = normalize_text(q)
    if normalized:
        alias_match = (
            select(CatalogBrandAlias.brand_id)
            .where(CatalogBrandAlias.alias_normalized.like(f"%{normalized}%"))
            .scalar_subquery()
        )
        stmt = stmt.where(CatalogBrand.id.in_(alias_match))
    return [
        BrandOut(id=brand.id, slug=brand.slug, name=brand.name, product_count=count)
        for brand, count in db.execute(stmt).all()
    ]


@router.get("/products", response_model=ProductPage)
def list_products(
    q: str = Query("", max_length=120, description="Name, brand, model, alias or category"),
    category: str | None = Query(
        None,
        max_length=400,
        description="Top-level or subcategory slug, or a comma-separated list of them",
    ),
    brand: str | None = Query(None, max_length=80, description="Brand slug"),
    include_discontinued: bool = True,
    max_weight_g: float | None = Query(None, gt=0, le=100000),
    min_capacity_ml: float | None = Query(None, gt=0, le=1000000),
    max_capacity_ml: float | None = Query(None, gt=0, le=1000000),
    cursor: str | None = Query(None, max_length=200, description="Opaque cursor from next_cursor"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        offset = decode_cursor(cursor)
        result = search_products(
            db,
            q=q,
            category=category,
            brand=brand,
            include_discontinued=include_discontinued,
            max_weight_g=max_weight_g,
            min_capacity_ml=min_capacity_ml,
            max_capacity_ml=max_capacity_ml,
            offset=offset,
            limit=limit,
        )
    except InvalidCursor as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except UnknownFilter as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ProductPage(
        items=[product_summary(product) for product in result.products],
        total=result.total,
        next_cursor=encode_cursor(result.next_offset) if result.next_offset is not None else None,
    )


# A product's owners only count once this many people own it, so the ranking
# can't reveal that one particular user owns something.
POPULAR_MIN_OWNERS = 3


@router.get("/products/popular", response_model=list[ProductSummaryOut])
def popular_products(
    category: str = Query(..., max_length=400, description="Slug or comma-separated slugs"),
    limit: int = Query(3, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Suggestions for an empty gear mat slot: active products in the
    categories, most owned first (distinct owners), then lightest."""
    try:
        ids = category_ids(db, category)
    except UnknownFilter as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    owners = (
        select(UserGearItem.product_id, func.count(func.distinct(UserGearItem.user_id)).label("n"))
        .where(UserGearItem.product_id.is_not(None))
        .group_by(UserGearItem.product_id)
        .subquery()
    )
    lightest_variant = (
        select(CatalogProductVariant.product_id, func.min(CatalogProductVariant.weight_g).label("g"))
        .group_by(CatalogProductVariant.product_id)
        .subquery()
    )
    owned = case((owners.c.n >= POPULAR_MIN_OWNERS, owners.c.n), else_=0)
    weight = func.coalesce(CatalogProduct.weight_g, lightest_variant.c.g)
    products = db.scalars(
        select(CatalogProduct)
        .outerjoin(owners, owners.c.product_id == CatalogProduct.id)
        .outerjoin(lightest_variant, lightest_variant.c.product_id == CatalogProduct.id)
        .where(CatalogProduct.category_id.in_(ids), CatalogProduct.status == "active")
        .order_by(owned.desc(), weight.is_(None), weight, CatalogProduct.name)
        .limit(limit)
        .options(
            joinedload(CatalogProduct.brand),
            joinedload(CatalogProduct.category).joinedload(CatalogCategory.parent),
            selectinload(CatalogProduct.variants),
            selectinload(CatalogProduct.images),
        )
    ).unique().all()
    return [product_summary(product) for product in products]


def load_product(db: Session, product_id: UUID) -> CatalogProduct | None:
    return db.scalar(
        select(CatalogProduct)
        .where(CatalogProduct.id == product_id)
        .options(
            joinedload(CatalogProduct.brand),
            joinedload(CatalogProduct.category).joinedload(CatalogCategory.parent),
            selectinload(CatalogProduct.variants),
            selectinload(CatalogProduct.images),
            selectinload(CatalogProduct.aliases),
            selectinload(CatalogProduct.sources).joinedload(CatalogProductSource.source),
        )
    )


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def get_product(product_id: UUID, db: Session = Depends(get_db)):
    product = load_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_detail(product)
