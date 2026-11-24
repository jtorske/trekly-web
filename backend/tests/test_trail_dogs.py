"""catalog_data/trail_dogs.json: every rule names an official https source and a real trail."""

import json

import pytest

from app.trail_dogs import DOGS_PATH, DogDataError, load_dogs, validate

CATALOGUE = json.load(open(DOGS_PATH.parent / "trails_canada.json", encoding="utf-8"))["trails"]


def test_file_is_valid_and_matches_the_catalogue():
    dogs = load_dogs()
    names = {(t["name"], t["province_code"]) for t in CATALOGUE}
    assert dogs and set(dogs) <= names
    assert all(d["dog_policy"] in ("on_leash", "not_allowed") and d["dog_policy_source_url"] for d in dogs.values())


def test_known_bans():
    dogs = load_dogs()
    for key in [("Joffre Lakes", "BC"), ("Garibaldi Lake", "BC"), ("West Coast Trail", "BC"), ("Skyline Trail", "AB")]:
        assert dogs[key]["dog_policy"] == "not_allowed", key


@pytest.mark.parametrize("entry", [
    {"name": "X", "province_code": "AB", "dog_policy": "on_leash"},
    {"name": "X", "province_code": "AB", "dog_policy": "on_leash", "dog_policy_source_url": "http://x"},
    {"name": "X", "province_code": "AB", "dog_policy": "sometimes", "dog_policy_source_url": "https://x"},
])
def test_rejects_unsourced_or_unknown_values(entry):
    with pytest.raises(DogDataError):
        validate(entry)
