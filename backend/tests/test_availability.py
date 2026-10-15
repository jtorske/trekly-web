"""Availability checks, alerts and the alert poller, against saved Parks Canada
responses (tests/fixtures/parks_canada_availability.json). No test makes a
network call."""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.alert_poller import JOB_NAME, alert_email, booking_url_for, build_windows, run_alert_poll
from app.backcountry import availability as av
from app.backcountry.availability import (
    AvailabilityChecker,
    MapGroup,
    ProviderError,
    RateLimited,
    availability_request,
    parse_statuses,
    summarize,
    take_budget,
    tent_pads,
)
from app.main import app
from app.models.availability import AvailabilityAlert, AvailabilityCache, JobLock
from app.models.backcountry import BackcountryPark, BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailCampground
from app.notify import Email
from app.routers.availability import get_availability_fetch, get_today

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "parks_canada_availability.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 15)
START = date(2026, 10, 20)  # the fixtures cover Oct 20-23
T0 = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

SKYLINE = MapGroup("-2147483592", "-2147483409", "7")
PUKASKWA = MapGroup("-2147483555", "-2147483276", "5")
EVELYN, SHOVEL, SNOWBOWL = "-2147483250", "-2147483167", "-2147483222"


class FixtureFetch:
    """Answers availability/map requests from the saved responses. `scenario`
    picks which response serves the Skyline map (real or synthetic full)."""

    def __init__(self, skyline="zone_jasper_skyline_near"):
        self.skyline = skyline
        self.calls = []
        self.fail = False

    def __call__(self, path, headers):
        query = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
        self.calls.append((query, headers))
        if self.fail:
            raise RuntimeError("HTTP 503")
        if query["endDate"] <= query["startDate"]:
            raise RuntimeError("HTTP Error 400: Bad Request")  # as Parks Canada answers start == end
        for label, fixture in FIXTURES.items():
            if label == "_comment" or (fixture["request"]["mapId"] == SKYLINE.map_id and label != self.skyline):
                continue
            request = fixture["request"]
            if request["mapId"] == query["mapId"] and request["startDate"] <= query["startDate"] \
                    and query["endDate"] <= request["endDate"]:
                body = json.loads(json.dumps(fixture["body"]))
                offset = (date.fromisoformat(query["startDate"]) - date.fromisoformat(request["startDate"])).days
                nights = (date.fromisoformat(query["endDate"]) - date.fromisoformat(query["startDate"])).days + 1
                for rid, entries in body["resourceAvailabilities"].items():
                    body["resourceAvailabilities"][rid] = entries[offset:offset + nights]
                return body
        raise AssertionError(f"no fixture for {query}")


class Clock:
    def __init__(self, at=T0):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, **kwargs):
        self.at += timedelta(**kwargs)


class Outbox:
    def __init__(self):
        self.sent: list[Email] = []
        self.fail = False

    def send(self, email):
        if self.fail:
            raise RuntimeError("SMTP down")
        self.sent.append(email)


def add_site(db, park, resource_id, name, group=SKYLINE, **overrides):
    values = dict(
        provider="parks_canada", provider_resource_id=resource_id, provider_location_id=group.location_id,
        provider_map_id=group.map_id, provider_booking_category_id=group.booking_category_id, park_id=park.id,
        booking_unit="Jasper - Backcountry", name=name, raw_name=name, kind="zone", is_publicly_listed=True,
        raw={}, last_synced_at=T0,
    )
    values.update(overrides)
    site = BackcountrySite(**values)
    db.add(site)
    db.flush()
    return site


