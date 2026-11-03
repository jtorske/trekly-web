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


def _ids(name: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in os.getenv(name, "").split(",") if part.strip())


def admin_user_ids() -> frozenset[str]:
    """Supabase user ids allowed into the admin area, every /api/admin route
    including trail photos (ADMIN_USER_IDS, comma-separated).
    PHOTO_ADMIN_USER_IDS, the photo review's original setting, still counts.
    Read on every call, so a change to the environment never needs a
    re-import; empty means nobody. Checked by app/admin_access.py."""
    return _ids("ADMIN_USER_IDS") | _ids("PHOTO_ADMIN_USER_IDS")
