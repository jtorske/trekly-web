"""Parks Canada backcountry catalogue: parsing, filtering and the upsert/retire sync.

tests/fixtures/parks_canada_catalog.json holds trimmed real responses from
reservation.pc.gc.ca (captured 2026-10-15), keyed by API path. No test makes a
network call.
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.backcountry import parks_canada as pc
from app.backcountry.sync import coverage, sync_catalog
from app.database import Base
from app.models.backcountry import BackcountryPark, BackcountrySite

FIXTURE = Path(__file__).parent / "fixtures" / "parks_canada_catalog.json"
OVERRIDES = Path(__file__).resolve().parents[1] / "catalog_data" / "backcountry_park_overrides.json"
BKY_RESOURCES = "resourcelocation/resources?resourceLocationId=-2147483638"
NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


class FixtureApi:
    def __init__(self, responses):
        self.responses = responses
        self.requested = []
        self.fail = set()

    def get(self, path):
        self.requested.append(path)
        if path in self.fail:
            raise RuntimeError("HTTP 503")
        if path not in self.responses:
            raise AssertionError(f"unexpected request: {path}")
        return copy.deepcopy(self.responses[path])


@pytest.fixture
def api():
    return FixtureApi(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def overrides():
    return pc.load_overrides(OVERRIDES)


@pytest.fixture
def db(engine, session_factory):
    Base.metadata.create_all(
        engine, tables=[BackcountryPark.__table__, BackcountrySite.__table__]
    )
    session = session_factory()
    yield session
    session.close()


def build(api, overrides):
    return pc.build_catalog(api.get, park_overrides=overrides, log=lambda _: None)


def by_name(catalog):
    return {site.raw_name: site for site in catalog.sites}


def park_of(catalog, site):
    return catalog.parks[site.park_id].name if site.park_id else None


# ---------------------------------------------------------------- hierarchy parsing


def test_parks_and_provinces_come_from_the_org_tree_and_park_offices(api, overrides):
    catalog = build(api, overrides)
    parks = {p.name: (p.province_code, p.region) for p in catalog.parks.values()}

    assert parks == {
        "Banff": ("AB", "Western"),
        "Kootenay": ("BC", "Western"),
        "Yoho": ("BC", "Western"),
        "Jasper": ("AB", "Western"),
        "Kluane": ("YT", "Western"),
        "Pacific Rim": ("BC", "Western"),
        "Bruce Peninsula": ("ON", "Central"),
    }


def test_site_names_codes_areas_and_capacity(api, overrides):
    sites = by_name(build(api, overrides))

    banff = sites["Allenby Junction - Br17"]
    assert (banff.name, banff.site_code, banff.kind) == ("Allenby Junction", "Br17", "zone")
    assert (banff.reservable_capacity, banff.max_capacity, banff.max_group_size) == (5, 5, 10)
    assert banff.provider_location_id == "-2147483638"
    assert banff.provider_map_id == "-2147483589"
    assert banff.provider_booking_category_id == "7"

    jasper = sites["70 - Blue Creek"]
    assert (jasper.name, jasper.site_code) == ("Blue Creek", "70")
    assert jasper.area == "North Boundary and Celestine Lake"

    pad = sites["HD1"]
    assert (pad.name, pad.site_code, pad.kind, pad.province_code) == ("HD1", "HD1", "site", "ON")
    assert pad.provider_booking_category_id == "5"

    assert sites["Floe Lake"].site_code is None
    assert all(s.latitude is None and s.longitude is None for s in sites.values())


def test_shared_banff_kootenay_yoho_unit_is_split_into_parks(api, overrides):
    catalog = build(api, overrides)
    sites = by_name(catalog)

    assert park_of(catalog, sites["Allenby Junction - Br17"]) == "Banff"  # coded -> Banff
    assert park_of(catalog, sites["Bryant Random"]) == "Banff"  # "Banff Random Camping" map
    assert park_of(catalog, sites["Rockwall Random"]) == "Kootenay"  # "Kootenay Random Camping" map
    assert park_of(catalog, sites["Floe Lake"]) == "Kootenay"  # override file
    assert park_of(catalog, sites["Laughing Falls"]) == "Yoho"  # override file
    assert sites["Laughing Falls"].province_code == "BC"
    assert sites["Bryant Random"].area == "Banff Random Camping"
    # No park signal at all: left empty (and reported), never guessed.
    grazing = sites["Brewster Creek Grazing"]
    assert (grazing.kind, grazing.park_id, grazing.province_code) == ("horse_camp", None, None)


def test_override_name_drift_is_warned(api, overrides):
    overrides = dict(overrides)
    overrides["-2147483103"] = {"name": "Floe Lake Campground", "park": "Kootenay"}

    catalog = build(api, overrides)

    assert any("Floe Lake Campground" in w for w in catalog.warnings)
    assert park_of(catalog, by_name(catalog)["Floe Lake"]) == "Kootenay"


# ---------------------------------------------------------------- backcountry-only filtering


def test_only_backcountry_locations_are_fetched(api, overrides):
    build(api, overrides)

    per_location = [p for p in api.requested if "resourceLocationId=" in p]
    fetched = {p.split("=")[1] for p in per_location}
    assert fetched == {"-2147483638", "-2147483592", "-2147483635", "-2147483562", "-2147483586"}
    # Frontcountry campgrounds (Banff Tunnel Mountain, Kootenay Redstreak, ...) never requested.
    assert not any("-2147483646" in p or "-2147483582" in p for p in per_location)
    assert not any(p.startswith("availability") for p in api.requested)


def test_trailheads_out_of_park_and_frontcountry_resources_are_dropped(api, overrides):
    catalog = build(api, overrides)
    names = set(by_name(catalog))

    assert "Emerald Lake Trailhead" not in names
    assert "Peter Lougheed Provincial Park (Out of Park)" not in names
    assert "Hamber (Out Of Park)" not in names
    assert "Out of Park - North" not in names
    assert "O1" not in names  # Kluane frontcountry campsite in a mixed location
    assert catalog.excluded == {"trailhead": 2, "out_of_park": 3}
    assert all(s.resource_model != pc.TRAILHEAD_MODEL for s in catalog.sites)


def test_kinds_and_public_listing(api, overrides):
    sites = by_name(build(api, overrides))

    assert sites["Gordon River (South)"].kind == "trail_permit"
    assert sites["Gordon River (South)"].provider_booking_category_id == "4"
    assert sites["Egypt Lake Shelter"].kind == "shelter"
    assert sites["Bryant Random"].kind == "random_zone"
    # Kluane's zones sit on maps the provider doesn't publish.
    assert sites["Bighorn Lake"].is_publicly_listed is False
    assert sites["Egypt Lake Shelter"].is_publicly_listed is False  # no map at all
    assert sites["Allenby Junction - Br17"].is_publicly_listed is True


# ---------------------------------------------------------------- sync: idempotent upsert


def test_sync_is_idempotent(api, overrides, db):
    first = sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()
    total = db.scalar(select(func.count()).select_from(BackcountrySite))
    assert first.created == total == 15
    assert first.parks_created == 7

    later = NOW + timedelta(days=1)
    second = sync_catalog(db, pc.PROVIDER, build(api, overrides), later)
    db.commit()

    assert (second.created, second.updated, second.retired, second.restored) == (0, 0, 0, 0)
    assert second.unchanged == total
    assert second.parks_created == 0
    assert db.scalar(select(func.count()).select_from(BackcountrySite)) == total
    assert db.scalar(select(func.count()).select_from(BackcountryPark)) == 7
    assert all(s.last_synced_at.replace(tzinfo=timezone.utc) == later for s in db.scalars(select(BackcountrySite)))


def test_sync_updates_changed_fields_in_place(api, overrides, db):
    sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()
    original_id = db.scalar(select(BackcountrySite.id).where(BackcountrySite.site_code == "Br17"))

    resource = api.responses[BKY_RESOURCES]["-2147483046"]
    resource["localizedValues"][0]["name"] = "Allenby Jct - Br17"
    resource["zoneCapacitySettings"]["capacity"] = 6
    report = sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()

    site = db.get(BackcountrySite, original_id)
    assert report.updated == 1
    assert (site.name, site.reservable_capacity) == ("Allenby Jct", 6)


# ---------------------------------------------------------------- sync: retiring


def test_removed_site_is_retired_then_restored(api, overrides, db):
    sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()

    floe = api.responses[BKY_RESOURCES].pop("-2147483103")
    removed_at = NOW + timedelta(days=1)
    report = sync_catalog(db, pc.PROVIDER, build(api, overrides), removed_at)
    db.commit()

    site = db.scalar(select(BackcountrySite).where(BackcountrySite.provider_resource_id == "-2147483103"))
    assert report.retired == 1
    assert site.retired_at.replace(tzinfo=timezone.utc) == removed_at  # kept, not deleted
    assert db.scalar(select(func.count()).select_from(BackcountrySite)) == 15

    api.responses[BKY_RESOURCES]["-2147483103"] = floe
    report = sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW + timedelta(days=2))
    db.commit()

    assert report.restored == 1
    assert db.get(BackcountrySite, site.id).retired_at is None


def test_failed_location_does_not_retire_its_sites(api, overrides, db):
    sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()

    api.fail.add("resourcelocation/resources?resourceLocationId=-2147483635")  # Bruce Peninsula
    catalog = build(api, overrides)
    report = sync_catalog(db, pc.PROVIDER, catalog, NOW + timedelta(days=1))
    db.commit()

    assert not catalog.complete
    assert report.retired == 0
    assert "incomplete run" in report.retire_skipped_reason
    assert db.scalar(
        select(func.count()).select_from(BackcountrySite).where(BackcountrySite.retired_at.is_not(None))
    ) == 0


def test_mass_retire_needs_explicit_flag(api, overrides, db):
    sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()
    api.responses[BKY_RESOURCES] = {}  # 8 of 15 rows vanish

    guarded = sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW + timedelta(days=1))
    assert guarded.retired == 0 and "would be retired" in guarded.retire_skipped_reason
    db.rollback()

    allowed = sync_catalog(
        db, pc.PROVIDER, build(api, overrides), NOW + timedelta(days=1), allow_mass_retire=True
    )
    db.commit()
    assert allowed.retired == 8  # every Banff/Kootenay/Yoho row
    assert allowed.parks_retired == 3
    active_parks = select(BackcountryPark.name).where(BackcountryPark.retired_at.is_(None))
    assert set(db.scalars(active_parks)) == {"Jasper", "Kluane", "Pacific Rim", "Bruce Peninsula"}


def test_coverage_reports_gaps(api, overrides, db):
    sync_catalog(db, pc.PROVIDER, build(api, overrides), NOW)
    db.commit()

    stats = coverage(db, pc.PROVIDER)

    assert stats["total"] == 15
    assert stats["gaps"]["no_coordinates"] == 15
    assert [name for _, name, _ in stats["gaps"]["no_park"]] == ["Brewster Creek Grazing"]
    assert stats["per_park"]["Kootenay"] == 3  # Floe Lake, Verdant Creek, Rockwall Random