@pytest.fixture
def world(session_factory, client):
    db = session_factory()
    park = BackcountryPark(provider="parks_canada", provider_park_id="1", name="Jasper", province_code="AB",
                           region="Western", last_synced_at=T0)
    db.add(park)
    db.flush()
    trail = Trail(name="Skyline Trail", region="Jasper, AB", country_code="CA", province_code="AB",
                  terrain_difficulty="moderate", typical_duration_nights=2)
    db.add(trail)
    db.flush()
    sites = {
        "evelyn": add_site(db, park, EVELYN, "Evelyn Creek", site_code="27"),
        "shovel": add_site(db, park, SHOVEL, "Little Shovel", site_code="28"),
        "snowbowl": add_site(db, park, SNOWBOWL, "Snowbowl", site_code="29"),
        "hidden": add_site(db, park, "-2147483282", "Watchtower", is_publicly_listed=False),
        "gone": add_site(db, park, "-2147483193", "Signal", retired_at=T0),
        "nomap": add_site(db, park, "-77", "Offline Camp", provider_map_id=None),
        "pad": add_site(db, park, "-2147477576", "PH1", group=PUKASKWA, kind="site"),
    }
    for order, key in enumerate(["evelyn", "shovel", "snowbowl", "hidden", "gone"], 1):
        db.add(TrailCampground(trail_id=trail.id, site_id=sites[key].id, route_order=order,
                               confidence="exact", source="test"))
    db.commit()
    ids = {"trail": trail.id, **{k: v.id for k, v in sites.items()}}
    db.close()
    return ids


@pytest.fixture
def fetch():
    fake = FixtureFetch()
    app.dependency_overrides[get_availability_fetch] = lambda: fake
    app.dependency_overrides[get_today] = lambda: TODAY
    yield fake


def sites_by_key(db, world, *keys):
    return [db.get(BackcountrySite, world[k]) for k in keys]


# ---------------------------------------------------------------- parsing and request shape


def test_status_values_from_real_responses():
    assert parse_statuses(FIXTURES["zone_jasper_skyline_near"]["body"], EVELYN, 4) == ["available"] * 4
    assert parse_statuses(FIXTURES["permit_wct_near"]["body"], "-2147472750", 4) == ["closed"] * 4
    assert parse_statuses(FIXTURES["pad_pukaskwa_near"]["body"], "-2147477576", 4) == ["closed"] * 4
    assert parse_statuses(FIXTURES["zone_jasper_skyline_future"]["body"], EVELYN, 4) == ["not_released"] * 4
    synthetic = FIXTURES["synthetic_zone_partly_full"]["body"]
    assert parse_statuses(synthetic, EVELYN, 4) == ["available", "full", "available", "available"]
    assert parse_statuses(synthetic, EVELYN, 2, offset=2) == ["available", "available"]


def test_unknown_codes_and_missing_nights_are_never_available():
    body = {"resourceAvailabilities": {"1": [{"availability": 5}, {"availability": 0}]}}
    assert parse_statuses(body, "1", 3) == ["unknown", "available", "unknown"]
    assert parse_statuses(body, "missing", 1) == ["unknown"]
    assert parse_statuses({}, "1", 1) == ["unknown"]


@pytest.mark.parametrize("statuses, summary", [
    (["available", "available"], "available"),
    (["available", "full"], "partial"),
    (["full", "full"], "full"),
    (["closed", "closed"], "closed"),
    (["closed", "full"], "full"),
    (["closed", "unknown"], "unknown"),
])
def test_summary(statuses, summary):
    assert summarize(statuses) == summary


def test_request_shape():
    path, headers = availability_request(SKYLINE, START, START + timedelta(days=2), party_size=6)
    query = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
    assert path.startswith("availability/map?")
    assert (query["mapId"], query["bookingCategoryId"]) == (SKYLINE.map_id, "7")
    assert (query["startDate"], query["endDate"]) == ("2026-10-20", "2026-10-22")  # inclusive
    assert json.loads(query["peopleCapacityCategoryCounts"])[0]["count"] == 6
    assert query["numEquipment"] == "2"  # 4 people per tent pad
    assert query["getDailyAvailability"] == "true"
    assert headers["Referer"].startswith("https://reservation.pc.gc.ca/create-booking/results?resourceLocationId=-2147483592")
    path2, _ = availability_request(SKYLINE, START, START, 2)
    assert parse_qs(urlsplit(path2).query)["cartUid"] != query["cartUid"]
    assert [tent_pads(n) for n in (1, 4, 5, 12)] == [1, 1, 2, 3]


# ---------------------------------------------------------------- checker: grouping, cache, budget


