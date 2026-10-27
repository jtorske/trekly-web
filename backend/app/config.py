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


def photo_admin_user_ids() -> frozenset[str]:
    """Supabase user ids allowed to review, approve and upload trail photos
    (PHOTO_ADMIN_USER_IDS, comma-separated). Read on every call so a change
    to the environment never needs a code path to be re-imported; empty
    means nobody."""
    return frozenset(
        part.strip().lower() for part in os.getenv("PHOTO_ADMIN_USER_IDS", "").split(",") if part.strip()
    )


def admin_user_ids() -> frozenset[str]:
    """Supabase user ids allowed to moderate profiles (ADMIN_USER_IDS,
    comma-separated). PHOTO_ADMIN_USER_IDS counts too, so the photo admins
    don't need a second setting. Read on every call; empty means nobody."""
    ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    return frozenset(part.strip().lower() for part in ids if part.strip()) | photo_admin_user_ids()
