"""Hikes from before Trekly (undated), the "hikes dated today" fair-use limit,
and what verification means for a hike log."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.main import app
from app.milestones import Facts, Hike, check, gather
from app.milestones_config import BY_ID, SEASONS
from app.models.hike_log import HikeLog
from app.models.trail import Trail
from app.points import score, verified_hikes
from app.routers.availability import get_today
from app.routers.me_hike_logs import TODAY_LIMIT

TODAY = date(2026, 11, 3)
PAST = "/api/me/hike-logs/past"


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = [
        Trail(name=f"Trail {i}", region="Banff National Park, AB", country_code="CA", province_code="AB",
              terrain_difficulty="moderate", typical_duration_nights=1 if i == 0 else 0)
        for i in range(6)
    ]
    rows.append(Trail(name="Old Trail", region="Gone, AB", country_code="CA", province_code="AB",
                      terrain_difficulty="easy", retired_at=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    session.add_all(rows)
    session.commit()
    ids = [str(row.id) for row in rows]
    session.close()
    app.dependency_overrides[get_today] = lambda: TODAY
    yield ids
    app.dependency_overrides.pop(get_today, None)


@pytest.fixture
def alice():
    return uuid.uuid4()


def put(client, headers, trail_id, hiked_on, **more):
    return client.put(f"/api/me/hike-logs/{trail_id}", json={"hiked_on": hiked_on, **more}, headers=headers)


# ---------------------------------------------------------------- undated hikes

def test_past_hikes_are_added_undated_and_never_overwrite(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    assert put(client, headers, trails[0], "2026-07-01").status_code == 201

    response = client.post(PAST, json={"trail_ids": [trails[0], trails[1], trails[2], trails[2], trails[6]]},
                           headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert [log["trail"]["id"] for log in body["added"]] == [trails[1], trails[2]]
    assert all(log["hiked_on"] is None and log["verified"] is False for log in body["added"])
    # The dated hike stays dated and the retired trail is skipped (repeats count once).
    assert body["skipped"] == 2

    logs = client.get("/api/me/hike-logs", headers=headers).json()
    assert logs[0]["hiked_on"] == "2026-07-01"  # dated first, undated after
    assert [log["hiked_on"] for log in logs[1:]] == [None, None]

    again = client.post(PAST, json={"trail_ids": [trails[1], trails[2]]}, headers=headers).json()
    assert again == {"added": [], "skipped": 2}


def test_past_hikes_need_a_list_and_sign_in(client, auth_headers, alice, trails):
    assert client.post(PAST, json={"trail_ids": [trails[1]]}).status_code == 401
    assert client.post(PAST, json={"trail_ids": []}, headers=auth_headers(alice)).status_code == 422


def test_an_entry_can_be_undated_and_dated_later(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    created = put(client, headers, trails[1], None, note="Years ago")
    assert created.status_code == 201
    assert created.json()["hiked_on"] is None
    assert put(client, headers, trails[1], "2019-08-10").json()["hiked_on"] == "2019-08-10"


def hike(day=None, nights=0, **more):
    trail = Trail(id=uuid.uuid4(), name="t", region="Banff National Park, AB", country_code="CA",
                  province_code="AB", terrain_difficulty="moderate", typical_duration_nights=nights)
    return Hike(trail, date.fromisoformat(day) if day else None, **more)


def test_undated_hikes_count_for_everything_but_date_milestones():
    undated = Facts(hikes=[hike(), hike()])
    # Counting rules see them...
    assert check(BY_ID["first-hike"], undated).earned
    assert score(undated).trails > 0
    # ...date rules don't.
    for milestone in BY_ID.values():
        if milestone.rule in {"seasons", "in_months", "consecutive_months", "calendar_months", "consecutive_days",
                              "same_day", "on_date", "tagged_in_window"}:
            assert not check(milestone, undated).earned, milestone.id

    # The same hikes with dates do earn date rules (Canada Day here).
    canada_day = next(m for m in BY_ID.values() if m.rule == "on_date" and m.params == {"month": 7, "day": 1})
    assert check(canada_day, Facts(hikes=[hike("2024-07-01")])).earned
    assert not check(canada_day, Facts(hikes=[hike()])).earned


def test_a_mix_counts_only_dated_hikes_for_seasons():
    seasons = next(m for m in BY_ID.values() if m.rule == "seasons")
    dated = [hike("2025-01-10"), hike("2025-04-10"), hike("2025-07-10")]
    assert set(SEASONS) == {"winter", "spring", "summer", "autumn"}
    assert not check(seasons, Facts(hikes=[*dated, hike(), hike()])).earned
    assert check(seasons, Facts(hikes=[*dated, hike("2025-10-20")])).earned


def test_undated_hikes_are_dated_by_when_they_were_logged_in_the_journal(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    client.post(PAST, json={"trail_ids": trails[:3]}, headers=headers)
    milestones = client.get("/api/me/milestones", headers=headers).json()["milestones"]
    earned = [m for m in milestones if m["earned"]]
    assert earned
    assert all(m["earned_on"] is not None for m in earned)
    assert not any(m["category"] == "seasons" for m in earned)


# ---------------------------------------------------------------- fair use

def test_only_a_few_hikes_can_be_dated_today(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    for trail_id in trails[:TODAY_LIMIT]:
        assert put(client, headers, trail_id, TODAY.isoformat()).status_code == 201
    refused = put(client, headers, trails[TODAY_LIMIT], TODAY.isoformat())
    assert refused.status_code == 429
    assert "another day" in refused.json()["detail"]
    # Yesterday and tomorrow (time zones) count towards the same limit.
    assert put(client, headers, trails[TODAY_LIMIT], "2026-11-02").status_code == 429
    # An older date, or none, is fine.
    assert put(client, headers, trails[TODAY_LIMIT], "2026-10-20").status_code == 201
    assert put(client, headers, trails[TODAY_LIMIT + 1], None).status_code == 201
    # Editing one of today's hikes isn't a new one.
    assert put(client, headers, trails[0], TODAY.isoformat(), note="Windy").status_code == 200


def test_bulk_past_entries_are_unlimited(client, auth_headers, alice, trails):
    headers = auth_headers(alice)
    for trail_id in trails[:TODAY_LIMIT]:
        put(client, headers, trail_id, TODAY.isoformat())
    added = client.post(PAST, json={"trail_ids": trails[TODAY_LIMIT:6]}, headers=headers).json()["added"]
    assert len(added) == 6 - TODAY_LIMIT


# ---------------------------------------------------------------- verification

def verify(session_factory, user, trail_id, hiked_on, nights=None, match=Decimal("0.910")):
    session = session_factory()
    log = session.query(HikeLog).filter_by(user_id=user, trail_id=uuid.UUID(trail_id)).one()
    log.hiked_on, log.verified, log.match_score, log.nights = date.fromisoformat(hiked_on), True, match, nights
    session.commit()
    session.close()


def test_changing_a_verified_hikes_date_drops_verification(client, auth_headers, alice, trails, session_factory):
    headers = auth_headers(alice)
    put(client, headers, trails[0], "2026-08-01")
    verify(session_factory, alice, trails[0], "2026-08-01", nights=2)
    body = client.get("/api/me/hike-logs", headers=headers).json()[0]
    assert (body["verified"], body["nights"]) == (True, 2)

    # A new note keeps it verified...
    assert put(client, headers, trails[0], "2026-08-01", note="Great").json()["verified"] is True
    # ...a new date doesn't.
    moved = put(client, headers, trails[0], "2026-08-05").json()
    assert (moved["verified"], moved["nights"]) == (False, None)


def test_the_client_cannot_mark_a_hike_verified(client, auth_headers, alice, trails):
    response = client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-01", "verified": True},
                          headers=auth_headers(alice))
    assert response.status_code == 422


def test_a_tracks_nights_override_the_trails_typical_nights(client, auth_headers, alice, trails, session_factory, db):
    headers = auth_headers(alice)
    put(client, headers, trails[1], "2026-08-01")  # a day hike on the map
    verify(session_factory, alice, trails[1], "2026-08-01", nights=2)  # but they camped twice
    facts = gather(db, alice)
    assert facts.hikes[0].nights == 2
    assert score(facts).nights > 0
    assert verified_hikes(facts) == facts.hikes


def test_verified_shows_on_public_profiles(client, auth_headers, alice, trails, session_factory):
    headers = auth_headers(alice)
    assert client.patch("/api/me/profile", json={"username": "alice"}, headers=headers).status_code == 200
    assert client.get("/api/me/privacy", headers=headers).json()["show_journal"] is True  # the public defaults
    put(client, headers, trails[0], "2026-08-01")
    client.post(PAST, json={"trail_ids": [trails[1]]}, headers=headers)
    verify(session_factory, alice, trails[0], "2026-08-01")
    entries = client.get("/api/profiles/alice").json()["journal"]["entries"]
    assert [(e["hiked_on"], e["verified"]) for e in entries] == [("2026-08-01", True), (None, False)]
