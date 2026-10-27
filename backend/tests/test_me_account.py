import uuid

import pytest

from app.models.trail import Trail


@pytest.fixture
def trails(session_factory, client):
    session = session_factory()
    rows = [
        Trail(name="Berg Lake Trail", region="BC", country_code="CA", province_code="BC", terrain_difficulty="moderate", typical_duration_nights=3, elevation_gain_m=800),
        Trail(name="Lost Coast Trail", region="California", country_code="US", province_code="CA", terrain_difficulty="moderate"),
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
    assert body["units"] is None  # never chosen: the app shows metric
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


def test_units_setting_is_saved_and_returned(client, headers, alice, bob):
    saved = client.patch("/api/me/profile", json={"units": "imperial"}, headers=headers(alice))
    assert saved.status_code == 200
    assert saved.json()["units"] == "imperial"
    # It follows the account, not the request: a fresh read returns it.
    assert client.get("/api/me/profile", headers=headers(alice)).json()["units"] == "imperial"
    # Other profile edits leave it alone.
    client.patch("/api/me/profile", json={"bio": "Hi"}, headers=headers(alice))
    assert client.get("/api/me/profile", headers=headers(alice)).json()["units"] == "imperial"
    assert client.patch("/api/me/profile", json={"units": "metric"}, headers=headers(alice)).json()["units"] == "metric"
    assert client.get("/api/me/profile", headers=headers(bob)).json()["units"] is None


@pytest.mark.parametrize("value", ["us", "Metric", "", 1])
def test_units_setting_rejects_unknown_values(client, headers, alice, value):
    response = client.patch("/api/me/profile", json={"units": value}, headers=headers(alice))
    assert response.status_code == 422


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


def test_avatar_upload_replace_and_remove(client, headers, alice):
    first = f"{alice}/{uuid.uuid4()}.webp"
    assert client.patch("/api/me/profile", json={"avatar_path": first}, headers=headers(alice)).json()["avatar_path"] == first

    # Replacing points the profile at the new file (the client then deletes the old one).
    second = f"{alice}/{uuid.uuid4()}.jpg"
    replaced = client.patch("/api/me/profile", json={"avatar_path": second, "bio": "New photo"}, headers=headers(alice)).json()
    assert replaced["avatar_path"] == second and replaced["bio"] == "New photo"
    assert client.get("/api/me/profile", headers=headers(alice)).json()["avatar_path"] == second

    # Editing other fields leaves the photo alone.
    assert client.patch("/api/me/profile", json={"bio": "Still here"}, headers=headers(alice)).json()["avatar_path"] == second

    removed = client.patch("/api/me/profile", json={"avatar_path": None}, headers=headers(alice)).json()
    assert removed["avatar_path"] is None
    assert client.get("/api/me/profile", headers=headers(alice)).json()["avatar_path"] is None


@pytest.mark.parametrize(
    "name",
    ["{uuid}.png", "{uuid}.jpeg", "avatar.webp", "{uuid}.webp/../x.webp", "nested/{uuid}.webp"],
)
def test_avatar_path_must_be_a_processed_upload(client, headers, alice, name):
    path = f"{alice}/{name.format(uuid=uuid.uuid4())}"
    assert client.patch("/api/me/profile", json={"avatar_path": path}, headers=headers(alice)).status_code == 422


def test_cannot_point_profile_at_another_users_avatar(client, headers, alice, bob):
    path = f"{bob}/{uuid.uuid4()}.webp"
    assert client.patch("/api/me/profile", json={"avatar_path": path}, headers=headers(alice)).status_code == 422


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
