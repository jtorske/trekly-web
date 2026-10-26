import uuid
from datetime import date, datetime, timezone

import pytest

from app.main import app
from app.models.trail import Trail
from app.routers.availability import get_today

TODAY = date(2026, 10, 26)


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = [
        Trail(name="Berg Lake Trail", region="Mount Robson Provincial Park, BC", country_code="CA", province_code="BC", terrain_difficulty="moderate", typical_duration_nights=3),
        Trail(name="Lost Coast Trail", region="California", country_code="US", province_code="CA", terrain_difficulty="moderate",
              retired_at=datetime(2026, 10, 1, tzinfo=timezone.utc)),
    ]
    session.add_all(rows)
    session.commit()
    ids = [str(row.id) for row in rows]
    session.close()
    app.dependency_overrides[get_today] = lambda: TODAY
    return ids


@pytest.fixture
def alice():
    return uuid.uuid4()


@pytest.fixture
def bob():
    return uuid.uuid4()


def photo(user, extension="webp"):
    return f"{user}/{uuid.uuid4()}.{extension}"


def test_log_edit_and_remove_a_hike(client, auth_headers, alice, trails):
    berg = trails[0]
    created = client.put(
        f"/api/me/hike-logs/{berg}",
        json={"hiked_on": "2026-08-14", "note": "  Clear skies at Berg Glacier.  "},
        headers=auth_headers(alice),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["trail"]["name"] == "Berg Lake Trail"
    assert body["hiked_on"] == "2026-08-14"
    assert body["note"] == "Clear skies at Berg Glacier."
    assert body["photo_path"] is None

    picture = photo(alice)
    edited = client.put(
        f"/api/me/hike-logs/{berg}",
        json={"hiked_on": "2026-08-15", "photo_path": picture},
        headers=auth_headers(alice),
    )
    assert edited.status_code == 200
    # A PUT replaces the entry: the omitted note is cleared.
    assert edited.json()["note"] is None
    assert edited.json()["photo_path"] == picture

    logs = client.get("/api/me/hike-logs", headers=auth_headers(alice)).json()
    assert [(log["trail"]["id"], log["hiked_on"]) for log in logs] == [(berg, "2026-08-15")]

    assert client.delete(f"/api/me/hike-logs/{berg}", headers=auth_headers(alice)).status_code == 204
    assert client.get("/api/me/hike-logs", headers=auth_headers(alice)).json() == []
    # Idempotent.
    assert client.delete(f"/api/me/hike-logs/{berg}", headers=auth_headers(alice)).status_code == 204


def test_list_is_newest_hike_first(client, auth_headers, alice, session_factory, trails):
    session = session_factory()
    extra = Trail(name="Skyline Trail", region="Jasper National Park, AB", country_code="CA", province_code="AB", terrain_difficulty="moderate")
    session.add(extra)
    session.commit()
    extra_id = str(extra.id)
    session.close()
    client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2025-07-01"}, headers=auth_headers(alice))
    client.put(f"/api/me/hike-logs/{extra_id}", json={"hiked_on": "2026-07-01"}, headers=auth_headers(alice))
    logs = client.get("/api/me/hike-logs", headers=auth_headers(alice)).json()
    assert [log["trail"]["name"] for log in logs] == ["Skyline Trail", "Berg Lake Trail"]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"hiked_on": "2026-10-28"}, "future"),
        ({"hiked_on": "1899-12-31"}, "1900"),
        ({"hiked_on": "2026-08-14", "note": "x" * 501}, None),
        ({"hiked_on": "not a date"}, None),
        ({"hiked_on": "2026-08-14", "user_id": str(uuid.uuid4())}, None),
        ({}, None),
    ],
)
def test_validation(client, auth_headers, alice, trails, payload, message):
    response = client.put(f"/api/me/hike-logs/{trails[0]}", json=payload, headers=auth_headers(alice))
    assert response.status_code == 422
    if message:
        assert message in response.json()["detail"]


def test_tomorrow_is_allowed_for_users_ahead_of_the_server(client, auth_headers, alice, trails):
    response = client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-10-27"}, headers=auth_headers(alice))
    assert response.status_code == 201


def test_blank_note_is_stored_as_none(client, auth_headers, alice, trails):
    response = client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-14", "note": "   "}, headers=auth_headers(alice))
    assert response.json()["note"] is None


