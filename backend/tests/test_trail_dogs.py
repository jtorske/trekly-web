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
    for key in [("Joffre Lakes", "BC"), ("Garibaldi Lake", "BC"), ("West Coast Trail", "BC"), ("Skyline Trail", "AB"),
                ("Grouse Grind", "BC"), ("Eva Lake", "BC"), ("Jade Lakes", "BC")]:
        assert dogs[key]["dog_policy"] == "not_allowed", key


@pytest.mark.parametrize("entry", [
    {"name": "X", "province_code": "AB", "dog_policy": "on_leash"},
    {"name": "X", "province_code": "AB", "dog_policy": "on_leash", "dog_policy_source_url": "http://x"},
    {"name": "X", "province_code": "AB", "dog_policy": "sometimes", "dog_policy_source_url": "https://x"},
])
def test_rejects_unsourced_or_unknown_values(entry):
    with pytest.raises(DogDataError):
        validate(entry)


def test_rules_need_a_checked_on_date_and_expiry_after_it():
    base = {"name": "X", "province_code": "AB", "dog_policy": "on_leash", "dog_policy_source_url": "https://x"}
    with pytest.raises(DogDataError):
        validate(base)
    with pytest.raises(DogDataError):
        validate({**base, "checked_on": "2026-11-24", "expires_on": "2026-01-01"})
    rule = validate({**base, "checked_on": "2026-11-24", "expires_on": "2026-12-31"})
    assert rule["expires_on"].isoformat() == "2026-12-31"


def test_every_rule_has_its_source_and_checked_on():
    assert all(r["dog_policy_source_url"] and r["checked_on"] for r in load_dogs().values())


def test_expired_rule_falls_back_to_unknown_never_allowed():
    from datetime import date

    from app.trail_dogs import effective_policy, expired_rules

    skyline = load_dogs()[("Skyline Trail", "AB")]
    assert skyline["dog_policy"] == "not_allowed" and skyline["expires_on"] == date(2026, 12, 31)
    assert effective_policy("Skyline Trail", "AB", "not_allowed", date(2026, 12, 31)) == "not_allowed"
    assert effective_policy("Skyline Trail", "AB", "not_allowed", date(2027, 1, 1)) == "unknown"
    # An expiring on-leash rule also falls back to unknown, not to allowed.
    dogs = {("Y", "AB"): validate({"name": "Y", "province_code": "AB", "dog_policy": "on_leash",
                                   "dog_policy_source_url": "https://y", "checked_on": "2026-01-01",
                                   "expires_on": "2026-06-30"})}
    assert effective_policy("Y", "AB", "on_leash", date(2026, 7, 1), dogs) == "unknown"
    assert len(expired_rules(date(2027, 1, 1))) == 7 and expired_rules(date(2026, 12, 1)) == []


def test_guide_sees_expired_bans_as_check_dog_rules():
    from datetime import date
    from types import SimpleNamespace

    from app.guide.estimate import TrailFacts
    from app.guide.recommend import SKI_DOG_NOTE, dog_note

    row = SimpleNamespace(
        id=1, slug="skyline-trail", name="Skyline Trail", province_code="AB", park_name="Jasper National Park",
        terrain_difficulty="moderate", distance_km=45.7, elevation_gain_m=1380, max_elevation_m=2526,
        typical_duration_nights=2, climate_zone="alpine", tags=[], description=None, winter_activities=[],
        avalanche_exposure="challenging", winter_route_ends=None, dog_policy="not_allowed", popularity_rank=11,
        photo=None,
    )
    assert TrailFacts.from_trail(row, date(2026, 12, 1)).dog_policy == "not_allowed"
    after = TrailFacts.from_trail(row, date(2027, 1, 2))
    assert after.dog_policy == "unknown" and dog_note(after).startswith("Check dog rules")
    ski = TrailFacts.from_trail(SimpleNamespace(**{**row.__dict__, "name": "Ski Loop", "tags": ["winter_only"],
                                                   "dog_policy": "unknown"}), date(2026, 12, 1))
    assert dog_note(ski) == SKI_DOG_NOTE
