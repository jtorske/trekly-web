"""Trail ↔ campground links: the table, the seed from the mapping file, and the API."""

import copy
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.backcountry import BackcountryPark, BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailBookingSystem, TrailCampground
from app.trail_campgrounds import MappingError, load_mapping, seed_trail_campgrounds

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

SYSTEMS = {
    "parks_canada": {"name": "Parks Canada", "url": "https://reservation.pc.gc.ca"},
    "bc_parks": {"name": "BC Parks", "url": None},
    "yukon_parks": {"name": "Yukon Parks", "url": None},
}


def add_trail(db, name, province="AB", nights=2):
    trail = Trail(name=name, region=f"Somewhere, {province}", country_code="CA", province_code=province,
                  terrain_difficulty="moderate", typical_duration_nights=nights)
    db.add(trail)
    db.flush()
    return trail


def add_site(db, park, resource_id, name, code=None, **overrides):
    values = dict(
        provider="parks_canada", provider_resource_id=resource_id, provider_location_id="-2147483638",
        provider_map_id="-2147483400", provider_booking_category_id="7", park_id=park.id,
        province_code="AB", booking_unit="Jasper - Backcountry", name=name, raw_name=name,
        site_code=code, kind="zone", reservable_capacity=8, max_capacity=6, is_publicly_listed=True,
        raw={}, last_synced_at=NOW,
    )
    values.update(overrides)
    site = BackcountrySite(**values)
    db.add(site)
    db.flush()
    return site


@pytest.fixture
def world(session_factory, client):
    """Trails and sites in the shared test database (the API client reads the same one)."""
    db = session_factory()
    park = BackcountryPark(provider="parks_canada", provider_park_id="1", name="Jasper", province_code="AB",
                           region="Western", last_synced_at=NOW)
    db.add(park)
    db.flush()
    skyline = add_trail(db, "Skyline Trail", "AB")
    add_trail(db, "Skyline Trail", "NS", nights=0)  # same name, other province: never linked
    add_trail(db, "Garibaldi Lake", "BC", nights=1)
    add_trail(db, "Bertha Lake", "AB", nights=0)
    add_trail(db, "Grizzly Lake", "YT", nights=2)
    sites = {
        "evelyn": add_site(db, park, "-1", "Evelyn Creek", "27"),
        "shovel": add_site(db, park, "-2", "Little Shovel", "28"),
        "snowbowl": add_site(db, park, "-3", "Snowbowl", "29"),
        "hidden": add_site(db, park, "-4", "Staff Zone", is_publicly_listed=False),
        "fh2": add_site(db, park, "-5", "FH2", "FH2", kind="site"),
        "fh1": add_site(db, park, "-6", "FH1", "FH1", kind="site"),
        "bertha": add_site(db, park, "-7", "Bertha Lake"),
    }
    db.commit()
    ids = {"skyline": skyline.id, **{k: v.id for k, v in sites.items()}}
    db.close()
    return ids


def mapping(**changes):
    data = {
        "booking_systems": copy.deepcopy(SYSTEMS),
        "trails": [
            {
                "name": "Skyline Trail", "province_code": "AB",
                "booking": [{"system": "parks_canada", "covers": "all"}],
                "campgrounds": [
                    {"resource_id": "-3", "name": "Snowbowl", "order": 3, "confidence": "exact"},
                    {"resource_id": "-1", "name": "Evelyn Creek", "order": 1, "confidence": "exact"},
                    {"resource_id": "-2", "name": "Little Shovel", "order": 2, "confidence": "likely",
                     "notes": "Order unverified."},
                    {"resource_id": "-4", "name": "Staff Zone", "order": 4, "confidence": "exact"},
                    {"resource_id": "-5", "name": "FH2", "stop": "Fish Harbour", "order": 5, "confidence": "exact"},
                    {"resource_id": "-6", "name": "FH1", "stop": "Fish Harbour", "order": 5, "confidence": "exact"},
                ],
            },
            {
                "name": "Garibaldi Lake", "province_code": "BC",
                "booking": [{"system": "bc_parks", "covers": "all", "note": "Garibaldi Lake campground."}],
                "campgrounds": [],
            },
            {
                "name": "Grizzly Lake", "province_code": "YT",
                "booking": [{"system": "yukon_parks", "covers": "all", "confirmed": False}],
                "campgrounds": [],
            },
            {
                "name": "Bertha Lake", "province_code": "AB", "overnight_option": True,
                "booking": [{"system": "parks_canada", "covers": "all"}],
                "campgrounds": [{"resource_id": "-7", "name": "Bertha Lake", "order": 1, "confidence": "exact"}],
            },
        ],
    }
    data.update(changes)
    return data


