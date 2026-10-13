"""Curated JSON provider: hand-verified records kept in the repository.

File format (see backend/catalog_data/curated_manufacturer_specs.json):

    {
      "source": {"slug": ..., "name": ..., "kind": "manual", ...},
      "records": [ { ...CatalogRecord fields... }, ... ]
    }
"""

import json
from collections.abc import Iterator
from pathlib import Path

from app.catalog.providers.base import SourceInfo


class CuratedJsonProvider:
    def __init__(self, path: Path):
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self._records = payload.get("records", [])
        self.source = SourceInfo(**payload["source"])

    def records(self) -> Iterator[dict]:
        yield from self._records
