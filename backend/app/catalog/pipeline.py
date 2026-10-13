"""Catalogue ingestion: validate, normalize, deduplicate and upsert.

Idempotency rules
- Taxonomy is upserted by slug.
- Brands resolve by normalized name or any normalized alias, so "MSR",
  "msr" and "Mountain Safety Research" (once aliased) are one brand.
- A product is matched first by its stable (source, source_record_id) link,
  then by (brand, slug). Re-importing an unchanged record is a no-op
  ("unchanged"); a changed record updates the same rows ("updated").
- Variants match by (product, slug); images by (product, url).
- Nothing is deleted. Products, variants and images missing from a feed are
  left alone; retiring a product is explicit (status "discontinued"), so user
  inventory that references it keeps working.

Each record is applied inside a SAVEPOINT, so one bad record is reported and
skipped without aborting the rest of the run.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.normalize import build_search_text, normalize_text, slugify
from app.catalog.providers.base import CatalogProvider, SourceInfo
from app.catalog.records import CatalogRecord, NormalizedRecord, normalize_record
from app.catalog.taxonomy import TAXONOMY
from app.models.catalog import (
    CatalogBrand,
    CatalogBrandAlias,
    CatalogCategory,
    CatalogIngestionRun,
    CatalogProduct,
    CatalogProductAlias,
    CatalogProductImage,
    CatalogProductSource,
    CatalogProductVariant,
    CatalogSource,
)


@dataclass
class RunReport:
    source: str
    dry_run: bool
    run_id: str | None = None
    status: str = "running"
    counts: Counter = field(default_factory=Counter)
    errors: list[dict] = field(default_factory=list)

    def error(self, record_id: str | None, message: str) -> None:
        self.errors.append({"record": record_id or "<unknown>", "message": message})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sync_taxonomy(session: Session) -> Counter:
    changes: Counter = Counter()
    existing = {c.slug: c for c in session.scalars(select(CatalogCategory))}

    def upsert(slug, name, icon_key, sort_order, parent=None, description=None):
        category = existing.get(slug)
        if category is None:
            category = CatalogCategory(slug=slug)
            session.add(category)
            existing[slug] = category
            changes["created"] += 1
        fields = {
            "name": name,
            "icon_key": icon_key,
            "sort_order": sort_order,
            "parent": parent,
            "description": description,
        }
        if any(getattr(category, key) != value for key, value in fields.items()):
            for key, value in fields.items():
                setattr(category, key, value)
            changes["updated"] += 1
        return category

    for top_index, top in enumerate(TAXONOMY):
        parent = upsert(top.slug, top.name, top.icon_key, top_index, description=top.description)
        for sub_index, sub in enumerate(top.subcategories):
            upsert(sub.slug, sub.name, sub.icon_key, sub_index, parent=parent)
    session.flush()
    return changes


def ensure_source(session: Session, info: SourceInfo) -> CatalogSource:
    source = session.scalar(select(CatalogSource).where(CatalogSource.slug == info.slug))
    if source is None:
        source = CatalogSource(slug=info.slug)
        session.add(source)
    source.name = info.name
    source.kind = info.kind
    source.homepage_url = info.homepage_url
    source.terms_url = info.terms_url
    source.terms_notes = info.terms_notes
    session.flush()
    return source


def resolve_brand(
    session: Session, name: str, aliases: list[str], website: str | None
) -> CatalogBrand:
    # The record's brand name decides the brand; aliases only add spellings.
    # An alias that already points at a *different* brand is a data error,
    # never a silent re-brand.
    brand = session.scalar(
        select(CatalogBrand)
        .join(CatalogBrandAlias)
        .where(CatalogBrandAlias.alias_normalized == normalize_text(name))
    ) or session.scalar(select(CatalogBrand).where(CatalogBrand.slug == slugify(name)))
    if brand is None:
        brand = CatalogBrand(slug=slugify(name), name=name, website_url=website)
        session.add(brand)
        session.flush()
    elif website and not brand.website_url:
        brand.website_url = website

    known = {alias.alias_normalized for alias in brand.aliases}
    for alias in [name, *aliases]:
        normalized = normalize_text(alias)
        if normalized in known:
            continue
        clash = session.scalar(
            select(CatalogBrandAlias).where(CatalogBrandAlias.alias_normalized == normalized)
        )
        if clash is not None:
            raise ValueError(
                f"brand alias '{alias}' already belongs to another brand ({clash.brand.name})"
            )
        brand.aliases.append(CatalogBrandAlias(alias=alias, alias_normalized=normalized))
        known.add(normalized)
    return brand


def _verified_datetime(record: CatalogRecord) -> datetime:
    return datetime.combine(record.verified_at, time(12, 0), tzinfo=timezone.utc)


def _apply_product_fields(
    session: Session,
    product: CatalogProduct,
    normalized: NormalizedRecord,
    brand: CatalogBrand,
    category: CatalogCategory,
) -> None:
    record = normalized.record
    product.brand = brand
    product.category = category
    product.name = record.name
    if product.slug != normalized.product_slug:
        clash = session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.brand_id == brand.id,
                CatalogProduct.slug == normalized.product_slug,
                CatalogProduct.id != product.id,
            )
        )
        if clash is None:
            product.slug = normalized.product_slug
    product.model_number = record.model_number
    product.model_year = record.model_year
    if record.status == "discontinued" and product.status != "discontinued":
        product.discontinued_at = _now()
    elif record.status == "active":
        product.discontinued_at = None
    product.status = record.status
    product.weight_g = normalized.weight_g
    product.weight_basis = normalized.weight_basis
    product.capacity_ml = normalized.capacity_ml
    product.specs = normalized.specs
    product.official_url = record.official_url
    product.verified_at = _verified_datetime(record)

    known_aliases = {alias.alias_normalized for alias in product.aliases}
    for alias in record.aliases:
        normalized_alias = normalize_text(alias)
        if normalized_alias and normalized_alias not in known_aliases:
            product.aliases.append(
                CatalogProductAlias(alias=alias, alias_normalized=normalized_alias)
            )
            known_aliases.add(normalized_alias)

    variants = {variant.slug: variant for variant in product.variants}
    for incoming in normalized.variants:
        variant = variants.get(incoming.slug)
        if variant is None:
            variant = CatalogProductVariant(slug=incoming.slug)
            product.variants.append(variant)
        variant.name = incoming.name
        variant.sku = incoming.sku
        variant.status = incoming.status
        variant.sort_order = incoming.sort_order
        variant.weight_g = incoming.weight_g
        variant.weight_basis = incoming.weight_basis
        variant.capacity_ml = incoming.capacity_ml
        variant.specs = incoming.specs

    images = {image.url: image for image in product.images}
    for incoming in record.images:
        image = images.get(incoming.url)
        if image is None:
            image = CatalogProductImage(url=incoming.url)
            product.images.append(image)
        image.alt_text = incoming.alt_text
        image.license = incoming.license
        image.attribution = incoming.attribution
        image.source_url = incoming.source_url
        image.approved = incoming.approved

    product.search_text = build_search_text(
        brand.name,
        *(alias.alias for alias in brand.aliases),
        record.name,
        *(alias.alias for alias in product.aliases),
        record.model_number,
        category.name,
        category.parent.name if category.parent else None,
        *(variant.name for variant in product.variants),
    )


def upsert_record(
    session: Session,
    source: CatalogSource,
    run: CatalogIngestionRun,
    normalized: NormalizedRecord,
    categories: dict[str, CatalogCategory],
) -> str:
    record = normalized.record
    brand = resolve_brand(session, record.brand, record.brand_aliases, record.brand_website)
    category = categories[record.category]

    link = session.scalar(
        select(CatalogProductSource).where(
            CatalogProductSource.source_id == source.id,
            CatalogProductSource.source_record_id == record.source_record_id,
        )
    )
    if link is not None and link.content_hash == normalized.content_hash:
        link.last_seen_run_id = run.id
        return "unchanged"

    product = link.product if link is not None else None
    outcome = "updated"
    if product is None:
        product = session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.brand_id == brand.id,
                CatalogProduct.slug == normalized.product_slug,
            )
        )
        if product is None:
            product = CatalogProduct(slug=normalized.product_slug)
            session.add(product)
            outcome = "created"
        else:
            # The same product arrived under a new record id or from another
            # source: link it rather than duplicating it.
            outcome = "merged"

    _apply_product_fields(session, product, normalized, brand, category)

    if link is None:
        link = CatalogProductSource(source=source, source_record_id=record.source_record_id)
        product.sources.append(link)
    link.source_url = record.source_url
    link.verified_at = _verified_datetime(record)
    link.content_hash = normalized.content_hash
    link.last_seen_run_id = run.id
    session.flush()
    return outcome


def run_import(session: Session, provider: CatalogProvider, dry_run: bool = False) -> RunReport:
    report = RunReport(source=provider.source.slug, dry_run=dry_run)
    sync_taxonomy(session)
    source = ensure_source(session, provider.source)
    run = CatalogIngestionRun(source=source, dry_run=dry_run, status="running")
    session.add(run)
    session.flush()
    report.run_id = str(run.id)

    categories = {c.slug: c for c in session.scalars(select(CatalogCategory))}
    seen: set[str] = set()

    try:
        for raw in provider.records():
            record_id = raw.get("source_record_id") if isinstance(raw, dict) else None
            try:
                record = CatalogRecord.model_validate(raw)
                normalized = normalize_record(record)
            except (ValidationError, ValueError) as error:
                report.counts["invalid"] += 1
                report.error(record_id, _describe(error))
                continue

            if record.source_record_id in seen:
                report.counts["duplicate_in_feed"] += 1
                report.error(record.source_record_id, "appears more than once in this feed")
                continue
            seen.add(record.source_record_id)

            savepoint = session.begin_nested()
            try:
                outcome = upsert_record(session, source, run, normalized, categories)
                savepoint.commit()
                report.counts[outcome] += 1
            except Exception as error:  # noqa: BLE001 — report and continue
                savepoint.rollback()
                report.counts["failed"] += 1
                report.error(record.source_record_id, str(error))
    except Exception as error:  # provider-level failure (e.g. unreadable feed)
        report.status = "failed"
        report.error(None, f"provider failed: {error}")

    if report.status != "failed":
        report.status = "partial" if report.errors else "succeeded"
    run.status = report.status
    run.finished_at = _now()
    run.counts = dict(report.counts)
    run.errors = report.errors[:500]

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return report


def _describe(error: Exception) -> str:
    if isinstance(error, ValidationError):
        parts = []
        for item in error.errors():
            location = ".".join(str(piece) for piece in item["loc"]) or "record"
            parts.append(f"{location}: {item['msg']}")
        return "; ".join(parts)
    return str(error)
