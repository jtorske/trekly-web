import uuid

import pytest


@pytest.fixture
def alice():
    return uuid.uuid4()


@pytest.fixture
def bob():
    return uuid.uuid4()


def product(client, q):
    return client.get("/api/gear/products", params={"q": q}).json()["items"][0]


def detail(client, product_id):
    return client.get(f"/api/gear/products/{product_id}").json()


def test_full_crud_with_catalogue_product(client, auth_headers, alice):
    headers = auth_headers(alice)
    tent = product(client, "copper spur")

    created = client.post("/api/me/gear", json={"product_id": tent["id"]}, headers=headers)
    assert created.status_code == 201
    item = created.json()
    assert item["kind"] == "catalog"
    assert item["display_name"] == "Big Agnes Copper Spur HV UL2"
    assert item["category"]["top_slug"] == "shelter"
    assert item["weight"] == {
        "effective_g": 1304.078,
        "source": "product",
        "manufacturer_g": 1304.078,
        "manufacturer_basis": "minimum",
        "override_g": None,
        "override_unit": None,
    }

    updated = client.patch(
        f"/api/me/gear/{item['id']}",
        json={
            "quantity": 2,
            "notes": "Seam-sealed 2026",
            "condition": "good",
            "weight_override": {"value": "2.9", "unit": "lb"},
        },
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["quantity"] == 2 and body["condition"] == "good"
    assert body["weight"]["source"] == "override"
    assert body["weight"]["override_g"] == 1315.418
    assert body["weight"]["override_unit"] == "lb"
    assert body["weight"]["manufacturer_g"] == 1304.078  # provenance preserved

    collection = client.get("/api/me/gear", headers=headers).json()
    assert len(collection["items"]) == 1
    assert collection["summary"]["known_weight_g"] == pytest.approx(2630.836)
    assert collection["summary"]["weight_is_complete"] is True
    assert collection["summary"]["categories_with_items"] == ["shelter"]

    cleared = client.patch(
        f"/api/me/gear/{item['id']}", json={"weight_override": None, "notes": None}, headers=headers
    ).json()
    assert cleared["weight"]["source"] == "product" and cleared["notes"] is None

    assert client.delete(f"/api/me/gear/{item['id']}", headers=headers).status_code == 204
    assert client.get("/api/me/gear", headers=headers).json()["items"] == []
    assert client.delete(f"/api/me/gear/{item['id']}", headers=headers).status_code == 404


def test_variant_selection_and_validation(client, auth_headers, alice):
    headers = auth_headers(alice)
    pad = detail(client, product(client, "tensor")["id"])
    long_wide = pad["variants"][1]

    created = client.post(
        "/api/me/gear",
        json={"product_id": pad["id"], "variant_id": long_wide["id"]},
        headers=headers,
    ).json()
    assert created["display_name"] == "NEMO Tensor All-Season (Long Wide)"
    assert created["weight"]["source"] == "variant"
    assert created["weight"]["effective_g"] == 566.99

    stove = product(client, "pocketrocket")
    mismatch = client.post(
        "/api/me/gear",
        json={"product_id": stove["id"], "variant_id": long_wide["id"]},
        headers=headers,
    )
    assert mismatch.status_code == 422
    missing = client.post(
        "/api/me/gear", json={"product_id": str(uuid.uuid4())}, headers=headers
    )
    assert missing.status_code == 422


def test_custom_item_with_unknown_weight(client, auth_headers, alice):
    headers = auth_headers(alice)
    created = client.post(
        "/api/me/gear",
        json={
            "custom_name": "  Grandpa's   wool blanket ",
            "custom_brand": "Unknown",
            "category": "sleep",
            "notes": "Heavy but warm",
        },
        headers=headers,
    )
    assert created.status_code == 201
    item = created.json()
    assert item["kind"] == "custom"
    assert item["display_name"] == "Grandpa's wool blanket"
    assert item["weight"]["effective_g"] is None and item["weight"]["source"] is None

    summary = client.get("/api/me/gear", headers=headers).json()["summary"]
    assert summary["items_missing_weight"] == 1
    assert summary["weight_is_complete"] is False
    assert summary["known_weight_g"] == 0


def test_custom_item_specs_and_capacity(client, auth_headers, alice):
    created = client.post(
        "/api/me/gear",
        json={
            "custom_name": "Old frame pack",
            "category": "backpacks",
            "capacity_override": {"value": "65", "unit": "l"},
            "custom_specs": {"frame_type": "external"},
            "weight_override": {"value": "4", "unit": "lb"},
        },
        headers=auth_headers(alice),
    )
    assert created.status_code == 201
    item = created.json()
    assert item["capacity"]["effective_ml"] == 65000.0 and item["capacity"]["source"] == "override"
    assert item["custom_specs"] == [
        {"key": "frame_type", "label": "Frame", "value": "external", "unit": None}
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "sleep"},  # no name, no product
        {"custom_name": "   ", "category": "sleep"},
        {"custom_name": "Thing"},  # no category
        {"custom_name": "Thing", "category": "spaceships"},
        {"custom_name": "Thing", "category": "sleep", "quantity": 0},
        {"custom_name": "Thing", "category": "sleep", "quantity": 100},
        {"custom_name": "Thing", "category": "sleep", "weight_override": {"value": "-1", "unit": "g"}},
        {"custom_name": "Thing", "category": "sleep", "weight_override": {"value": "1", "unit": "stone"}},
        {"custom_name": "Thing", "category": "sleeping-pads", "custom_specs": {"r_value": "warm"}},
        {"custom_name": "Thing", "category": "sleep", "condition": "pristine"},
        {"custom_name": "x" * 121, "category": "sleep"},
        {"custom_name": "Thing", "category": "sleep", "user_id": str(uuid.uuid4())},
        {"custom_name": "Thing", "category": "sleep", "image_path": "someone-else/photo.jpg"},
    ],
)
def test_validation_errors(client, auth_headers, alice, payload):
    response = client.post("/api/me/gear", json=payload, headers=auth_headers(alice))
    assert response.status_code == 422, payload