def test_one_request_per_map_and_cached_after(session_factory, world):
    db = session_factory()
    fake, clock = FixtureFetch(), Clock()
    checker = AvailabilityChecker(db, fake, now=clock)
    sites = sites_by_key(db, world, "evelyn", "shovel", "snowbowl", "pad")
    result = checker.check(sites, START, 3, 2)
    assert len(fake.calls) == 2 and result.live_requests == 2
    assert result.sites[world["evelyn"]].statuses == ["available"] * 3
    assert result.sites[world["pad"]].summary == "closed"

    clock.advance(minutes=4)
    again = checker.check(sites, START, 3, 2)
    assert len(fake.calls) == 2 and again.live_requests == 0
    assert again.fetched_at == T0

    clock.advance(minutes=2)  # past the 5-minute TTL
    checker.check(sites, START, 3, 2)
    assert len(fake.calls) == 4
    db.close()


def test_party_size_is_part_of_the_cache_key(session_factory, world):
    db = session_factory()
    fake = FixtureFetch()
    checker = AvailabilityChecker(db, fake, now=Clock())
    sites = sites_by_key(db, world, "evelyn")
    checker.check(sites, START, 2, 2)
    checker.check(sites, START, 2, 5)
    assert len(fake.calls) == 2
    db.close()


def test_sites_without_a_map_are_unknown_without_a_request(session_factory, world):
    db = session_factory()
    fake = FixtureFetch()
    result = AvailabilityChecker(db, fake, now=Clock()).check(sites_by_key(db, world, "nomap"), START, 2, 2)
    assert result.sites[world["nomap"]].statuses == ["unknown", "unknown"] and fake.calls == []
    db.close()


def test_global_budget_caps_live_requests_per_minute(session_factory, world):
    db = session_factory()
    fake, clock = FixtureFetch(), Clock()
    checker = AvailabilityChecker(db, fake, now=clock, requests_per_minute=2)
    sites = sites_by_key(db, world, "evelyn")
    checker.check(sites, START, 1, 1)
    checker.check(sites, START, 1, 2)
    with pytest.raises(RateLimited) as caught:
        checker.check(sites, START, 1, 3)
    assert 1 <= caught.value.retry_after_s <= 60 and len(fake.calls) == 2
    checker.check(sites, START, 1, 1)  # cached: no budget needed
    clock.advance(seconds=61)
    checker.check(sites, START, 1, 3)
    assert len(fake.calls) == 3
    db.close()


def test_budget_is_shared_between_checkers(session_factory, world):
    one, two = session_factory(), session_factory()
    clock = Clock()
    take_budget(one, clock(), limit=1)
    with pytest.raises(RateLimited):
        take_budget(two, clock(), limit=1)
    one.close()
    two.close()


def test_provider_errors_are_not_cached(session_factory, world):
    db = session_factory()
    fake = FixtureFetch()
    fake.fail = True
    with pytest.raises(ProviderError):
        AvailabilityChecker(db, fake, now=Clock()).check(sites_by_key(db, world, "evelyn"), START, 1, 2)
    assert db.scalar(select(AvailabilityCache)) is None
    db.close()


# ---------------------------------------------------------------- availability API


def test_api_checks_only_the_trails_listed_campgrounds(client, world, fetch):
    body = client.get(f"/api/trails/{world['trail']}/availability",
                      params={"start": "2026-10-20", "nights": 3, "party": 2}).json()
    assert {c["site_id"] for c in body["campgrounds"]} == {str(world[k]) for k in ("evelyn", "shovel", "snowbowl")}
    assert len(fetch.calls) == 1  # one map, one request; no unlisted or retired sites
    evelyn = next(c for c in body["campgrounds"] if c["site_id"] == str(world["evelyn"]))
    assert evelyn["summary"] == "available"
    assert [n["date"] for n in evelyn["nights"]] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert body["checked_at"] is not None


def test_api_reports_full_nights(client, world, fetch):
    fetch.skyline = "synthetic_zone_partly_full"
    body = client.get(f"/api/trails/{world['trail']}/availability", params={"start": "2026-10-20", "nights": 2}).json()
    summaries = {c["site_id"]: c["summary"] for c in body["campgrounds"]}
    assert summaries[str(world["evelyn"])] == "partial"
    assert summaries[str(world["shovel"])] == "full"


@pytest.mark.parametrize("params", [
    {"start": "2026-10-14", "nights": 2},  # past
    {"start": "2026-10-20", "nights": 15},
    {"start": "2026-10-20", "nights": 0},
    {"start": "2028-06-01", "nights": 2},  # too far ahead
    {"start": "2026-10-20", "nights": 2, "party": 13},
])
def test_api_validates_the_stay(client, world, fetch, params):
    assert client.get(f"/api/trails/{world['trail']}/availability", params=params).status_code == 422
    assert fetch.calls == []


