import uuid

import pytest


@pytest.fixture
def alice():
    return uuid.uuid4()


@pytest.fixture
def bob():
    return uuid.uuid4()


def add(client, headers, **payload):
    response = client.post("/api/me/gear", json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()


def test_create_list_update_delete_setup(client, auth_headers, alice):
    headers = auth_headers(alice)
    stove = client.get("/api/gear/products", params={"q": "pocketrocket"}).json()["items"][0]
    stove_item = add(client, headers, product_id=stove["id"])
    pot = add(client, headers, custom_name="Old pot", category="cookware")

    created = client.post(
        "/api/me/setups",
        json={"name": "  Ultralight   2-Night Kit ", "description": "Summer only", "item_ids": [stove_item["id"], pot["id"], stove_item["id"]]},
        headers=headers,
    )
    assert created.status_code == 201
    setup = created.json()
    assert setup["name"] == "Ultralight 2-Night Kit"
    assert [i["id"] for i in setup["items"]] == [stove_item["id"], pot["id"]]  # deduped, ordered
    assert setup["known_weight_g"] == 83.0 and setup["items_missing_weight"] == 1

    listed = client.get("/api/me/setups", headers=headers).json()
    assert [s["name"] for s in listed] == ["Ultralight 2-Night Kit"]

    updated = client.patch(
        f"/api/me/setups/{setup['id']}", json={"item_ids": [pot["id"]], "name": "Kitchen"}, headers=headers
    ).json()
    assert updated["name"] == "Kitchen" and updated["item_count"] == 1

    # Removing gear from the inventory removes it from setups too.
    assert client.delete(f"/api/me/gear/{pot['id']}", headers=headers).status_code == 204
    assert client.get("/api/me/setups", headers=headers).json()[0]["item_count"] == 0

    assert client.delete(f"/api/me/setups/{setup['id']}", headers=headers).status_code == 204
    assert client.get("/api/me/setups", headers=headers).json() == []
    # Deleting a setup never deletes gear.
    assert len(client.get("/api/me/gear", headers=headers).json()["items"]) == 1


def test_setup_names_unique_per_user_case_insensitive(client, auth_headers, alice, bob):
    assert client.post("/api/me/setups", json={"name": "Desert"}, headers=auth_headers(alice)).status_code == 201
    assert client.post("/api/me/setups", json={"name": "desert"}, headers=auth_headers(alice)).status_code == 409
    assert client.post("/api/me/setups", json={"name": "Desert"}, headers=auth_headers(bob)).status_code == 201


@pytest.mark.parametrize("payload", [{"name": ""}, {"name": "x" * 81}, {"name": "ok", "description": "x" * 501}, {"name": "ok", "user_id": str(uuid.uuid4())}])
def test_setup_validation(client, auth_headers, alice, payload):
    assert client.post("/api/me/setups", json=payload, headers=auth_headers(alice)).status_code == 422


def test_setups_are_private_and_cannot_include_others_gear(client, auth_headers, alice, bob):
    alice_item = add(client, auth_headers(alice), custom_name="Alice quilt", category="quilts")
    alice_setup = client.post("/api/me/setups", json={"name": "A", "item_ids": [alice_item["id"]]}, headers=auth_headers(alice)).json()

    bob_headers = auth_headers(bob)
    assert client.get("/api/me/setups", headers=bob_headers).json() == []
    assert client.patch(f"/api/me/setups/{alice_setup['id']}", json={"name": "Mine"}, headers=bob_headers).status_code == 404
    assert client.delete(f"/api/me/setups/{alice_setup['id']}", headers=bob_headers).status_code == 404
    stolen = client.post("/api/me/setups", json={"name": "B", "item_ids": [alice_item["id"]]}, headers=bob_headers)
    assert stolen.status_code == 422
    assert client.post("/api/me/setups", json={"name": "B", "item_ids": [str(uuid.uuid4())]}, headers=bob_headers).status_code == 422
    assert client.get("/api/me/setups", headers=auth_headers(alice)).json()[0]["item_count"] == 1


def test_setups_require_auth(client):
    assert client.get("/api/me/setups").status_code == 401
    assert client.post("/api/me/setups", json={"name": "x"}).status_code == 401
