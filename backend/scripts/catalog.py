"""Gear catalogue maintenance CLI.

Run from backend/:

    python scripts/catalog.py import                     # curated seed (default provider)
    python scripts/catalog.py import --dry-run           # validate + report, write nothing
    python scripts/catalog.py import --file path.json    # another curated JSON file
    python scripts/catalog.py import --csv feed.csv --source-slug acme-feed \\
        --source-name "Acme product feed" --source-kind licensed_feed
    python scripts/catalog.py coverage                   # products per category / brand
    python scripts/catalog.py retire <brand-slug>/<product-slug>

Imports are idempotent: re-running a feed updates the same rows and reports
unchanged records as such. Exit code is 1 if any record failed or was invalid.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from app.catalog.pipeline import run_import  # noqa: E402
from app.catalog.providers import CsvFeedProvider, CuratedJsonProvider, default_providers  # noqa: E402
from app.catalog.providers.base import SourceInfo  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.catalog import (  # noqa: E402
    CatalogBrand,
    CatalogCategory,
    CatalogProduct,
    CatalogProductImage,
)


def _provider(args):
    if args.file:
        return CuratedJsonProvider(args.file)
    if args.csv:
        if not (args.source_slug and args.source_name):
            sys.exit("--csv needs --source-slug and --source-name")
        return CsvFeedProvider(
            args.csv,
            SourceInfo(args.source_slug, args.source_name, args.source_kind, terms_notes=args.terms_notes),
        )
    providers = default_providers()
    if args.provider not in providers:
        sys.exit(f"Unknown provider '{args.provider}'. Known: {', '.join(providers)}")
    return providers[args.provider]


def cmd_import(args) -> int:
    provider = _provider(args)
    with SessionLocal() as session:
        report = run_import(session, provider, dry_run=args.dry_run)
    label = "DRY RUN — nothing written" if report.dry_run else f"run {report.run_id}"
    print(f"Source: {report.source} ({label})")
    print(f"Status: {report.status}")
    for key in ("created", "updated", "merged", "unchanged", "invalid", "duplicate_in_feed", "failed"):
        if report.counts.get(key):
            print(f"  {key:>18}: {report.counts[key]}")
    for error in report.errors[:50]:
        print(f"  ! {error['record']}: {error['message']}")
    if len(report.errors) > 50:
        print(f"  … {len(report.errors) - 50} more errors")
    return 0 if not report.errors else 1


def cmd_coverage(_args) -> int:
    with SessionLocal() as session:
        tops = session.scalars(
            select(CatalogCategory)
            .where(CatalogCategory.parent_id.is_(None))
            .order_by(CatalogCategory.sort_order)
        ).all()
        total = 0
        for top in tops:
            rows = session.execute(
                select(CatalogCategory.name, func.count(CatalogProduct.id))
                .join(CatalogProduct, CatalogProduct.category_id == CatalogCategory.id, isouter=True)
                .where(CatalogCategory.parent_id == top.id)
                .group_by(CatalogCategory.id, CatalogCategory.name, CatalogCategory.sort_order)
                .order_by(CatalogCategory.sort_order)
            ).all()
            top_count = sum(count for _, count in rows)
            total += top_count
            print(f"{top.name}: {top_count}")
            for name, count in rows:
                print(f"    {name}: {count}")
        brands = session.execute(
            select(CatalogBrand.name, func.count(CatalogProduct.id))
            .join(CatalogProduct)
            .group_by(CatalogBrand.id, CatalogBrand.name)
            .order_by(func.count(CatalogProduct.id).desc(), CatalogBrand.name)
        ).all()
        with_weight = session.scalar(
            select(func.count()).select_from(CatalogProduct).where(CatalogProduct.weight_g.is_not(None))
        )
        images = session.scalar(
            select(func.count()).select_from(CatalogProductImage).where(CatalogProductImage.approved)
        )
        discontinued = session.scalar(
            select(func.count()).select_from(CatalogProduct).where(CatalogProduct.status == "discontinued")
        )
        print(f"\nTotal products: {total} ({discontinued} discontinued)")
        print(f"Products with a product-level weight: {with_weight} (others may have per-variant weights)")
        print(f"Approved images: {images}")
        print(f"Brands ({len(brands)}): " + ", ".join(f"{name} ({count})" for name, count in brands))
    return 0


def cmd_retire(args) -> int:
    brand_slug, _, product_slug = args.product.partition("/")
    with SessionLocal() as session:
        product = session.scalar(
            select(CatalogProduct)
            .join(CatalogBrand)
            .where(CatalogBrand.slug == brand_slug, CatalogProduct.slug == product_slug)
        )
        if product is None:
            print(f"No product {args.product}")
            return 1
        product.status = "discontinued"
        product.discontinued_at = product.discontinued_at or datetime.now(timezone.utc)
        session.commit()
        print(f"Retired {product.brand.name} {product.name}. User inventory referencing it is unaffected.")
        print("Also set \"status\": \"discontinued\" in the source record, or the next import will reactivate it.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import or update catalogue records")
    imp.add_argument("--provider", default="curated")
    imp.add_argument("--file")
    imp.add_argument("--csv")
    imp.add_argument("--source-slug")
    imp.add_argument("--source-name")
    imp.add_argument("--source-kind", default="licensed_feed", choices=["manufacturer", "licensed_feed", "manual"])
    imp.add_argument("--terms-notes")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=cmd_import)

    sub.add_parser("coverage", help="Show catalogue coverage").set_defaults(func=cmd_coverage)

    retire = sub.add_parser("retire", help="Mark a product discontinued")
    retire.add_argument("product", help="<brand-slug>/<product-slug>")
    retire.set_defaults(func=cmd_retire)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
