from pathlib import Path

from app.catalog.providers.base import CatalogProvider, SourceInfo
from app.catalog.providers.csv_feed import CsvFeedProvider
from app.catalog.providers.curated import CuratedJsonProvider

CATALOG_DATA_DIR = Path(__file__).resolve().parents[3] / "catalog_data"
CURATED_FILE = CATALOG_DATA_DIR / "curated_manufacturer_specs.json"


def default_providers() -> dict[str, CatalogProvider]:
    """Providers the import CLI knows by name."""
    return {"curated": CuratedJsonProvider(CURATED_FILE)}


__all__ = [
    "CATALOG_DATA_DIR",
    "CURATED_FILE",
    "CatalogProvider",
    "CsvFeedProvider",
    "CuratedJsonProvider",
    "SourceInfo",
    "default_providers",
]