def test_catalogue_items_cannot_carry_custom_brand(client, auth_headers, alice):
    tent = product(client, "copper spur")
    response = client.post(
        "/api/me/gear",
        json={"product_id": tent["id"], "custom_brand": "Fake"},
        headers=auth_headers(alice),
    )
    assert response.status_code == 422


def test_own_photo_path_accepted(client, auth_headers, alice):
    path = f"{alice}/{uuid.uuid4()}.jpg"
    response = client.post(
        "/api/me/gear",
        json={"custom_name": "Mug", "category": "utensils", "image_path": path},
        headers=auth_headers(alice),
    )
    assert response.status_code == 201
    assert response.json()["image_path"] == path


def test_duplicate_submission_is_idempotent(client, auth_headers, alice):
    headers = auth_headers(alice)
    request_id = str(uuid.uuid4())
    payload = {"custom_name": "Spork", "category": "utensils", "client_request_id": request_id}
    first = client.post("/api/me/gear", json=payload, headers=headers)
    second = client.post("/api/me/gear", json=payload, headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/me/gear", headers=headers).json()["items"]) == 1

    # Owning several of the same product is allowed when the user means it.
    third = client.post(
        "/api/me/gear", json={"custom_name": "Spork", "category": "utensils"}, headers=headers
    )
    assert third.status_code == 201
    assert len(client.get("/api/me/gear", headers=headers).json()["items"]) == 2


def test_users_cannot_see_or_change_each_others_gear(client, auth_headers, alice, bob):
    item = client.post(
        "/api/me/gear",
        json={"custom_name": "Alice's quilt", "category": "quilts"},
        headers=auth_headers(alice),
    ).json()

    bob_headers = auth_headers(bob)
    assert client.get("/api/me/gear", headers=bob_headers).json()["items"] == []
    assert client.patch(
        f"/api/me/gear/{item['id']}", json={"quantity": 5}, headers=bob_headers
    ).status_code == 404
    assert client.delete(f"/api/me/gear/{item['id']}", headers=bob_headers).status_code == 404

    # Reusing Alice's client_request_id doesn't leak her item to Bob either.
    request_id = str(uuid.uuid4())
    client.post(
        "/api/me/gear",
        json={"custom_name": "Tarp", "category": "tarps", "client_request_id": request_id},
        headers=auth_headers(alice),
    )
    bobs = client.post(
        "/api/me/gear",
        json={"custom_name": "Bob's tarp", "category": "tarps", "client_request_id": request_id},
        headers=bob_headers,
    )
    assert bobs.status_code == 201 and bobs.json()["display_name"] == "Bob's tarp"

    alice_items = client.get("/api/me/gear", headers=auth_headers(alice)).json()["items"]
    assert [i["display_name"] for i in alice_items] == ["Alice's quilt", "Tarp"]
    assert alice_items[0]["quantity"] == 1


def test_replace_catalogue_product_and_convert_to_custom(client, auth_headers, alice):
    headers = auth_headers(alice)
    tent = product(client, "copper spur")
    stove = product(client, "pocketrocket")
    item = client.post("/api/me/gear", json={"product_id": tent["id"]}, headers=headers).json()

    replaced = client.patch(
        f"/api/me/gear/{item['id']}", json={"product_id": stove["id"]}, headers=headers
    ).json()
    assert replaced["display_name"] == "MSR PocketRocket Deluxe"
    assert replaced["category"]["slug"] == "stoves"

    custom = client.patch(
        f"/api/me/gear/{item['id']}",
        json={"product_id": None, "custom_name": "Homemade alcohol stove", "category": "stoves"},
        headers=headers,
    ).json()
    assert custom["kind"] == "custom" and custom["product"] is None

    nameless = client.patch(
        f"/api/me/gear/{item['id']}", json={"custom_name": None}, headers=headers
    )
    assert nameless.status_code == 422


def test_discontinued_products_stay_in_inventory(client, auth_headers, alice):
    jacket = product(client, "beta ar")
    assert jacket["status"] == "discontinued"
    item = client.post(
        "/api/me/gear", json={"product_id": jacket["id"]}, headers=auth_headers(alice)
    )
    assert item.status_code == 201
    assert item.json()["product"]["status"] == "discontinued"
