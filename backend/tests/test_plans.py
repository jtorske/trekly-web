"""Trip plans API: ownership, itinerary validation, booked-night protection,
derived night statuses and per-plan availability checks (saved fixtures only,
no network)."""

import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.availability import AvailabilityAlert
from app.models.backcountry import BackcountrySite
from app.models.trail_campground import TrailCampground
from app.models.trip_plan import TripPlanNight
from tests.test_availability import TODAY, add_site, fetch, world  # noqa: F401  (fixtures)


@pytest.fixture
def owner(make_token):
    user_id = uuid.uuid4()
    return user_id, {"Authorization": f"Bearer {make_token(user_id, email='hiker@example.com')}"}


@pytest.fixture
def stranger(make_token):
    return {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}


@pytest.fixture
def trail(world, session_factory):
    """The test world's Skyline Trail, plus a trail permit and a group-size
    limit at Little Shovel."""
    db = session_factory()
    db.get(BackcountrySite, world["shovel"]).max_group_size = 4
    park = db.get(BackcountrySite, world["evelyn"]).park
    permit = add_site(db, park, "-99", "Skyline Trail permit", kind="trail_permit")
    db.add(TrailCampground(trail_id=world["trail"], site_id=permit.id, route_order=6,
                           confidence="exact", source="test"))
    db.commit()
    db.close()
    return {**world, "permit": permit.id}


def night(key=None, trail=None, choice=None):
    if key is None:
        return {"choice": choice or "undecided", "site_id": None}
    return {"choice": "campground", "site_id": str(trail[key])}


def plan_body(trail, **overrides):
    body = {
        "trail_id": str(trail["trail"]),
        "title": "  Skyline with Sam ",
        "start_date": "2026-10-20",
        "nights": 3,
        "party_size": 2,
        "notes": "",
        "itinerary": [night("evelyn", trail), night("shovel", trail), night(choice="outside")],
    }
    body.update(overrides)
    return body


def edit_body(plan, **overrides):
    body = {
        "title": plan["title"],
        "start_date": plan["start_date"],
        "nights": plan["nights"],
        "party_size": plan["party_size"],
        "setup_id": plan["setup_id"],
        "notes": plan["notes"],
        "itinerary": [
            {"choice": n["choice"], "site_id": n["site"]["id"] if n["site"] else None} for n in plan["itinerary"]
        ],
    }
    body.update(overrides)
    return body


