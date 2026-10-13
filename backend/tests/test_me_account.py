import uuid

import pytest

from app.models.trail import Trail


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = [
        Trail(name="Berg Lake Trail", region="BC", terrain_difficulty="moderate", typical_duration_nights=3, elevation_gain_m=800),
        Trail(name="Lost Coast Trail", region="California", terrain_difficulty="moderate"),
    ]
    session.add_all(rows)
    session.commit()
    ids = [str(row.id) for row in rows]
    session.close()
    return ids


@pytest.fixture
def alice():
    return uuid.uuid4()


@pytest.fixture
def bob():
    return uuid.uuid4()


@pytest.fixture
def headers(make_token):
    def _headers(user_id, email=None):
        return {"Authorization": f"Bearer {make_token(user_id, email=email)}"}

    return _headers


def test_profile_is_created_on_first_read_with_sensible_defaults(client, headers, alice):
    response = client.get("/api/me/profile", headers=headers(alice, "alice@example.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(alice)
    assert body["email"] == "alice@example.com"
    assert body["display_name"] is None and body["username"] is None
    assert body["counts"] == {"saved_trails": 0, "gear_items": 0}
    assert body["visibility"] == "private"
    assert body["member_since"]
    # Idempotent: a second read doesn't create a duplicate.
    assert client.get("/api/me/profile", headers=headers(alice)).json()["id"] == str(alice)


def test_update_profile_persists_and_validates(client, headers, alice):
    updated = client.patch(
        "/api/me/profile",
        json={"display_name": "  Alice   Trail ", "username": "Alice_Hikes", "bio": " Peak bagger ", "home_region": "Cascades"},
        headers=headers(alice),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["display_name"] == "Alice Trail"
    assert body["username"] == "alice_hikes"
    assert body["bio"] == "Peak bagger"

    again = client.get("/api/me/profile", headers=headers(alice)).json()
    assert again["username"] == "alice_hikes" and again["home_region"] == "Cascades"

    cleared = client.patch("/api/me/profile", json={"bio": "", "home_region": None}, headers=headers(alice)).json()
    assert cleared["bio"] is None and cleared["home_region"] is None
    assert cleared["display_name"] == "Alice Trail"  # untouched fields stay


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab"},
        {"username": "has space"},
        {"username": "x" * 31},
        {"display_name": "x" * 61},
        {"bio": "x" * 281},
        {"avatar_path": "someone-else/avatar.png"},
        {"email": "new@example.com"},
        {"id": str(uuid.uuid4())},
    ],
)
def test_profile_validation(client, headers, alice, payload):
    assert client.patch("/api/me/profile", json=payload, headers=headers(alice)).status_code == 422


def test_username_must_be_unique(client, headers, alice, bob):
    assert client.patch("/api/me/profile", json={"username": "trailname"}, headers=headers(alice)).status_code == 200
    clash = client.patch("/api/me/profile", json={"username": "TrailName"}, headers=headers(bob))
    assert clash.status_code == 409
    # Re-saving your own username is fine.
    assert client.patch("/api/me/profile", json={"username": "trailname"}, headers=headers(alice)).status_code == 200


def test_own_avatar_path_accepted(client, headers, alice):
    path = f"{alice}/{uuid.uuid4()}.webp"
    response = client.patch("/api/me/profile", json={"avatar_path": path}, headers=headers(alice))
    assert response.status_code == 200 and response.json()["avatar_path"] == path


def test_save_and_unsave_trails(client, headers, alice, trails):
    first = client.put(f"/api/me/saved-trails/{trails[0]}", headers=headers(alice))
    assert first.status_code == 201
    assert first.json()["trail"]["name"] == "Berg Lake Trail"
    duplicate = client.put(f"/api/me/saved-trails/{trails[0]}", headers=headers(alice))
    assert duplicate.status_code == 200  # idempotent double-click
    client.put(f"/api/me/saved-trails/{trails[1]}", headers=headers(alice))

    saved = client.get("/api/me/saved-trails", headers=headers(alice)).json()
    assert {s["trail"]["name"] for s in saved} == {"Berg Lake Trail", "Lost Coast Trail"}
    assert client.get("/api/me/profile", headers=headers(alice)).json()["counts"]["saved_trails"] == 2

    assert client.delete(f"/api/me/saved-trails/{trails[0]}", headers=headers(alice)).status_code == 204
    assert client.delete(f"/api/me/saved-trails/{trails[0]}", headers=headers(alice)).status_code == 204
    saved = client.get("/api/me/saved-trails", headers=headers(alice)).json()
    assert [s["trail"]["name"] for s in saved] == ["Lost Coast Trail"]


def test_saving_unknown_trail_is_404(client, headers, alice, trails):
    assert client.put(f"/api/me/saved-trails/{uuid.uuid4()}", headers=headers(alice)).status_code == 404
    assert client.put("/api/me/saved-trails/not-a-uuid", headers=headers(alice)).status_code == 422


def test_users_cannot_see_or_change_each_others_account_data(client, headers, alice, bob, trails):
    client.patch("/api/me/profile", json={"display_name": "Alice", "bio": "secret plans"}, headers=headers(alice))
    client.put(f"/api/me/saved-trails/{trails[0]}", headers=headers(alice))

    bob_profile = client.get("/api/me/profile", headers=headers(bob)).json()
    assert bob_profile["id"] == str(bob) and bob_profile["bio"] is None
    assert client.get("/api/me/saved-trails", headers=headers(bob)).json() == []

    # Bob "unsaving" Alice's trail only affects Bob's (empty) bookmarks.
    assert client.delete(f"/api/me/saved-trails/{trails[0]}", headers=headers(bob)).status_code == 204
    assert len(client.get("/api/me/saved-trails", headers=headers(alice)).json()) == 1


def test_account_endpoints_require_auth(client, trails):
    assert client.get("/api/me/profile").status_code == 401
    assert client.patch("/api/me/profile", json={}).status_code == 401
    assert client.get("/api/me/saved-trails").status_code == 401
    assert client.put(f"/api/me/saved-trails/{trails[0]}").status_code == 401
    assert client.request("DELETE", "/api/me", json={"confirm": "delete my account"}).status_code == 401


def test_delete_account_requires_confirmation_and_removes_only_own_data(client, headers, alice, bob, trails):
    for user in (alice, bob):
        client.patch("/api/me/profile", json={"display_name": "Hiker"}, headers=headers(user))
        client.put(f"/api/me/saved-trails/{trails[0]}", headers=headers(user))
        client.post("/api/me/gear", json={"custom_name": "Mug", "category": "utensils"}, headers=headers(user))

    wrong = client.request("DELETE", "/api/me", json={"confirm": "yes"}, headers=headers(alice))
    assert wrong.status_code == 422
    assert client.get("/api/me/gear", headers=headers(alice)).json()["items"]

    gone = client.request("DELETE", "/api/me", json={"confirm": "Delete my account"}, headers=headers(alice))
    assert gone.status_code == 204
    assert client.get("/api/me/gear", headers=headers(alice)).json()["items"] == []
    assert client.get("/api/me/saved-trails", headers=headers(alice)).json() == []

    # Bob's data and the shared catalogue are untouched.
    assert len(client.get("/api/me/gear", headers=headers(bob)).json()["items"]) == 1
    assert len(client.get("/api/me/saved-trails", headers=headers(bob)).json()) == 1
    assert client.get("/api/gear/products").json()["total"] == 4