@pytest.mark.parametrize("name", ["photo.png", "{uuid}.png", "{uuid}.webp.exe", "nested/{uuid}.webp", "../{uuid}.webp"])
def test_photo_must_be_a_processed_upload(client, auth_headers, alice, trails, name):
    path = f"{alice}/{name.format(uuid=uuid.uuid4())}"
    response = client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-14", "photo_path": path}, headers=auth_headers(alice))
    assert response.status_code == 422


def test_cannot_point_an_entry_at_another_users_photo(client, auth_headers, alice, bob, trails):
    response = client.put(
        f"/api/me/hike-logs/{trails[0]}",
        json={"hiked_on": "2026-08-14", "photo_path": photo(bob)},
        headers=auth_headers(alice),
    )
    assert response.status_code == 422


def test_unknown_trail_is_404(client, auth_headers, alice, trails):
    response = client.put(f"/api/me/hike-logs/{uuid.uuid4()}", json={"hiked_on": "2026-08-14"}, headers=auth_headers(alice))
    assert response.status_code == 404


def test_retired_trail_keeps_existing_entries_but_takes_no_new_ones(client, auth_headers, alice, bob, session_factory, trails):
    lost_coast = trails[1]
    assert client.put(f"/api/me/hike-logs/{lost_coast}", json={"hiked_on": "2026-08-14"}, headers=auth_headers(alice)).status_code == 409

    # An entry made before the trail retired is still listed and editable.
    session = session_factory()
    trail = session.get(Trail, uuid.UUID(lost_coast))
    trail.retired_at = None
    session.commit()
    client.put(f"/api/me/hike-logs/{lost_coast}", json={"hiked_on": "2026-05-01"}, headers=auth_headers(alice))
    trail.retired_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    session.commit()
    session.close()

    logs = client.get("/api/me/hike-logs", headers=auth_headers(alice)).json()
    assert logs[0]["trail"]["name"] == "Lost Coast Trail"
    assert logs[0]["trail"]["retired_at"] is not None
    edited = client.put(f"/api/me/hike-logs/{lost_coast}", json={"hiked_on": "2026-05-02", "note": "Black sand"}, headers=auth_headers(alice))
    assert edited.status_code == 200
    assert client.put(f"/api/me/hike-logs/{lost_coast}", json={"hiked_on": "2026-05-02"}, headers=auth_headers(bob)).status_code == 409


def test_users_cannot_see_or_change_each_others_entries(client, auth_headers, alice, bob, trails):
    berg = trails[0]
    client.put(f"/api/me/hike-logs/{berg}", json={"hiked_on": "2026-08-14", "note": "Alice's"}, headers=auth_headers(alice))

    assert client.get("/api/me/hike-logs", headers=auth_headers(bob)).json() == []
    # Bob's PUT creates Bob's own entry; Alice's is untouched.
    assert client.put(f"/api/me/hike-logs/{berg}", json={"hiked_on": "2026-01-01"}, headers=auth_headers(bob)).status_code == 201
    assert client.delete(f"/api/me/hike-logs/{berg}", headers=auth_headers(bob)).status_code == 204

    logs = client.get("/api/me/hike-logs", headers=auth_headers(alice)).json()
    assert [(log["hiked_on"], log["note"]) for log in logs] == [("2026-08-14", "Alice's")]


def test_hike_log_endpoints_require_auth(client, trails):
    assert client.get("/api/me/hike-logs").status_code == 401
    assert client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-14"}).status_code == 401
    assert client.delete(f"/api/me/hike-logs/{trails[0]}").status_code == 401


def test_account_deletion_removes_only_own_entries(client, auth_headers, alice, bob, trails):
    for user in (alice, bob):
        client.put(f"/api/me/hike-logs/{trails[0]}", json={"hiked_on": "2026-08-14"}, headers=auth_headers(user))
    assert client.request("DELETE", "/api/me", json={"confirm": "delete my account"}, headers=auth_headers(alice)).status_code == 204
    assert client.get("/api/me/hike-logs", headers=auth_headers(alice)).json() == []
    assert len(client.get("/api/me/hike-logs", headers=auth_headers(bob)).json()) == 1
