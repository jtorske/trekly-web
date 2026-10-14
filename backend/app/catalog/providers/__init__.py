from pathlib import Path

from app.catalog.providers.base import CatalogProvider, SourceInfo
from app.catalog.providers.csv_feed import CsvFeedProvider
from app.catalog.providers.curated import CuratedJsonProvider

CATALOG_DATA_DIR = Path(__file__).resolve().parents[3] / "catalog_data"
CURATED_FILE = CATALOG_DATA_DIR / "curated_manufacturer_specs.json"
EXCERPTS_FILE = CATALOG_DATA_DIR / "curated_official_excerpts.json"
CURATED_FILES = (CURATED_FILE, EXCERPTS_FILE)


def default_providers() -> dict[str, CatalogProvider]:
    """Providers the import CLI knows by name, in import order.

    Directly-read manufacturer pages import first; search-excerpt records are a
    separate, lower-confidence source and merge into the same products if both
    exist (provenance keeps both links).
    """
    return {
        "curated": CuratedJsonProvider(CURATED_FILE),
        "official-excerpts": CuratedJsonProvider(EXCERPTS_FILE),
    }


__all__ = [
    "CATALOG_DATA_DIR",
    "CURATED_FILE",
    "CURATED_FILES",
    "EXCERPTS_FILE",
    "CatalogProvider",
    "CsvFeedProvider",
    "CuratedJsonProvider",
    "SourceInfo",
    "default_providers",
]