def create(client, headers, body):
    response = client.post("/api/me/plans", json=body, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()


def test_guests_cannot_use_plans(client, trail, fetch):
    assert client.get("/api/me/plans").status_code == 401
    assert client.post("/api/me/plans", json=plan_body(trail)).status_code == 401


def test_create_and_read_a_plan(client, trail, fetch, owner):
    _, headers = owner
    plan = create(client, headers, plan_body(trail))
    assert plan["title"] == "Skyline with Sam" and plan["notes"] is None
    assert plan["trail"]["name"] == "Skyline Trail"
    # Plain dates: night N is start + N; you walk out the morning after the last night.
    assert [n["date"] for n in plan["itinerary"]] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert plan["last_night"] == "2026-10-22" and plan["end_date"] == "2026-10-23"
    evelyn, shovel, outside = plan["itinerary"]
    assert evelyn["site"]["name"] == "Evelyn Creek" and evelyn["status"] == "not_checked"
    assert evelyn["site"]["checkable"] is True and "resourceLocationId" in evelyn["site"]["book_url"]
    assert shovel["site"]["max_group_size"] == 4
    assert outside["choice"] == "outside" and outside["site"] is None and outside["status"] is None
    assert plan["permits"][0]["name"] == "Skyline Trail permit"

    assert client.get(f"/api/me/plans/{plan['id']}", headers=headers).json() == plan
    listed = client.get("/api/me/plans", headers=headers).json()
    assert [(p["id"], p["nights"], p["booked_nights"]) for p in listed] == [(plan["id"], 3, 0)]


def test_plans_are_private(client, trail, fetch, owner, stranger):
    plan = create(client, owner[1], plan_body(trail))
    url = f"/api/me/plans/{plan['id']}"
    assert client.get(url, headers=stranger).status_code == 404
    assert client.put(url, json=edit_body(plan), headers=stranger).status_code == 404
    assert client.put(f"{url}/nights/0", json={"booked_by_me": True}, headers=stranger).status_code == 404
    assert client.post(f"{url}/check", headers=stranger).status_code == 404
    assert client.delete(url, headers=stranger).status_code == 404
    assert client.get("/api/me/plans", headers=stranger).json() == []


@pytest.mark.parametrize("change", [
    {"itinerary": [night()]},  # length doesn't match nights
    {"nights": 15, "itinerary": [night()] * 15},
    {"party_size": 13},
    {"start_date": "2026-10-13"},  # before today, beyond the one-day time zone allowance
    {"start_date": "2028-06-01"},
    {"itinerary": [night(), {"choice": "campground", "site_id": None}, night()]},
    {"itinerary": [night(), {"choice": "outside", "site_id": str(uuid.uuid4())}, night()]},
])
def test_create_validates_the_plan(client, trail, fetch, owner, change):
    assert client.post("/api/me/plans", json=plan_body(trail, **change), headers=owner[1]).status_code == 422


@pytest.mark.parametrize("key", ["pad", "hidden", "permit", "gone"])
def test_nights_only_take_this_trails_campgrounds(client, trail, fetch, owner, key):
    """Not on the trail, not publicly listed, a permit (not a place to sleep),
    or retired: none can be picked for a night."""
    body = plan_body(trail, itinerary=[night(key, trail), night(), night()])
    response = client.post("/api/me/plans", json=body, headers=owner[1])
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Night 1:")


def test_a_plan_may_start_yesterday_for_users_behind_the_server(client, trail, fetch, owner):
    assert client.post("/api/me/plans", json=plan_body(trail, start_date="2026-10-14"),
                       headers=owner[1]).status_code == 201


def test_setup_must_be_your_own(client, trail, fetch, owner, stranger):
    theirs = client.post("/api/me/setups", json={"name": "Not yours"}, headers=stranger).json()
    response = client.post("/api/me/plans", json=plan_body(trail, setup_id=theirs["id"]), headers=owner[1])
    assert response.status_code == 422

    mine = client.post("/api/me/setups", json={"name": "Weekend kit"}, headers=owner[1]).json()
    plan = create(client, owner[1], plan_body(trail, setup_id=mine["id"]))
    assert plan["setup"]["name"] == "Weekend kit" and plan["setup"]["known_weight_g"] == 0

    # Deleting the setup keeps the plan, without gear.
    assert client.delete(f"/api/me/setups/{mine['id']}", headers=owner[1]).status_code == 204
    reread = client.get(f"/api/me/plans/{plan['id']}", headers=owner[1]).json()
    assert reread["setup_id"] is None and reread["setup"] is None


def test_mark_nights_booked(client, trail, fetch, owner):
    plan = create(client, owner[1], plan_body(trail, itinerary=[night("evelyn", trail), night(), night(choice="outside")]))
    url = f"/api/me/plans/{plan['id']}/nights"
    booked = client.put(f"{url}/0", json={"booked_by_me": True}, headers=owner[1]).json()
    assert booked["itinerary"][0]["status"] == "booked" and booked["booked_nights"] == 1
    # Somewhere Parks Canada doesn't book can be marked booked too...
    assert client.put(f"{url}/2", json={"booked_by_me": True}, headers=owner[1]).json()["itinerary"][2]["status"] == "booked"
    # ...but not a night with nowhere chosen.
    assert client.put(f"{url}/1", json={"booked_by_me": True}, headers=owner[1]).status_code == 422
    assert client.put(f"{url}/7", json={"booked_by_me": True}, headers=owner[1]).status_code == 404
    unbooked = client.put(f"{url}/0", json={"booked_by_me": False}, headers=owner[1]).json()
    assert unbooked["itinerary"][0]["status"] == "not_checked"


def test_edits_that_would_drop_a_booked_night_need_confirming(client, trail, fetch, owner):
    plan = create(client, owner[1], plan_body(trail))
    url = f"/api/me/plans/{plan['id']}"
    plan = client.put(f"{url}/nights/2", json={"booked_by_me": True}, headers=owner[1]).json()

    shorter = edit_body(plan, nights=2, itinerary=edit_body(plan)["itinerary"][:2])
    refused = client.put(url, json=shorter, headers=owner[1])
    assert refused.status_code == 409
    assert "night 3 (2026-10-22)" in refused.json()["detail"]
    assert client.get(url, headers=owner[1]).json()["nights"] == 3  # nothing written

    moved = edit_body(plan, start_date="2026-10-21")
    assert client.put(url, json=moved, headers=owner[1]).status_code == 409
    swapped = edit_body(plan)
    swapped["itinerary"][2] = night("snowbowl", trail)
    assert client.put(url, json=swapped, headers=owner[1]).status_code == 409

    done = client.put(url, json=shorter | {"confirm_drop_booked": True}, headers=owner[1])
    assert done.status_code == 200
    assert done.json()["nights"] == 2 and len(done.json()["itinerary"]) == 2 and done.json()["booked_nights"] == 0


def test_unrelated_edits_keep_booked_nights(client, trail, fetch, owner):
    plan = create(client, owner[1], plan_body(trail))
    url = f"/api/me/plans/{plan['id']}"
    plan = client.put(f"{url}/nights/0", json={"booked_by_me": True}, headers=owner[1]).json()
    longer = edit_body(plan, notes="Bring bear spray", nights=4,
                       itinerary=edit_body(plan)["itinerary"] + [night("snowbowl", trail)])
    updated = client.put(url, json=longer, headers=owner[1]).json()
    assert updated["notes"] == "Bring bear spray"
    assert [n["status"] for n in updated["itinerary"]] == ["booked", "not_checked", None, "not_checked"]


def test_retired_campground_can_stay_on_a_plan(client, trail, fetch, owner, session_factory):
    plan = create(client, owner[1], plan_body(trail))
    db = session_factory()
    db.get(BackcountrySite, trail["evelyn"]).retired_at = datetime(2026, 10, 16, tzinfo=timezone.utc)
    db.commit()
    db.close()
    reread = client.get(f"/api/me/plans/{plan['id']}", headers=owner[1]).json()
    assert reread["itinerary"][0]["site"]["retired"] is True
    assert reread["itinerary"][0]["site"]["checkable"] is False
    # Saving the plan unchanged keeps it; moving it to another night doesn't.
    assert client.put(f"/api/me/plans/{plan['id']}", json=edit_body(reread), headers=owner[1]).status_code == 200
    moved = edit_body(reread)
    moved["itinerary"] = [night(), night("evelyn", trail), night()]
    assert client.put(f"/api/me/plans/{plan['id']}", json=moved, headers=owner[1]).status_code == 422


def test_active_alert_shows_on_the_night_it_covers(client, trail, fetch, owner, session_factory):
    user_id, headers = owner
    plan = create(client, headers, plan_body(trail))
    db = session_factory()
    db.add(AvailabilityAlert(user_id=user_id, email="hiker@example.com", site_id=trail["shovel"],
                             start_date=date(2026, 10, 21), nights=1, party_size=2, status="active"))
    db.add(AvailabilityAlert(user_id=user_id, email="hiker@example.com", site_id=trail["evelyn"],
                             start_date=date(2026, 10, 20), nights=1, party_size=2, status="cancelled"))
    db.commit()
    db.close()
    reread = client.get(f"/api/me/plans/{plan['id']}", headers=headers).json()
    assert [n["status"] for n in reread["itinerary"]] == ["not_checked", "alert", None]
    assert reread["itinerary"][1]["alert_id"] is not None


def test_check_remembers_each_nights_answer(client, trail, fetch, owner):
    plan = create(client, owner[1], plan_body(trail))
    url = f"/api/me/plans/{plan['id']}"
    fetch.skyline = "synthetic_zone_partly_full"
    checked = client.post(f"{url}/check", headers=owner[1]).json()
    evelyn, shovel, outside = checked["itinerary"]
    assert len(fetch.calls) == 1  # both campgrounds share one map
    assert evelyn["last_checked_at"] is not None and evelyn["status"] == evelyn["last_status"]
    assert shovel["status"] == "full"
    assert outside["last_status"] is None

    # A different party size can change the answer, so old checks are dropped.
    bigger = client.put(url, json=edit_body(checked, party_size=6), headers=owner[1]).json()
    assert [n["status"] for n in bigger["itinerary"]] == ["not_checked", "not_checked", None]


def test_check_skips_nights_already_past(client, trail, fetch, owner, session_factory):
    plan = create(client, owner[1], plan_body(trail, start_date="2026-10-14",
                                              itinerary=[night("evelyn", trail), night(), night()]))
    response = client.post(f"/api/me/plans/{plan['id']}/check", headers=owner[1])
    assert response.status_code == 200 and fetch.calls == []  # only night 1 had a campground, and it's past
    assert response.json()["itinerary"][0]["status"] == "not_checked"


def test_check_a_finished_trip(client, trail, fetch, owner):
    plan = create(client, owner[1], plan_body(trail, start_date="2026-10-14", nights=1, itinerary=[night("evelyn", trail)]))
    assert client.post(f"/api/me/plans/{plan['id']}/check", headers=owner[1]).status_code == 422


def test_delete_plan(client, trail, fetch, owner, session_factory):
    plan = create(client, owner[1], plan_body(trail))
    assert client.delete(f"/api/me/plans/{plan['id']}", headers=owner[1]).status_code == 204
    assert client.get(f"/api/me/plans/{plan['id']}", headers=owner[1]).status_code == 404
    db = session_factory()
    assert db.query(TripPlanNight).count() == 0
    db.close()


def test_list_is_soonest_first(client, trail, fetch, owner):
    later = create(client, owner[1], plan_body(trail, start_date="2026-11-02"))
    sooner = create(client, owner[1], plan_body(trail, start_date="2026-10-16"))
    assert [p["id"] for p in client.get("/api/me/plans", headers=owner[1]).json()] == [sooner["id"], later["id"]]
