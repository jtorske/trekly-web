"""LighterPack import: reading the CSV, matching items to the catalogue, and
the preview -> confirm flow (nothing is added before the confirm)."""

import uuid
from decimal import Decimal

import pytest

from app.catalog.normalize import normalize_text
from app.gear_import.lighterpack import (
    ImportFileError, Product, Row, guess_category, match_row, parse_csv,
)

PREVIEW = "/api/me/gear/import/lighterpack"
CONFIRM = "/api/me/gear/import/lighterpack/confirm"

HEADER = "Item Name,Category,desc,qty,weight,unit,url,price,worn,consumable\n"


def csv_of(*lines: str) -> str:
    return HEADER + "\n".join(lines) + "\n"


def product(brand, name, category="backpacks", grams=None, aliases=(), brand_aliases=()):
    return Product(
        id=uuid.uuid4(), brand=brand,
        brand_names=tuple(normalize_text(b) for b in (brand, *brand_aliases)),
        name=name, names=tuple(normalize_text(n) for n in (name, *aliases)),
        category=category, weights_g=(Decimal(grams),) if grams else (),
    )


def row(name, desc="", grams=None, category=""):
    return Row(index=0, name=name, category=category, description=desc, quantity=1,
               weight_value=Decimal(grams) if grams else None, weight_unit="g" if grams else None,
               worn=False, consumable=False)


CATALOGUE = [
    product("Osprey", "Exos 58", grams=1130),
    product("Osprey", "Exos 38", grams=1050),
    product("Osprey", "Exos Pro 55", grams=850),
    product("Osprey", "Atmos AG 65", grams=2080),
    product("Osprey", "Atmos AG LT 65", grams=1880),
    product("Zpacks", "Duplex", category="tents", grams=539),
    product("Gossamer Gear", "Mariposa 60", grams=907),
    product("MSR", "PocketRocket Deluxe", category="stoves", grams=83, brand_aliases=("Mountain Safety Research",)),
]


# ---------------------------------------------------------------- parsing

def test_reads_a_lighterpack_export():
    rows = parse_csv(
        "﻿" + csv_of(
            "Exos 58,Pack,Osprey,1,1130,gram,,,,",
            "Rain jacket,Clothing,Frogg Toggs,1,6.2,ounce,,,Worn,",
            "Dinners,Food,,3,0.5,pound,,,,Consumable",
            ",,blank names are skipped,1,10,gram,,,,",
        )
    )
    assert [(r.name, r.quantity, r.weight_unit, r.carry) for r in rows] == [
        ("Exos 58", 1, "g", None), ("Rain jacket", 1, "oz", "worn"), ("Dinners", 3, "lb", "consumable"),
    ]
    assert rows[1].weight_g == Decimal("6.2") * Decimal("28.349523125")


@pytest.mark.parametrize("text, message", [
    ("", "empty"),
    ("name,colour\nTent,green\n", "LighterPack export"),
    (HEADER, "no items"),
])
def test_refuses_files_that_are_not_an_export(text, message):
    with pytest.raises(ImportFileError, match=message):
        parse_csv(text)


# ---------------------------------------------------------------- matching

def test_brand_and_full_name_is_a_high_confidence_match():
    match = match_row(row("Osprey Exos 58", grams=1135), CATALOGUE)
    assert match.best.product.name == "Exos 58"
    assert match.best.confidence == "high"


def test_a_different_model_number_is_not_the_match():
    match = match_row(row("Exos Pro 55", "Osprey"), CATALOGUE)
    assert match.best.product.name == "Exos Pro 55"
    assert "Exos 58" not in [c.product.name for c in match.alternatives[:1]] or match.alternatives[0].score < match.best.score


def test_the_longer_name_wins_a_tie():
    assert match_row(row("Osprey Atmos AG LT 65"), CATALOGUE).best.product.name == "Atmos AG LT 65"
    assert match_row(row("Osprey Atmos AG 65"), CATALOGUE).best.product.name == "Atmos AG 65"


def test_brand_aliases_count():
    match = match_row(row("Mountain Safety Research PocketRocket Deluxe"), CATALOGUE)
    assert (match.best.product.name, match.best.confidence) == ("PocketRocket Deluxe", "high")


def test_naming_another_brand_rules_a_product_out():
    match = match_row(row("Duplex", "Big Agnes copy"), CATALOGUE)
    assert match.best is not None and match.best.product.name == "Duplex"  # no other brand named
    other = match_row(row("Gossamer Gear Duplex"), CATALOGUE)
    assert other.best is None or other.best.confidence == "low"


def test_a_far_off_weight_lowers_confidence():
    close = match_row(row("Zpacks Duplex", grams=540), CATALOGUE).best
    far = match_row(row("Zpacks Duplex", grams=2400), CATALOGUE).best
    assert close.score > far.score


def test_unmatched_items_get_a_category_guess():
    match = match_row(row("Smartwater bottle 1L", category="Water"), CATALOGUE)
    assert match.best is None
    assert match.category == "bottles-reservoirs"
    assert guess_category(row("Headlamp")) == "lighting"
    assert guess_category(row("Thing", category="Sleep system")) == "sleeping-bags"
    assert guess_category(row("Mystery item")) == "misc"


# ---------------------------------------------------------------- the flow

@pytest.fixture
def alice():
    return uuid.uuid4()


EXPORT = csv_of(
    "Copper Spur HV UL2,Shelter,Big Agnes,1,3.2,pound,,,,",
    "PocketRocket Deluxe,Kitchen,MSR,1,83,gram,,,,",
    "Homemade windscreen,Kitchen,foil,1,12,gram,,,,",
    "Trail mix,Food,,2,200,gram,,,,Consumable",
)


