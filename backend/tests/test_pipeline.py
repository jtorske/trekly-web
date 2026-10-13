import json
from decimal import Decimal

from sqlalchemy import func, select

from app.catalog.pipeline import run_import
from app.catalog.providers import CURATED_FILE, CuratedJsonProvider
from app.catalog.providers.base import SourceInfo
from app.catalog.providers.csv_feed import CsvFeedProvider
from app.catalog.taxonomy import ALL_SLUGS
from app.models.catalog import (
    CatalogBrand,
    CatalogCategory,
    CatalogIngestionRun,
    CatalogProduct,
    CatalogProductSource,
    CatalogProductVariant,
)
from tests.conftest import SAMPLE_RECORDS, StaticProvider, make_record


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_import_creates_normalized_records(db):
    report = run_import(db, StaticProvider(SAMPLE_RECORDS))
    assert report.status == "succeeded"
    assert report.counts["created"] == 4
    assert count(db, CatalogProduct) == 4
    assert count(db, CatalogBrand) == 4
    assert count(db, CatalogCategory) == len(ALL_SLUGS)

    tent = db.scalar(select(CatalogProduct).where(CatalogProduct.slug == "copper-spur-hv-ul2"))
    assert tent.weight_g == Decimal("1304.078")  # 2 lb 14 oz = 1304.07806 g
    assert tent.weight_basis == "minimum"
    assert tent.specs["published_weight"] == "2 lb 14 oz"
    assert "big agnes" in tent.search_text and "tents" in tent.search_text