def test_api_busy_and_provider_errors(client, world, fetch, monkeypatch):
    monkeypatch.setattr(av, "REQUESTS_PER_MINUTE", 0)
    busy = client.get(f"/api/trails/{world['trail']}/availability", params={"start": "2026-10-20", "nights": 1})
    assert busy.status_code == 429 and int(busy.headers["Retry-After"]) >= 1
    assert fetch.calls == []
    monkeypatch.setattr(av, "REQUESTS_PER_MINUTE", 20)
    fetch.fail = True
    down = client.get(f"/api/trails/{world['trail']}/availability", params={"start": "2026-10-21", "nights": 1})
    assert down.status_code == 502


def test_api_unknown_trail(client, fetch):
    assert client.get(f"/api/trails/{uuid.uuid4()}/availability",
                      params={"start": "2026-10-20", "nights": 1}).status_code == 404


# ---------------------------------------------------------------- alerts API


@pytest.fixture
def user(make_token):
    user_id = uuid.uuid4()
    return user_id, {"Authorization": f"Bearer {make_token(user_id, email='hiker@example.com')}"}


def alert_body(world, **overrides):
    body = {"site_id": str(world["evelyn"]), "trail_id": str(world["trail"]),
            "start_date": "2026-10-20", "nights": 2, "party_size": 2}
    body.update(overrides)
    return body


def test_guests_cannot_set_alerts(client, world, fetch):
    assert client.post("/api/me/alerts", json=alert_body(world)).status_code == 401
    assert client.get("/api/me/alerts").status_code == 401


def test_create_list_cancel_rearm_delete(client, session_factory, world, fetch, user):
    user_id, headers = user
    created = client.post("/api/me/alerts", json=alert_body(world), headers=headers)
    assert created.status_code == 201, created.text
    alert = created.json()
    assert (alert["campground"], alert["site_code"], alert["park"]) == ("Evelyn Creek", "27", "Jasper")
    assert alert["trail"]["name"] == "Skyline Trail"
    assert (alert["end_date"], alert["status"]) == ("2026-10-22", "active")
    assert fetch.calls == []  # setting an alert never calls the provider

    db = session_factory()
    assert db.get(AvailabilityAlert, uuid.UUID(alert["id"])).email == "hiker@example.com"
    db.close()

    assert [a["id"] for a in client.get("/api/me/alerts", headers=headers).json()] == [alert["id"]]
    assert client.post(f"/api/me/alerts/{alert['id']}/rearm", headers=headers).status_code == 409
    cancelled = client.post(f"/api/me/alerts/{alert['id']}/cancel", headers=headers).json()
    assert cancelled["status"] == "cancelled"
    assert client.delete(f"/api/me/alerts/{alert['id']}", headers=headers).status_code == 204
    assert client.get("/api/me/alerts", headers=headers).json() == []


def test_rearm_after_notification(client, session_factory, world, fetch, user):
    _, headers = user
    alert = client.post("/api/me/alerts", json=alert_body(world), headers=headers).json()
    db = session_factory()
    db.get(AvailabilityAlert, uuid.UUID(alert["id"])).status = "notified"
    db.commit()
    db.close()
    assert client.post(f"/api/me/alerts/{alert['id']}/rearm", headers=headers).json()["status"] == "active"


@pytest.mark.parametrize("overrides, status_code", [
    ({"site_id": "hidden"}, 422),       # not publicly listed
    ({"site_id": "gone"}, 422),         # retired
    ({"site_id": "nomap"}, 422),        # no online availability
    ({"site_id": "pad"}, 422),          # not on this trail
    ({"start_date": "2026-10-14"}, 422),
    ({"nights": 15}, 422),
])
def test_invalid_alerts(client, world, fetch, user, overrides, status_code):
    _, headers = user
    if "site_id" in overrides:
        overrides = {"site_id": str(world[overrides["site_id"]])}
    assert client.post("/api/me/alerts", json=alert_body(world, **overrides), headers=headers).status_code == status_code