def gear(client, headers):
    return client.get("/api/me/gear", headers=headers).json()["items"]


def test_preview_proposes_matches_and_adds_nothing(client, auth_headers, alice):
    headers = auth_headers(alice)
    response = client.post(PREVIEW, json={"csv": EXPORT}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    rows = body["rows"]
    assert rows[0]["match"]["product"]["display_name"] == "Big Agnes Copper Spur HV UL2"
    assert rows[0]["match"]["confidence"] == "high"
    assert rows[1]["match"]["product"]["name"] == "PocketRocket Deluxe"
    assert rows[2]["match"] is None and rows[2]["category"] == "fuel-accessories"
    # Food is offered but not ticked.
    assert [r["include"] for r in rows] == [True, True, True, False]
    assert (body["matched"], body["unmatched"]) == (2, 2)
    assert gear(client, headers) == []


def test_preview_explains_a_bad_file(client, auth_headers, alice):
    response = client.post(PREVIEW, json={"csv": "just,some\ncolumns,here\n"}, headers=auth_headers(alice))
    assert response.status_code == 422
    assert "Export to CSV" in response.json()["detail"]


def confirm_payload(rows, import_id):
    items = []
    for r in rows:
        if not r["include"]:
            continue
        item = {"index": r["index"], "quantity": r["quantity"], "weight": r["weight"], "carry": r["carry"]}
        if r["match"]:
            item["product_id"] = r["match"]["product"]["id"]
        else:
            item.update(name=r["name"], category=r["category"], notes=r["description"] or None)
        items.append(item)
    return {"import_id": str(import_id), "items": items}


def test_confirm_adds_matches_and_custom_items_once(client, auth_headers, alice):
    headers = auth_headers(alice)
    rows = client.post(PREVIEW, json={"csv": EXPORT}, headers=headers).json()["rows"]
    payload = confirm_payload(rows, uuid.uuid4())

    done = client.post(CONFIRM, json=payload, headers=headers)
    assert done.status_code == 201
    assert done.json() == {"added": 3, "already_added": 0}
    items = {item["display_name"]: item for item in gear(client, headers)}
    assert set(items) == {"Big Agnes Copper Spur HV UL2", "MSR PocketRocket Deluxe", "Homemade windscreen"}
    # Their own scale's weight is kept when it differs from the catalogue's...
    tent = items["Big Agnes Copper Spur HV UL2"]["weight"]
    assert tent["source"] == "override" and tent["override_unit"] == "lb"
    # ...and not when it's the same.
    assert items["MSR PocketRocket Deluxe"]["weight"]["source"] == "product"
    assert items["Homemade windscreen"]["weight"]["effective_g"] == 12
    assert items["Homemade windscreen"]["kind"] == "custom"

    # Retrying the same import adds nothing.
    again = client.post(CONFIRM, json=payload, headers=headers).json()
    assert again == {"added": 0, "already_added": 3}
    assert len(gear(client, headers)) == 3


def test_one_bad_item_adds_none(client, auth_headers, alice):
    headers = auth_headers(alice)
    payload = {"import_id": str(uuid.uuid4()), "items": [
        {"index": 0, "name": "Good item", "category": "misc"},
        {"index": 1, "name": "Bad item", "category": "no-such-category"},
    ]}
    response = client.post(CONFIRM, json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Item 2:")
    assert gear(client, headers) == []


def test_confirm_rejects_repeated_rows_and_unknown_products(client, auth_headers, alice):
    headers = auth_headers(alice)
    twice = {"import_id": str(uuid.uuid4()), "items": [{"index": 0, "name": "A", "category": "misc"}] * 2}
    assert client.post(CONFIRM, json=twice, headers=headers).status_code == 422
    ghost = {"import_id": str(uuid.uuid4()), "items": [{"index": 0, "product_id": str(uuid.uuid4())}]}
    assert client.post(CONFIRM, json=ghost, headers=headers).status_code == 422
    assert client.post(PREVIEW, json={"csv": EXPORT}).status_code == 401


def test_generic_words_alone_are_not_a_match():
    catalogue = [product("Zpacks", "Vertice Rain Jacket", category="rainwear", grams=170)]
    match = match_row(row("Frogg Toggs rain jacket"), catalogue)
    assert match.best is None and match.category == "rainwear"


def test_numbers_with_units_compare_as_numbers():
    catalogue = [product("TOAKS", "Titanium 750ml Pot", category="cookware", grams=103)]
    assert match_row(row("Toaks 750 pot"), catalogue).best.confidence == "high"


def test_a_name_that_fits_several_products_is_at_most_medium():
    catalogue = [
        product("NEMO", "Tensor Trail", category="sleeping-pads", grams=425),
        product("NEMO", "Tensor Elite", category="sleeping-pads", grams=240),
        product("NEMO", "Tensor All-Season", category="sleeping-pads", grams=440),
    ]
    match = match_row(row("Nemo Tensor", grams=425), catalogue)
    assert match.best.product.name == "Tensor Trail"
    assert match.best.confidence == "medium"
    assert {c.product.name for c in match.alternatives} <= {"Tensor Elite", "Tensor All-Season"}


def test_a_contradicting_model_number_is_only_an_alternative():
    match = match_row(row("Osprey Exos 48", grams=1180), CATALOGUE)
    assert match.best is None
    assert {c.product.name for c in match.alternatives} >= {"Exos 38"}
