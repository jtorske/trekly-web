"""Catalogue search and filtering.

Search behaviour
- The query is normalized like the stored search_text (lowercase, no
  accents or punctuation), so "arcteryx" matches "Arc'teryx".
- Every query token must appear somewhere in the product's search document
  (brand, brand aliases, name, aliases, model number, category, variants).
- On Postgres, pg_trgm word similarity also admits near-misses so typos
  ("cooper spur") still find "Copper Spur"; exact token matches rank first.
- Category filters accept a top-level slug (includes its subcategories) or a
  subcategory slug.

Pagination is offset-based behind an opaque cursor: the catalogue is small
enough (thousands of rows) that this stays fast and keeps relevance ordering
stable between pages.
"""

import base64
import json
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.catalog.normalize import normalize_text
from app.models.catalog import (
    CatalogBrand,
    CatalogCategory,
    CatalogProduct,
    CatalogProductVariant,
)

TYPO_SIMILARITY_THRESHOLD = 0.45
MAX_QUERY_TOKENS = 8


class InvalidCursor(ValueError):
    pass


class UnknownFilter(LookupError):
    pass


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = json.loads(base64.urlsafe_b64decode(padded))["o"]
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidCursor("Invalid cursor") from error
    if not isinstance(offset, int) or offset < 0:
        raise InvalidCursor("Invalid cursor")
    return offset


def _escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


MAX_CATEGORY_FILTERS = 10


def category_ids(session: Session, slugs: str) -> list:
    """Ids for one slug or a comma-separated list ("tents,tarps").

    A top-level slug includes its subcategories. Unknown slugs are an error
    rather than silently ignored, so a mistyped slot can never widen results.
    """
    wanted = [slug.strip() for slug in slugs.split(",") if slug.strip()][:MAX_CATEGORY_FILTERS]
    if not wanted:
        raise UnknownFilter("Empty category filter")
    ids: list = []
    for slug in wanted:
        category = session.scalar(select(CatalogCategory).where(CatalogCategory.slug == slug))
        if category is None:
            raise UnknownFilter(f"Unknown category '{slug}'")
        ids.append(category.id)
        ids.extend(
            session.scalars(
                select(CatalogCategory.id).where(CatalogCategory.parent_id == category.id)
            ).all()
        )
    return ids


@dataclass
class SearchResult:
    products: list[CatalogProduct]
    total: int
    next_offset: int | None


def search_products(
    session: Session,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    include_discontinued: bool = True,
    max_weight_g: float | None = None,
    min_capacity_ml: float | None = None,
    max_capacity_ml: float | None = None,
    offset: int = 0,
    limit: int = 20,
) -> SearchResult:
    stmt: Select = select(CatalogProduct.id).join(CatalogBrand)
    if category:
        stmt = stmt.where(CatalogProduct.category_id.in_(category_ids(session, category)))
    if brand:
        if session.scalar(select(CatalogBrand.id).where(CatalogBrand.slug == brand)) is None:
            raise UnknownFilter(f"Unknown brand '{brand}'")
        stmt = stmt.where(CatalogBrand.slug == brand)
    if not include_discontinued:
        stmt = stmt.where(CatalogProduct.status == "active")
    # Weight/capacity filters match a product if the product itself or any of
    # its variants qualifies. Products with unknown values don't match: we
    # can't claim an unknown weight is under a limit.
    if max_weight_g is not None:
        variant_ok = select(CatalogProductVariant.id).where(
            CatalogProductVariant.product_id == CatalogProduct.id,
            CatalogProductVariant.weight_g <= max_weight_g,
        )
        stmt = stmt.where(or_(CatalogProduct.weight_g <= max_weight_g, variant_ok.exists()))
    for bound, op in ((min_capacity_ml, "ge"), (max_capacity_ml, "le")):
        if bound is None:
            continue
        product_cond = (
            CatalogProduct.capacity_ml >= bound if op == "ge" else CatalogProduct.capacity_ml <= bound
        )
        variant_cond = (
            CatalogProductVariant.capacity_ml >= bound
            if op == "ge"
            else CatalogProductVariant.capacity_ml <= bound
        )
        variant_ok = select(CatalogProductVariant.id).where(
            CatalogProductVariant.product_id == CatalogProduct.id, variant_cond
        )
        stmt = stmt.where(or_(product_cond, variant_ok.exists()))

    order_by = [CatalogBrand.name, CatalogProduct.name, CatalogProduct.id]
    normalized = normalize_text(q or "")
    if normalized:
        tokens = normalized.split()[:MAX_QUERY_TOKENS]
        token_match = and_(
            *(
                CatalogProduct.search_text.like(f"%{_escape_like(token)}%", escape="\\")
                for token in tokens
            )
        )
        exact = stmt.where(token_match)
        has_exact = session.scalar(select(exact.order_by(None).exists()))
        if has_exact or session.get_bind().dialect.name != "postgresql":
            stmt = exact
        else:
            # No product contains every query token: fall back to trigram
            # similarity so typos ("guardain", "therma rest") still find
            # something, without polluting exact results with near-misses.
            similarity = func.extensions.word_similarity(
                literal(normalized), CatalogProduct.search_text
            )
            stmt = stmt.where(similarity >= TYPO_SIMILARITY_THRESHOLD)
            order_by = [similarity.desc(), *order_by]

    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    ids = session.scalars(stmt.order_by(*order_by).offset(offset).limit(limit)).all()

    products_by_id = {
        product.id: product
        for product in session.scalars(
            select(CatalogProduct)
            .where(CatalogProduct.id.in_(ids))
            .options(
                joinedload(CatalogProduct.brand),
                joinedload(CatalogProduct.category).joinedload(CatalogCategory.parent),
                selectinload(CatalogProduct.variants),
                selectinload(CatalogProduct.images),
            )
        ).unique()
    }
    products = [products_by_id[product_id] for product_id in ids if product_id in products_by_id]
    next_offset = offset + len(ids) if offset + len(ids) < total else None
    return SearchResult(products=products, total=total, next_offset=next_offset)
