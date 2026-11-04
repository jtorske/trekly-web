"""Which campgrounds take alerts, the party-size limit, the newer campground
types against recorded responses, and that polling follows active alerts,
not the size of the catalogue. No test makes a network call."""

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.backcountry.alertable import UNLIMITED_QUOTA, alert_block, party_problem
from app.backcountry.availability import AvailabilityChecker, MapGroup, availability_request, parse_statuses, summarize
from app.models.backcountry import BackcountrySite
from app.models.trail_campground import TrailCampground
from tests.test_availability import (  # noqa: F401  (fixtures)
    PUKASKWA,
    SKYLINE,
    START,
    T0,
    Clock,
    FixtureFetch,
    Outbox,
    add_site,
    alert_body,
    fetch,
    make_alert,
    outbox,
    poll,
    user,
    world,
)

TYPES = json.loads((Path(__file__).parent / "fixtures" / "parks_canada_availability_types.json").read_text(encoding="utf-8"))
RECORDED = {k: v for k, v in TYPES.items() if k != "_comment"}
PARADISE_VALLEY = "-2147482971"
HECTOR_LAKE = "-2147483107"


def site(**values):
    defaults = dict(kind="zone", name="Camp", provider_resource_id="-1", reservable_capacity=5, max_group_size=None)
    return BackcountrySite(**{**defaults, **values})


# ---------------------------------------------------------------- the rules


@pytest.mark.parametrize(
    "values, blocked",
    [
        ({"kind": "zone"}, False),
        ({"kind": "site", "reservable_capacity": None}, False),
        ({"kind": "backpacking_campground"}, False),  # Chilkoot
        ({"kind": "random_zone", "reservable_capacity": 4}, False),  # Jasper random zones have real quotas
        ({"kind": "random_zone", "reservable_capacity": UNLIMITED_QUOTA}, True),  # never fills up
        ({"kind": "horse_camp"}, True),
        ({"kind": "trail_permit"}, True),  # a separate, later phase
        ({"kind": "cabin"}, True),  # not confirmed against an "available" response yet
        ({"kind": "shelter"}, True),
        ({"kind": "zone", "provider_resource_id": PARADISE_VALLEY}, True),  # in person or by phone only
        ({"kind": "zone", "provider_resource_id": HECTOR_LAKE}, True),
    ],
)
def test_which_campgrounds_take_alerts(values, blocked):
    reason = alert_block(site(**values))
    assert (reason is not None) == blocked
    if blocked:
        assert reason.endswith(".")


def test_party_size_limit():
    lake_ohara = site(name="Lake O'Hara Backcountry Sites", max_group_size=4)
    assert party_problem(lake_ohara, 4) is None
    assert party_problem(lake_ohara, 5) == "Lake O'Hara Backcountry Sites takes at most 4 people per booking."
    assert party_problem(site(name="Corral", max_group_size=1), 2) == "Corral takes at most 1 person per booking."
    assert party_problem(site(max_group_size=None), 12) is None


# ---------------------------------------------------------------- the API


@pytest.fixture
def more_sites(session_factory, world):
    """An unlimited random zone, a cabin and a 4-person site on the Skyline trail."""
    db = session_factory()
    park_id = db.get(BackcountrySite, world["evelyn"]).park_id
    park = type("P", (), {"id": park_id})
    rows = {
        "unlimited": add_site(db, park, "-9001", "Skyline Random", kind="random_zone", reservable_capacity=UNLIMITED_QUOTA),
        "cabin": add_site(db, park, "-9002", "Trail Cabin", kind="cabin"),
        "small": add_site(db, park, "-9003", "Small Camp", max_group_size=4),
    }
    for order, key in enumerate(rows, 10):
        db.add(TrailCampground(trail_id=world["trail"], site_id=rows[key].id, route_order=order,
                               confidence="exact", source="test"))
    db.commit()
    ids = {k: v.id for k, v in rows.items()}
    db.close()
    return {**world, **ids}


def test_trail_campgrounds_say_which_take_alerts(client, more_sites, fetch):
    body = client.get(f"/api/trails/{more_sites['trail']}/campgrounds").json()
    by_name = {c["name"]: c for c in body["campgrounds"]}
    assert by_name["Evelyn Creek"]["watchable"] is True and by_name["Evelyn Creek"]["alert_note"] is None
    assert by_name["Skyline Random"]["watchable"] is False and "no quota" in by_name["Skyline Random"]["alert_note"]
    assert by_name["Trail Cabin"]["watchable"] is False
    assert by_name["Small Camp"]["watchable"] is True and by_name["Small Camp"]["max_group_size"] == 4
    assert by_name["Signal"]["watchable"] is False  # retired


@pytest.mark.parametrize("key", ["unlimited", "cabin"])
def test_api_refuses_alerts_where_they_cant_help(client, more_sites, fetch, user, key):
    _, headers = user
    response = client.post("/api/me/alerts", json=alert_body(more_sites, site_id=str(more_sites[key])), headers=headers)
    assert response.status_code == 422
    assert fetch.calls == []


