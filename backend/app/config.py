"""App settings read from the environment (with sensible defaults)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip().upper() for part in value.split(",") if part.strip())


# Which countries the public trail catalogue covers (ISO 3166-1 alpha-2,
# comma-separated) and how many trails it keeps, by popularity rank. Read by
# both the trail seed script and the /api/trails list endpoint.
TRAIL_CATALOG_COUNTRIES = _csv(os.getenv("TRAIL_CATALOG_COUNTRIES", "CA"))
TRAIL_CATALOG_LIMIT = int(os.getenv("TRAIL_CATALOG_LIMIT", "100"))
