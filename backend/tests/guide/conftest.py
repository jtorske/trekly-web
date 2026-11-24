"""Fixtures for Trekly Guide: a synthetic trail builder and the real catalogue.

`catalogue` seeds an in-memory SQLite database from the committed catalogue
files (trails_canada.json, trail_routes.json, trail_winter.json,
trail_dogs.json) exactly as scripts/seed_trails.py + the sync scripts do, so
the persona evals run against the trails Trekly actually serves.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.database import Base
from app.guide.estimate import TrailFacts
from app.models.trail import Trail
from app.trail_catalog import load_catalog, sync_trails
from app.trail_dogs import load_dogs, sync_dogs
from app.trail_routes import routes_by_name
from app.trail_winter import load_winter, sync_winter


def make_trail(name="Test Trail", **overrides) -> TrailFacts:
    values = dict(
        id=uuid.uuid4(),
        slug=name.lower().replace(" ", "-"),
        name=name,
        province_code="AB",
        park_name=None,
        terrain="moderate",
        distance_km=10.0,
        elevation_gain_m=500,
        max_elevation_m=2000,
        nights=0,
        climate_zone="temperate",
        tags=(),
        description=None,
        winter_activities=(),
        avalanche_exposure="unknown",
        winter_route_ends=None,
        dog_policy="unknown",
        popularity_rank=50,
        has_photo=False,
    )
    values.update(overrides)
    return TrailFacts(**values)


def seed_catalogue(db) -> None:
    sync_trails(db, load_catalog(), TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT, routes=routes_by_name())
    sync_winter(db, load_winter())
    sync_dogs(db, load_dogs())
    db.commit()


@pytest.fixture(scope="session")
def catalogue_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[t] for t in ("trails", "trail_photos", "trail_route_maps")]
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_catalogue(db)
    yield db
    db.close()
    engine.dispose()


@pytest.fixture(scope="session")
def catalogue(catalogue_session) -> list[TrailFacts]:
    """Every live trail, as the Guide sees it."""
    from app.routers.trails import live_trails

    rows = catalogue_session.query(Trail).filter(*live_trails()).order_by(Trail.popularity_rank).all()
    return [TrailFacts.from_trail(t) for t in rows]


@pytest.fixture(scope="session")
def by_slug(catalogue) -> dict[str, TrailFacts]:
    return {t.slug: t for t in catalogue}
