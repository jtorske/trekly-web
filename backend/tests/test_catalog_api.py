def names(response):
    return [item["display_name"] for item in response.json()["items"]]


def test_categories_tree(client):
    response = client.get("/api/gear/categories")
    assert response.status_code == 200
    tree = response.json()
    assert [c["slug"] for c in tree] == [
        "backpack", "shelter", "sleep", "clothing", "cooking",
        "hydration", "footwear", "navigation", "safety", "accessories",
    ]
    shelter = next(c for c in tree if c["slug"] == "shelter")
    assert "tents" in [s["slug"] for s in shelter["subcategories"]]


def test_search_by_name_brand_alias_and_category(client):
    assert names(client.get("/api/gear/products", params={"q": "copper spur"})) == [
        "Big Agnes Copper Spur HV UL2"
    ]
    assert names(client.get("/api/gear/products", params={"q": "mountain safety research"})) == [
        "MSR PocketRocket Deluxe"
    ]
    assert names(client.get("/api/gear/products", params={"q": "arcteryx"})) == [
        "Arc'teryx Beta AR Jacket"
    ]
    assert names(client.get("/api/gear/products", params={"q": "tensor insulated"})) == [
        "NEMO Tensor All-Season"
    ]
    assert names(client.get("/api/gear/products", params={"q": "long wide"})) == [
        "NEMO Tensor All-Season"
    ]
    assert names(client.get("/api/gear/products", params={"q": "stoves"})) == [
        "MSR PocketRocket Deluxe"
    ]


def test_search_no_results_and_punctuation_only_queries(client):
    response = client.get("/api/gear/products", params={"q": "hovercraft"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "next_cursor": None}
    # Punctuation normalizes away: "%" is a plain browse, not a LIKE wildcard.
    assert names(client.get("/api/gear/products", params={"q": "%_"})) == names(
        client.get("/api/gear/products")
    )


def test_filters(client):
    assert names(client.get("/api/gear/products", params={"category": "sleep"})) == [
        "NEMO Tensor All-Season"
    ]
    assert names(client.get("/api/gear/products", params={"category": "tents"})) == [
        "Big Agnes Copper Spur HV UL2"
    ]
    assert names(client.get("/api/gear/products", params={"brand": "msr"})) == [
        "MSR PocketRocket Deluxe"
    ]
    active = names(client.get("/api/gear/products", params={"include_discontinued": "false"}))
    assert "Arc'teryx Beta AR Jacket" not in active
    assert client.get("/api/gear/products", params={"category": "nope"}).status_code == 404
    assert client.get("/api/gear/products", params={"brand": "nope"}).status_code == 404


def test_pagination_with_cursor(client):
    first = client.get("/api/gear/products", params={"limit": 3}).json()
    assert first["total"] == 4 and len(first["items"]) == 3 and first["next_cursor"]
    second = client.get(
        "/api/gear/products", params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    all_ids = [i["id"] for i in first["items"] + second["items"]]
    assert len(set(all_ids)) == 4
    assert client.get("/api/gear/products", params={"cursor": "garbage!"}).status_code == 400
    assert client.get("/api/gear/products", params={"limit": 500}).status_code == 422


def test_product_summary_and_detail(client):
    pad = client.get("/api/gear/products", params={"q": "tensor"}).json()["items"][0]
    assert pad["weight_g"] is None
    assert pad["weight_range_g"] == [399.728, 566.99]
    assert pad["variant_count"] == 2
    assert pad["image"] is None  # no approved image -> client uses illustration
    assert pad["key_specs"][0] == {"key": "r_value", "label": "R-value", "value": 5.4, "unit": None}

    detail = client.get(f"/api/gear/products/{pad['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert [v["name"] for v in body["variants"]] == ["Regular Mummy", "Long Wide"]
    assert body["variants"][0]["weight_basis"] == "minimum"
    assert body["sources"][0]["url"].startswith("https://www.nemoequipment.com")
    assert body["aliases"] == ["Tensor Insulated"]


def test_product_not_found(client):
    assert client.get("/api/gear/products/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/gear/products/not-a-uuid").status_code == 422


def test_brands(client):
    brands = client.get("/api/gear/brands").json()
    assert [b["name"] for b in brands] == ["Arc'teryx", "Big Agnes", "MSR", "NEMO"]
    assert [b["name"] for b in client.get("/api/gear/brands", params={"q": "nemo equip"}).json()] == ["NEMO"]
    assert [b["name"] for b in client.get("/api/gear/brands", params={"category": "cooking"}).json()] == ["MSR"]


SLOT_CASES = {
    # slot categories -> products that may appear
    "backpacks": set(),
    "tents,tarps,bivy-sacks": {"Big Agnes Copper Spur HV UL2"},
    "sleeping-bags,quilts": set(),
    "sleeping-pads": {"NEMO Tensor All-Season"},
    "rainwear": {"Arc'teryx Beta AR Jacket"},
    "stoves": {"MSR PocketRocket Deluxe"},
}


def test_slot_selectors_only_return_their_categories(client):
    for categories, expected in SLOT_CASES.items():
        body = client.get("/api/gear/products", params={"category": categories, "limit": 50}).json()
        assert set(names_of(body)) == expected, categories
        allowed = set(categories.split(","))
        assert all(item["category"]["slug"] in allowed for item in body["items"]), categories


def names_of(body):
    return [item["display_name"] for item in body["items"]]


def test_unknown_slot_category_is_rejected_not_widened(client):
    assert client.get("/api/gear/products", params={"category": "tents,spaceships"}).status_code == 404
    assert client.get("/api/gear/products", params={"category": ","}).status_code == 404


def test_search_and_slot_filter_combine(client):
    body = client.get("/api/gear/products", params={"category": "stoves", "q": "copper"}).json()
    assert body["items"] == []
    body = client.get("/api/gear/products", params={"category": "stoves", "q": "pocket"}).json()
    assert names_of(body) == ["MSR PocketRocket Deluxe"]


def test_weight_and_capacity_filters_use_variants_and_skip_unknowns(client):
    # NEMO only has variant weights (399.7 g and 567 g); Arc'teryx has none.
    light = client.get("/api/gear/products", params={"max_weight_g": 450}).json()
    assert set(names_of(light)) == {"MSR PocketRocket Deluxe", "NEMO Tensor All-Season"}
    lighter = client.get("/api/gear/products", params={"max_weight_g": 300}).json()
    assert names_of(lighter) == ["MSR PocketRocket Deluxe"]
    assert client.get("/api/gear/products", params={"min_capacity_ml": 1}).json()["items"] == []
    assert client.get("/api/gear/products", params={"max_weight_g": 0}).status_code == 422