def test_api_enforces_the_maximum_group_size(client, more_sites, fetch, user):
    _, headers = user
    body = alert_body(more_sites, site_id=str(more_sites["small"]))
    too_many = client.post("/api/me/alerts", json={**body, "party_size": 5}, headers=headers)
    assert too_many.status_code == 422 and "at most 4 people" in too_many.json()["detail"]
    created = client.post("/api/me/alerts", json={**body, "party_size": 4}, headers=headers)
    assert created.status_code == 201, created.text
    # Changing the stay is held to the same limit.
    alert_id = created.json()["id"]
    stay = {"start_date": body["start_date"], "nights": body["nights"]}
    assert client.patch(f"/api/me/alerts/{alert_id}", json={**stay, "party_size": 6}, headers=headers).status_code == 422
    assert client.patch(f"/api/me/alerts/{alert_id}", json={**stay, "party_size": 3}, headers=headers).status_code == 200


# ---------------------------------------------------------------- recorded responses for the newer types


@pytest.mark.parametrize("label", sorted(RECORDED))
def test_recorded_responses_for_cabins_shelters_and_chilkoot(label):
    recorded = RECORDED[label]
    request = recorded["request"]
    group = MapGroup(request["resourceLocationId"], request["mapId"], request["bookingCategoryId"])
    start, end = date.fromisoformat(request["startDate"]), date.fromisoformat(request["endDate"])

    # The request we'd send today is the one that was recorded.
    path, headers = availability_request(group, start, end, 2)
    query = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
    for key in ("mapId", "bookingCategoryId", "startDate", "endDate", "peopleCapacityCategoryCounts", "numEquipment"):
        assert query[key] == request[key], key
    assert request["mapId"] in headers["Referer"]

    statuses = parse_statuses(recorded["body"], recorded["site"]["resource_id"], 3)
    assert set(statuses) <= {"closed", "not_released"}  # none was open: why cabins and shelters stay off
    assert summarize(statuses) in ("closed", "not_released")


def test_recorded_kinds_and_booking_categories():
    seen = {(v["site"]["kind"], v["request"]["bookingCategoryId"]) for v in RECORDED.values()}
    assert seen == {("cabin", "5"), ("shelter", "7"), ("backpacking_campground", "17")}


# ---------------------------------------------------------------- polling follows alerts


def test_catalogue_size_doesnt_change_how_much_we_poll(session_factory, world):
    """200 more campgrounds on 40 more maps, none with an alert: the poller
    still makes exactly one request, for the one map that has alerts."""
    db = session_factory()
    park = type("P", (), {"id": db.get(BackcountrySite, world["evelyn"]).park_id})
    for i in range(200):
        group = MapGroup("-555", str(-7000 - i % 40), "7")
        add_site(db, park, str(-8000 - i), f"Extra {i}", group=group)
    db.commit()
    make_alert(db, world, site="evelyn")
    make_alert(db, world, site="shovel")
    db.close()

    fake = FixtureFetch()
    report = poll(session_factory, fake, Outbox(), Clock())
    assert report.checked == 2
    assert len(fake.calls) == 1 and fake.calls[0][0]["mapId"] == SKYLINE.map_id


def test_trails_with_only_unalertable_campgrounds_arent_watchable(client, session_factory, world, fetch):
    """The SQL rule (trail search, "Alerts available") agrees with the per-site one."""
    from app.models.trail import Trail

    db = session_factory()
    park = type("P", (), {"id": db.get(BackcountrySite, world["evelyn"]).park_id})
    trail = Trail(name="Hut Approach", region="Jasper, AB", country_code="CA", province_code="AB",
                  terrain_difficulty="moderate", typical_duration_nights=1, popularity_rank=1)
    db.add(trail)
    db.flush()
    sites = [
        add_site(db, park, "-9101", "Hut Random", kind="random_zone", reservable_capacity=UNLIMITED_QUOTA),
        add_site(db, park, "-9102", "Warden Cabin", kind="cabin"),
        add_site(db, park, "-9103", "Grazing", kind="horse_camp"),
        add_site(db, park, PARADISE_VALLEY, "Paradise Valley"),
    ]
    for order, row in enumerate(sites, 1):
        db.add(TrailCampground(trail_id=trail.id, site_id=row.id, route_order=order, confidence="exact", source="test"))
    db.commit()
    trail_id = trail.id
    db.close()

    assert client.get(f"/api/trails/{trail_id}").json()["has_watchable_campgrounds"] is False
    def listed(watchable):
        return [t["name"] for t in client.get("/api/trails", params={"watchable": watchable, "limit": 100}).json()]

    assert "Hut Approach" in listed("false") and "Hut Approach" not in listed("true")