def test_reimport_is_idempotent(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    snapshot = {p.id: (p.weight_g, p.updated_at) for p in db.scalars(select(CatalogProduct))}

    report = run_import(db, StaticProvider(SAMPLE_RECORDS))
    assert report.counts == {"unchanged": 4}
    assert count(db, CatalogProduct) == 4
    assert count(db, CatalogProductVariant) == 2
    assert count(db, CatalogProductSource) == 4
    assert {p.id: (p.weight_g, p.updated_at) for p in db.scalars(select(CatalogProduct))} == snapshot
    assert count(db, CatalogIngestionRun) == 2


def test_changed_record_updates_in_place(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    original_id = db.scalar(select(CatalogProduct.id).where(CatalogProduct.slug == "copper-spur-hv-ul2"))

    changed = [make_record(weight={"text": "3 lb 1 oz", "basis": "minimum"}, status="discontinued")]
    report = run_import(db, StaticProvider(changed))
    assert report.counts == {"updated": 1}
    tent = db.get(CatalogProduct, original_id)
    assert tent.weight_g == Decimal("1389.127")
    assert tent.status == "discontinued"
    assert tent.discontinued_at is not None
    assert count(db, CatalogProduct) == 4  # retired, not deleted or duplicated


def test_brand_aliases_prevent_duplicate_brands(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    record = make_record(
        source_record_id="test:arcteryx-atom",
        brand="ARCTERYX",
        name="Atom Hoody",
        category="insulation",
        specs={"insulation_type": "synthetic"},
    )
    report = run_import(db, StaticProvider([record]))
    assert report.counts == {"created": 1}
    assert db.scalar(select(func.count()).select_from(CatalogBrand).where(CatalogBrand.slug == "arcteryx")) == 1
    assert count(db, CatalogBrand) == 4


def test_same_product_from_second_source_is_merged(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    other = StaticProvider(
        [make_record(source_record_id="feed:12345", brand="Big Agnes", name="Copper Spur HV UL2")],
        slug="other-feed",
        kind="licensed_feed",
    )
    report = run_import(db, other)
    assert report.counts == {"merged": 1}
    assert count(db, CatalogProduct) == 4
    assert count(db, CatalogProductSource) == 5


def test_invalid_and_duplicate_records_are_reported_not_imported(db):
    records = [
        make_record(),
        make_record(),  # same source_record_id again
        make_record(source_record_id="test:bad-category", category="spaceships"),
        make_record(source_record_id="test:bad-spec", specs={"warp_factor": 9}),
        make_record(source_record_id="test:bad-weight", weight={"text": "light"}),
        make_record(source_record_id="test:future", verified_at="2999-01-01"),
        {"brand": "No id"},
    ]
    report = run_import(db, StaticProvider(records))
    assert report.status == "partial"
    assert report.counts["created"] == 1
    assert report.counts["duplicate_in_feed"] == 1
    assert report.counts["invalid"] == 5
    assert count(db, CatalogProduct) == 1
    messages = " ".join(error["message"] for error in report.errors)
    assert "spaceships" in messages and "warp_factor" in messages


def test_unknown_values_stay_unknown(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    jacket = db.scalar(select(CatalogProduct).where(CatalogProduct.slug == "beta-ar-jacket"))
    assert jacket.weight_g is None
    assert jacket.capacity_ml is None
    assert jacket.specs == {}


def test_dry_run_writes_nothing(db):
    report = run_import(db, StaticProvider(SAMPLE_RECORDS), dry_run=True)
    assert report.counts["created"] == 4
    assert count(db, CatalogProduct) == 0
    assert count(db, CatalogIngestionRun) == 0


def test_alias_clash_between_brands_is_an_error(db):
    run_import(db, StaticProvider(SAMPLE_RECORDS))
    record = make_record(
        source_record_id="test:clash", brand="Mystery Gear", brand_aliases=["MSR"], name="Thing"
    )
    report = run_import(db, StaticProvider([record]))
    assert report.counts == {"failed": 1}
    assert "already belongs" in report.errors[0]["message"]
    assert db.scalar(select(CatalogBrand).where(CatalogBrand.slug == "mystery-gear")) is None


def test_csv_feed_provider_groups_variants(tmp_path, db):
    feed = tmp_path / "feed.csv"
    feed.write_text(
        "record_id,brand,name,category,source_url,verified_at,variant_name,weight_text,weight_basis,spec:r_value,spec:pad_type\n"
        "feed:pad-1,Example Co,Cloud Pad,sleeping-pads,https://example.com/pad,2026-10-01,Regular,1 lb 1 oz,minimum,4.2,air\n"
        "feed:pad-1,Example Co,Cloud Pad,sleeping-pads,https://example.com/pad,2026-10-01,Long,1 lb 4 oz,minimum,4.2,air\n"
        "feed:lamp-1,Example Co,Glow 300,lighting,https://example.com/lamp,2026-10-01,,,,,\n",
        encoding="utf-8",
    )
    provider = CsvFeedProvider(feed, SourceInfo("example-feed", "Example feed", "licensed_feed"))
    records = list(provider.records())
    assert len(records) == 2
    assert [v["name"] for v in records[0]["variants"]] == ["Regular", "Long"]
    assert "weight" not in records[1]  # blank cells are unknown, not zero

    report = run_import(db, provider)
    assert report.status == "succeeded", report.errors
    pad = db.scalar(select(CatalogProduct).where(CatalogProduct.slug == "cloud-pad"))
    assert [v.weight_g for v in pad.variants] == [Decimal("481.942"), Decimal("566.990")]
    assert pad.variants[0].specs["r_value"] == 4.2


def test_curated_seed_file_is_valid(db):
    """The committed seed catalogue must import cleanly and be re-runnable."""
    provider = CuratedJsonProvider(CURATED_FILE)
    payload = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    for record in payload["records"]:
        assert record["source_url"].startswith("https://"), record["source_record_id"]
        assert record.get("verified_at"), record["source_record_id"]

    first = run_import(db, provider)
    assert first.status == "succeeded", first.errors[:5]
    assert first.counts["created"] + first.counts.get("merged", 0) == len(payload["records"])

    second = run_import(db, CuratedJsonProvider(CURATED_FILE))
    expected = {"unchanged": len(payload["records"])} if payload["records"] else {}
    assert dict(second.counts) == expected
