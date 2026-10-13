"""Provider adapter interface.

A provider wraps one data source — a curated file, a licensed CSV feed, a
manufacturer's authorized API — and yields raw dicts in the CatalogRecord
shape (app/catalog/records.py). Providers do no database work; the pipeline
handles validation, normalization, deduplication and upserts, so a new
source only needs to map its own fields.

To add a provider: subclass nothing, just implement `source` and `records()`,
register it in app/catalog/providers/__init__.py, and document the source's
licence/terms in docs/gear-catalog.md before importing anything.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class SourceInfo:
    slug: str
    name: str
    kind: Literal["manufacturer", "licensed_feed", "manual"]
    homepage_url: str | None = None
    terms_url: str | None = None
    terms_notes: str | None = None


class CatalogProvider(Protocol):
    source: SourceInfo

    def records(self) -> Iterator[dict]:
        """Yield raw records. May raise for a source-level failure (e.g. auth)."""
        ...
