"""Winter classification: validation, safety defaults, the committed file and the DB sync."""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import trail_winter
from app.models.trail import Trail
from app.trail_winter import DEFAULTS, WinterDataError, load_winter, sync_winter, unmatched, validate

ATES_URL = "https://parks.canada.ca/ates/simple"
SOURCE_URL = "https://parks.canada.ca/winter"


def winter_entry(**overrides):
    row = {"name": "Chester Lake", "province_code": "AB", "winter_activities": ["snowshoe"],
           "avalanche_exposure": "simple", "avalanche_source_url": ATES_URL,
           "winter_access_note": None, "winter_notes": "Shared with skiers", "winter_source_url": SOURCE_URL}
    row.update(overrides)
    return row


def trail(name="Chester Lake", province="AB", **kw):
    return Trail(name=name, region="Kananaskis, AB", country_code="CA", province_code=province,
                 terrain_difficulty="moderate", popularity_rank=kw.pop("rank", 1), **kw)


# --- validation and safety defaults

def test_defaults_are_not_recommended_and_unknown():
    assert DEFAULTS["winter_activities"] == []
    assert DEFAULTS["avalanche_exposure"] == "unknown"


def test_missing_fields_fall_back_to_unknown_never_none():
    values = validate({"name": "X", "province_code": "AB"})
    assert values["avalanche_exposure"] == "unknown"
    assert values["winter_activities"] == []


@pytest.mark.parametrize("rating", ["none", "simple", "challenging", "complex"])
def test_any_rating_needs_its_official_source(rating):
    with pytest.raises(WinterDataError, match="source URL"):
        validate(winter_entry(avalanche_exposure=rating, avalanche_source_url=None))


def test_activities_need_a_source():
    with pytest.raises(WinterDataError, match="need a source"):
        validate(winter_entry(winter_source_url=None))


def test_route_end_needs_a_winter_route():
    assert validate(winter_entry(winter_route_ends="The Red Chairs"))["winter_route_ends"] == "The Red Chairs"
    with pytest.raises(WinterDataError, match="winter route"):
        validate(winter_entry(winter_activities=[], winter_route_ends="The Red Chairs"))


def test_rejects_ski_touring_and_unknown_classes():
    with pytest.raises(WinterDataError, match="unknown winter activities"):
        validate(winter_entry(winter_activities=["ski_touring"]))
    with pytest.raises(WinterDataError, match="not an ATES class"):
        validate(winter_entry(avalanche_exposure="low"))


def test_activities_are_stored_in_a_fixed_order():
    assert validate(winter_entry(winter_activities=["snowshoe", "winter_hike"]))["winter_activities"] == [
        "winter_hike", "snowshoe"]
    with pytest.raises(WinterDataError):
        validate(winter_entry(winter_activities=["snowshoe", "snowshoe"]))


def test_rejects_plain_http_sources():
    with pytest.raises(WinterDataError, match="https"):
        validate(winter_entry(winter_source_url="http://example.test"))
    with pytest.raises(WinterDataError, match="https"):
        validate(winter_entry(winter_report_url="http://example.test/report"))


def test_duplicate_entries_are_rejected(tmp_path):
    path = tmp_path / "w.json"
    path.write_text(json.dumps({"meta": {}, "trails": [winter_entry(), winter_entry()]}))
    with pytest.raises(WinterDataError, match="twice"):
        load_winter.__wrapped__(path)


# --- the committed file

def test_committed_file_is_valid_and_conservative():
    winter = load_winter()
    assert winter, "catalog_data/trail_winter.json should list trails"
    # Nothing in the file claims "no avalanche terrain" yet; if it ever does, it carries its source.
    for key, values in winter.items():
        assert values["avalanche_exposure"] != "none" or values["avalanche_source_url"], key
    # Partial winter routes say where they end (the user's rule for Minnewanka, Wilcox, Jacques Lake).
    for key in [("Lake Minnewanka Shoreline Trail", "AB"), ("Wilcox Pass", "AB"), ("Jacques Lake", "AB")]:
        assert winter[key]["winter_route_ends"], key
    # Groomed ski trails say so and name where to check grooming (the user's rule for new XC trails).
    for key, values in winter.items():
        if "xc_ski" in values["winter_activities"]:
            assert "groom" in (values["winter_notes"] or "").lower() or "track-set" in (values["winter_notes"] or "").lower(), key
        # Backcountry touring terrain is never recommended.
    assert winter[("Elfin Lakes", "BC")]["winter_activities"] == []
    # Every rated trail points at an official source.
    for key, values in winter.items():
        if values["avalanche_exposure"] != "unknown":
            assert "parks.canada.ca" in values["avalanche_source_url"], key


def test_committed_file_matches_the_catalogue():
    catalogue = json.loads((trail_winter.WINTER_PATH.parent / "trails_canada.json").read_text(encoding="utf-8"))
    names = {(t["name"], t["province_code"]) for t in catalogue["trails"]}
    assert [key for key in load_winter() if key not in names] == []


# --- the database sync

def test_sync_writes_entries_and_resets_unlisted_trails(db):
    listed = trail()
    other = trail("Rawson Lake", rank=2, winter_activities=["snowshoe"], winter_source_url=SOURCE_URL,
                  avalanche_exposure="simple", avalanche_source_url=ATES_URL)
    retired = trail("Old Trail", rank=3, retired_at=datetime.now(timezone.utc))
    db.add_all([listed, other, retired])
    db.flush()

    winter = {("Chester Lake", "AB"): validate(winter_entry())}
    changed = dict(sync_winter(db, winter))

    assert listed.winter_activities == ["snowshoe"]
    assert listed.avalanche_exposure == "simple" and listed.avalanche_source_url == ATES_URL
    # Dropped from the file: back to not recommended / unknown.
    assert other.winter_activities == [] and other.avalanche_exposure == "unknown"
    assert other.avalanche_source_url is None
    assert "Old Trail" not in changed
    assert set(changed) == {"Chester Lake", "Rawson Lake"}
    # Same file again: nothing to do.
    assert sync_winter(db, winter) == []


def test_new_trails_default_to_unknown(db):
    t = trail()
    db.add(t)
    db.flush()
    db.refresh(t)
    assert t.avalanche_exposure == "unknown"
    assert t.winter_activities == []


def test_a_rating_without_source_is_refused_by_the_database(db):
    db.add(trail(avalanche_exposure="none"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_unmatched_lists_entries_without_an_active_trail(db):
    db.add(trail())
    db.flush()
    winter = {("Chester Lake", "AB"): validate(winter_entry()),
              ("Typo Lake", "AB"): validate(winter_entry(name="Typo Lake"))}
    assert unmatched(db, winter) == [("Typo Lake", "AB")]