def test_duplicate_and_limit(client, world, fetch, user, monkeypatch):
    _, headers = user
    assert client.post("/api/me/alerts", json=alert_body(world), headers=headers).status_code == 201
    assert client.post("/api/me/alerts", json=alert_body(world), headers=headers).status_code == 409
    for nights in range(3, 12):
        client.post("/api/me/alerts", json=alert_body(world, nights=nights), headers=headers)
    over = client.post("/api/me/alerts", json=alert_body(world, nights=12), headers=headers)
    assert over.status_code == 422 and "up to 10" in over.json()["detail"]


def test_alerts_need_an_email(client, world, fetch, make_token):
    headers = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    assert client.post("/api/me/alerts", json=alert_body(world), headers=headers).status_code == 422


def test_users_cannot_see_or_touch_each_others_alerts(client, world, fetch, user, make_token):
    _, headers = user
    alert = client.post("/api/me/alerts", json=alert_body(world), headers=headers).json()
    other = {"Authorization": f"Bearer {make_token(uuid.uuid4(), email='other@example.com')}"}
    assert client.get("/api/me/alerts", headers=other).json() == []
    assert client.post(f"/api/me/alerts/{alert['id']}/cancel", headers=other).status_code == 404
    assert client.delete(f"/api/me/alerts/{alert['id']}", headers=other).status_code == 404


# ---------------------------------------------------------------- poller


def make_alert(db, world, site="evelyn", start=START, nights=2, party=2, **overrides):
    alert = AvailabilityAlert(user_id=uuid.uuid4(), email="hiker@example.com", site_id=world[site],
                              trail_id=world["trail"], start_date=start, nights=nights, party_size=party,
                              status="active", **overrides)
    db.add(alert)
    db.commit()
    return alert.id


def poll(session_factory, fake, outbox, clock, **kwargs):
    db = session_factory()
    try:
        checker = AvailabilityChecker(db, fake, now=clock)
        return run_alert_poll(db, checker, outbox, now=clock, holder="test", **kwargs)
    finally:
        db.close()


def test_poller_notifies_once_when_the_whole_stay_opens(session_factory, world):
    db = session_factory()
    open_id = make_alert(db, world, "evelyn", nights=3)
    full_id = make_alert(db, world, "shovel", start=START + timedelta(days=1), nights=2)
    db.close()
    fake, outbox, clock = FixtureFetch("synthetic_zone_partly_full"), Outbox(), Clock()

    report = poll(session_factory, fake, outbox, clock)
    # Evelyn is full on night 2 in the synthetic response, Little Shovel every night.
    assert (report.checked, report.notified, len(fake.calls)) == (2, 0, 1)

    fake.skyline = "zone_jasper_skyline_near"  # everything opens up
    clock.advance(minutes=11)
    report = poll(session_factory, fake, outbox, clock)
    assert report.notified == 2 and len(fake.calls) == 2
    assert len(outbox.sent) == 2
    db = session_factory()
    opened = db.get(AvailabilityAlert, open_id)
    assert opened.status == "notified" and opened.last_result == ["available"] * 3
    assert db.get(AvailabilityAlert, full_id).status == "notified"
    db.close()

    clock.advance(minutes=11)
    report = poll(session_factory, fake, outbox, clock)
    assert report.checked == 0 and len(outbox.sent) == 2  # never emailed twice


def test_alerts_on_one_map_share_a_request(session_factory, world):
    db = session_factory()
    for site, offset in (("evelyn", 0), ("shovel", 1), ("snowbowl", 2)):
        make_alert(db, world, site, start=START + timedelta(days=offset), nights=1)
    make_alert(db, world, "pad", nights=2)
    db.close()
    fake = FixtureFetch()
    report = poll(session_factory, fake, Outbox(), Clock())
    assert report.checked == 4 and len(fake.calls) == 2  # Skyline once, Pukaskwa once
    skyline_call = next(q for q, _ in fake.calls if q["mapId"] == SKYLINE.map_id)
    assert (skyline_call["startDate"], skyline_call["endDate"]) == ("2026-10-20", "2026-10-22")


def test_windows_split_far_apart_dates(session_factory, world):
    db = session_factory()
    make_alert(db, world, "evelyn", start=START, nights=1)
    make_alert(db, world, "shovel", start=START + timedelta(days=60), nights=1)
    make_alert(db, world, "snowbowl", start=START, nights=1, party=6)
    alerts = db.scalars(select(AvailabilityAlert)).all()
    windows = build_windows(alerts)
    assert len(windows) == 3  # two date windows for party 2, one for party 6
    db.close()


