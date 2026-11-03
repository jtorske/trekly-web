"""The pre-import validator agrees with the shipped catalogue and the Gear mat."""

import importlib.util
from pathlib import Path

from app.catalog.taxonomy import SUBCATEGORY_TO_TOP

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "catalog_validate.py"
spec = importlib.util.spec_from_file_location("catalog_validate", SCRIPT)
catalog_validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_validate)


def test_every_subcategory_has_a_mat_slot():
    slots = catalog_validate.slot_categories()
    assert set(SUBCATEGORY_TO_TOP) <= set(slots)
    assert slots["camp-furniture"] == "camp-chair"
    assert slots["sanitation"] == "other"


def test_every_subcategory_has_weight_bounds():
    assert set(SUBCATEGORY_TO_TOP) <= set(catalog_validate.WEIGHT_BOUNDS_G)


def test_shipped_catalogue_has_no_hard_failures(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["catalog_validate.py"])
    assert catalog_validate.main() == 0
    assert "Hard failures: **0**" in capsys.readouterr().out
