"""Generic CSV feed adapter for a permitted manufacturer or licensed feed.

Many brands and distributors share product data as spreadsheets. This
adapter maps one row per product (or per variant, grouped by a product id
column) onto CatalogRecord dicts using a column map, so onboarding such a
feed is configuration rather than code.

Expected columns are configurable; the defaults are:

    record_id, brand, name, category, model_number, status, official_url,
    source_url, verified_at, weight_text | weight_value + weight_unit,
    weight_basis, capacity_value + capacity_unit, variant_name, variant_sku,
    spec:<key> (any number of spec columns, e.g. spec:r_value)

Blank cells are treated as unknown, never as zero.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from app.catalog.providers.base import SourceInfo

SPEC_PREFIX = "spec:"


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _parse_spec(raw: str):
    text = raw.strip()
    lowered = text.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    return text  # numeric strings are validated/converted by the spec registry


class CsvFeedProvider:
    def __init__(self, path: Path, source: SourceInfo, columns: dict[str, str] | None = None):
        self.path = Path(path)
        self.source = source
        self.columns = {key: key for key in (
            "record_id", "brand", "name", "category", "model_number", "status",
            "official_url", "source_url", "verified_at", "weight_text", "weight_value",
            "weight_unit", "weight_basis", "capacity_value", "capacity_unit",
            "variant_name", "variant_sku",
        )}
        self.columns.update(columns or {})

    def _get(self, row: dict, key: str) -> str | None:
        value = row.get(self.columns[key])
        return None if _blank(value) else value.strip()

    def _weight(self, row: dict) -> dict | None:
        basis = self._get(row, "weight_basis")
        text = self._get(row, "weight_text")
        if text:
            return {"text": text, "basis": basis}
        value, unit = self._get(row, "weight_value"), self._get(row, "weight_unit")
        if value and unit:
            return {"value": value, "unit": unit, "basis": basis}
        return None

    def _capacity(self, row: dict) -> dict | None:
        value, unit = self._get(row, "capacity_value"), self._get(row, "capacity_unit")
        return {"value": value, "unit": unit} if value and unit else None

    def _specs(self, row: dict) -> dict:
        return {
            column[len(SPEC_PREFIX):]: _parse_spec(value)
            for column, value in row.items()
            if column and column.startswith(SPEC_PREFIX) and not _blank(value)
        }

    def records(self) -> Iterator[dict]:
        grouped: dict[str, dict] = {}
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                record_id = self._get(row, "record_id")
                if not record_id:
                    # Let the pipeline report it as invalid rather than dropping it silently.
                    yield {"source_record_id": "", "brand": self._get(row, "brand") or ""}
                    continue
                variant_name = self._get(row, "variant_name")
                record = grouped.get(record_id)
                if record is None:
                    record = {
                        key: value
                        for key, value in {
                            "source_record_id": record_id,
                            "brand": self._get(row, "brand"),
                            "name": self._get(row, "name"),
                            "category": self._get(row, "category"),
                            "model_number": self._get(row, "model_number"),
                            "status": self._get(row, "status"),
                            "official_url": self._get(row, "official_url"),
                            "source_url": self._get(row, "source_url"),
                            "verified_at": self._get(row, "verified_at"),
                        }.items()
                        if value is not None
                    }
                    record["variants"] = []
                    if not variant_name:
                        if weight := self._weight(row):
                            record["weight"] = weight
                        if capacity := self._capacity(row):
                            record["capacity"] = capacity
                        record["specs"] = self._specs(row)
                    grouped[record_id] = record
                if variant_name:
                    variant = {"name": variant_name, "specs": self._specs(row)}
                    if sku := self._get(row, "variant_sku"):
                        variant["sku"] = sku
                    if weight := self._weight(row):
                        variant["weight"] = weight
                    if capacity := self._capacity(row):
                        variant["capacity"] = capacity
                    record["variants"].append(variant)
        yield from grouped.values()