def seed(session_factory, data):
    db = session_factory()
    report = seed_trail_campgrounds(db, data, source="test")
    db.commit()
    db.close()
    return report


def snapshot(session_factory):
    db = session_factory()
    links = sorted(
        (str(l.trail_id), str(l.site_id), l.route_order, l.stop_name, l.notes, l.confidence, l.updated_at)
        for l in db.scalars(select(TrailCampground))
    )
    bookings = sorted(
        (str(b.trail_id), b.system, b.covers, b.confirmed, b.note, b.position, b.updated_at)
        for b in db.scalars(select(TrailBookingSystem))
    )
    db.close()
    return links, bookings


# ---------------------------------------------------------------- link table


def test_route_order_and_confidence_are_checked(session_factory, world):
    db = session_factory()
    db.add(TrailCampground(trail_id=world["skyline"], site_id=world["evelyn"], route_order=0,
                           confidence="exact", source="test"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(TrailCampground(trail_id=world["skyline"], site_id=world["evelyn"], route_order=1,
                           confidence="maybe", source="test"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.close()


def test_a_site_is_linked_to_a_trail_once(session_factory, world):
    db = session_factory()
    for _ in range(2):
        db.add(TrailCampground(trail_id=world["skyline"], site_id=world["evelyn"], route_order=1,
                               confidence="exact", source="test"))
    with pytest.raises(Exception):  # identity conflict in the session or a PK violation
        db.flush()
    db.close()


def test_linked_sites_cannot_be_deleted(session_factory, world):
    seed(session_factory, mapping())
    db = session_factory()
    db.delete(db.get(BackcountrySite, world["evelyn"]))
    with pytest.raises(IntegrityError):
        db.flush()
    db.close()


# ---------------------------------------------------------------- mapping validation


def test_the_checked_in_mapping_is_valid():
    data = load_mapping()
    assert data["trails"], "mapping file has no trails"
    for system in data["booking_systems"].values():
        if system is not data["booking_systems"]["parks_canada"]:
            assert system["url"] is None, "non-Parks Canada URLs stay empty until verified"


@pytest.mark.parametrize(
    "breakage, message",
    [
        (lambda d: d["trails"][0]["booking"].__setitem__(0, {"system": "nope", "covers": "all"}), "unknown booking system"),
        (lambda d: d["trails"][0]["campgrounds"][0].__setitem__("confidence", "maybe"), "confidence"),
        (lambda d: d["trails"][0]["campgrounds"][0].__setitem__("order", 0), "order"),
        (lambda d: d["trails"][0]["campgrounds"].append(dict(d["trails"][0]["campgrounds"][0])), "listed twice"),
        (lambda d: d["trails"].append(copy.deepcopy(d["trails"][1])), "listed twice"),
    ],
)
def test_invalid_mappings_are_rejected_before_writing(session_factory, world, breakage, message):
    data = mapping()
    breakage(data)
    db = session_factory()
    with pytest.raises(MappingError, match=message):
        seed_trail_campgrounds(db, data)
    assert db.scalar(select(func.count()).select_from(TrailCampground)) == 0
    db.close()


# ---------------------------------------------------------------- seed


def test_seed_creates_links_and_booking_systems(session_factory, world):
    report = seed(session_factory, mapping())
    assert (report.links_created, report.booking_created) == (7, 4)
    assert any("Staff Zone is not publicly listed" in w for w in report.warnings)
    db = session_factory()
    link = db.get(TrailCampground, (world["skyline"], world["shovel"]))
    assert (link.route_order, link.confidence, link.notes, link.source) == (2, "likely", "Order unverified.", "test")
    assert db.get(TrailCampground, (world["skyline"], world["fh1"])).stop_name == "Fish Harbour"
    db.close()


def test_seed_is_idempotent(session_factory, world):
    seed(session_factory, mapping())
    before = snapshot(session_factory)
    report = seed(session_factory, mapping())
    assert (report.links_created, report.links_updated, report.links_unchanged) == (0, 0, 7)
    assert (report.booking_created, report.booking_updated, report.booking_unchanged) == (0, 0, 4)
    assert not report.links_removed and not report.booking_removed
    assert snapshot(session_factory) == before


def test_seed_updates_changed_links_in_place(session_factory, world):
    seed(session_factory, mapping())
    data = mapping()
    data["trails"][0]["campgrounds"][2]["confidence"] = "exact"
    report = seed(session_factory, data)
    assert (report.links_updated, report.links_unchanged) == (1, 6)
    db = session_factory()
    assert db.get(TrailCampground, (world["skyline"], world["shovel"])).confidence == "exact"
    db.close()


def test_links_to_retired_sites_are_kept_and_reported(session_factory, world):
    seed(session_factory, mapping())
    db = session_factory()
    db.get(BackcountrySite, world["snowbowl"]).retired_at = NOW
    db.commit()
    db.close()
    report = seed(session_factory, mapping())
    assert report.retired_links == ["Skyline Trail (AB): Snowbowl (-3)"]
    assert not report.links_removed
    db = session_factory()
    assert db.get(TrailCampground, (world["skyline"], world["snowbowl"])) is not None
    db.close()


def test_links_taken_out_of_the_file_are_removed(session_factory, world):
    seed(session_factory, mapping())
    data = mapping()
    del data["trails"][0]["campgrounds"][0]  # Snowbowl
    data["trails"] = [t for t in data["trails"] if t["name"] != "Garibaldi Lake"]
    report = seed(session_factory, data)
    assert report.links_removed == ["Skyline Trail (AB): Snowbowl"]
    assert report.booking_removed == ["Garibaldi Lake (BC): bc_parks"]


def test_an_unresolvable_site_leaves_that_trail_alone(session_factory, world):
    seed(session_factory, mapping())
    data = mapping()
    data["trails"][0]["campgrounds"] = [{"resource_id": "-999", "name": "Ghost", "order": 1, "confidence": "exact"}]
    report = seed(session_factory, data)
    assert any("-999" in w for w in report.warnings)
    assert not report.links_removed
    db = session_factory()
    assert db.scalar(select(func.count()).select_from(TrailCampground)
                     .where(TrailCampground.trail_id == world["skyline"])) == 6
    db.close()


def test_unknown_trails_are_skipped_with_a_warning(session_factory, world):
    data = mapping()
    data["trails"].append({"name": "Nowhere Trail", "province_code": "AB",
                           "booking": [{"system": "parks_canada", "covers": "all"}], "campgrounds": []})
    report = seed(session_factory, data)
    assert "Nowhere Trail (AB): no such trail; skipped" in report.warnings


def test_trails_are_matched_on_name_and_province(session_factory, world):
    seed(session_factory, mapping())
    db = session_factory()
    ns = db.scalar(select(Trail).where(Trail.name == "Skyline Trail", Trail.province_code == "NS"))
    assert db.scalar(select(func.count()).select_from(TrailCampground)
                     .where(TrailCampground.trail_id == ns.id)) == 0
    db.close()


# ---------------------------------------------------------------- API


def trail_id(session_factory, name, province):
    db = session_factory()
    found = db.scalar(select(Trail.id).where(Trail.name == name, Trail.province_code == province))
    db.close()
    return found


def test_api_returns_campgrounds_in_route_order_without_unlisted_sites(client, session_factory, world):
    seed(session_factory, mapping())
    body = client.get(f"/api/trails/{world['skyline']}/campgrounds").json()
    assert [c["name"] for c in body["campgrounds"]] == ["Evelyn Creek", "Little Shovel", "Snowbowl", "FH1", "FH2"]
    assert body["trip_type"] == "overnight"
    assert body["overnight_option"] is False
    assert body["route_order_approximate"] is True  # Little Shovel is 'likely'
    first = body["campgrounds"][0]
    assert first["park"] == {"name": "Jasper", "province_code": "AB"}
    assert (first["site_code"], first["kind"], first["reservable_capacity"], first["max_capacity"]) == ("27", "zone", 8, 6)
    assert first["retired"] is False
    # One booking form per park and booking type, never per campground.
    assert body["booking_links"] == [{
        "label": "Book Jasper backcountry on Parks Canada",
        "url": "https://reservation.pc.gc.ca/create-booking/results"
               "?resourceLocationId=-2147483638&mapId=-2147483400&bookingCategoryId=7",
    }]
    assert body["booking"] == [{"system": "parks_canada", "name": "Parks Canada", "url": "https://reservation.pc.gc.ca",
                                "covers": "all", "confirmed": True, "note": None}]


def test_api_flags_retired_sites(client, session_factory, world):
    seed(session_factory, mapping())
    db = session_factory()
    db.get(BackcountrySite, world["snowbowl"]).retired_at = NOW
    db.commit()
    db.close()
    body = client.get(f"/api/trails/{world['skyline']}/campgrounds").json()
    snowbowl = next(c for c in body["campgrounds"] if c["name"] == "Snowbowl")
    assert snowbowl["retired"] is True


def test_api_booked_elsewhere_and_unconfirmed_systems(client, session_factory, world):
    seed(session_factory, mapping())
    garibaldi = client.get(f"/api/trails/{trail_id(session_factory, 'Garibaldi Lake', 'BC')}/campgrounds").json()
    assert garibaldi["campgrounds"] == []
    assert garibaldi["booking"] == [{"system": "bc_parks", "name": "BC Parks", "url": None, "covers": "all",
                                     "confirmed": True, "note": "Garibaldi Lake campground."}]
    grizzly = client.get(f"/api/trails/{trail_id(session_factory, 'Grizzly Lake', 'YT')}/campgrounds").json()
    assert grizzly["booking"][0]["name"] is None and grizzly["booking"][0]["confirmed"] is False


def test_api_day_hike_with_campgrounds_is_an_overnight_option(client, session_factory, world):
    seed(session_factory, mapping())
    body = client.get(f"/api/trails/{trail_id(session_factory, 'Bertha Lake', 'AB')}/campgrounds").json()
    assert (body["trip_type"], body["overnight_option"]) == ("day", True)
    assert [c["name"] for c in body["campgrounds"]] == ["Bertha Lake"]


def test_api_day_hike_without_links_is_empty(client, session_factory, world):
    body = client.get(f"/api/trails/{trail_id(session_factory, 'Skyline Trail', 'NS')}/campgrounds").json()
    assert body == {"trail_id": body["trail_id"], "trip_type": "day", "overnight_option": False,
                    "route_order_approximate": False, "booking": [], "booking_links": [], "campgrounds": []}


def test_api_unknown_trail_is_404(client, world):
    assert client.get(f"/api/trails/{uuid.uuid4()}/campgrounds").status_code == 404


def test_booking_links_group_by_location_and_category(client, session_factory, world):
    data = mapping()
    db = session_factory()
    park = db.scalar(select(BackcountryPark))
    add_site(db, park, "-8", "Pachena Bay (North)", kind="trail_permit", provider_location_id="-50",
             provider_map_id="-51", provider_booking_category_id="4")
    add_site(db, park, "-9", "Gone", provider_location_id="-60", provider_map_id="-61", retired_at=NOW)
    db.commit()
    db.close()
    data["trails"][0]["campgrounds"] += [
        {"resource_id": "-8", "name": "Pachena Bay (North)", "order": 6, "confidence": "exact"},
        {"resource_id": "-9", "name": "Gone", "order": 7, "confidence": "exact"},
    ]
    seed(session_factory, data)
    links = client.get(f"/api/trails/{world['skyline']}/campgrounds").json()["booking_links"]
    # Five Jasper zones and pads share one form; the permit gets its own; the retired site none.
    assert [l["label"] for l in links] == ["Book Jasper backcountry on Parks Canada", "Book the trail permit on Parks Canada"]
    assert links[1]["url"].endswith("?resourceLocationId=-50&mapId=-51&bookingCategoryId=4")