def test_poller_runs_never_overlap_and_respect_the_minimum_interval(session_factory, world):
    db = session_factory()
    make_alert(db, world)
    db.add(JobLock(name=JOB_NAME, locked_by="other-host:1", locked_until=T0 + timedelta(minutes=5)))
    db.commit()
    db.close()
    fake, outbox, clock = FixtureFetch(), Outbox(), Clock()

    report = poll(session_factory, fake, outbox, clock)
    assert report.status == "skipped" and "holds the lock" in report.reason and fake.calls == []

    clock.advance(minutes=6)  # the other run's lease has expired (e.g. it crashed)
    assert poll(session_factory, fake, outbox, clock).status == "ran"

    clock.advance(minutes=3)
    report = poll(session_factory, fake, outbox, clock)
    assert report.status == "skipped" and "minimum interval" in report.reason

    db = session_factory()
    lock = db.get(JobLock, JOB_NAME)
    assert lock.locked_until is None and lock.last_finished_at is not None and lock.last_result.startswith("checked")
    db.close()


def test_poller_request_cap_defers_the_rest(session_factory, world):
    db = session_factory()
    make_alert(db, world, "evelyn")
    make_alert(db, world, "pad")
    db.close()
    fake = FixtureFetch()
    report = poll(session_factory, fake, Outbox(), Clock(), max_requests=1)
    assert len(fake.calls) == 1 and report.checked == 1 and report.deferred == 1


def test_poller_stops_when_the_global_budget_is_used_up(session_factory, world):
    db = session_factory()
    make_alert(db, world, "evelyn")
    for _ in range(av.REQUESTS_PER_MINUTE):
        take_budget(db, T0)
    db.close()
    fake = FixtureFetch()
    report = poll(session_factory, fake, Outbox(), Clock())
    assert fake.calls == [] and report.deferred == 1


def test_poller_expires_past_alerts(session_factory, world):
    db = session_factory()
    past = make_alert(db, world, start=TODAY - timedelta(days=1))
    db.close()
    report = poll(session_factory, FixtureFetch(), Outbox(), Clock())
    assert report.expired == 1
    db = session_factory()
    assert db.get(AvailabilityAlert, past).status == "expired"
    db.close()


def test_failed_email_keeps_the_alert_active(session_factory, world):
    db = session_factory()
    alert_id = make_alert(db, world)
    db.close()
    outbox = Outbox()
    outbox.fail = True
    report = poll(session_factory, FixtureFetch(), outbox, Clock())
    assert report.notified == 0 and report.errors
    db = session_factory()
    assert db.get(AvailabilityAlert, alert_id).status == "active"
    db.close()


def test_alert_email_content(session_factory, world):
    db = session_factory()
    alert_id = make_alert(db, world, nights=2, party=3)
    alert = db.get(AvailabilityAlert, alert_id)
    email = alert_email(alert, booking_url_for(alert))
    assert email.to == "hiker@example.com"
    assert email.subject == "Evelyn Creek has opened up for Tue Oct 20"
    assert "Tue Oct 20 to Thu Oct 22 (2 nights), party of 3" in email.text
    assert "resourceLocationId=-2147483592&mapId=-2147483409&bookingCategoryId=7" in email.text
    assert f"/trails?id={world['trail']}&start=2026-10-20&nights=2&party=3" in email.text
    assert "/alerts" in email.text
    db.close()


def test_one_night_asks_for_two_dates(session_factory, world):
    """Parks Canada rejects startDate == endDate (HTTP 400, seen live)."""
    db = session_factory()
    fake = FixtureFetch()
    result = AvailabilityChecker(db, fake, now=Clock()).check(sites_by_key(db, world, "evelyn"), START, 1, 2)
    assert result.sites[world["evelyn"]].statuses == ["available"]
    query = fake.calls[0][0]
    assert (query["startDate"], query["endDate"]) == ("2026-10-20", "2026-10-21")
    db.close()


def test_poller_handles_a_one_night_alert(session_factory, world):
    db = session_factory()
    make_alert(db, world, nights=1)
    db.close()
    outbox = Outbox()
    report = poll(session_factory, FixtureFetch(), outbox, Clock())
    assert report.errors == [] and report.notified == 1 and len(outbox.sent) == 1
