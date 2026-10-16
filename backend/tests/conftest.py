"""Test fixtures: an in-memory SQLite catalogue and real ES256 access tokens.

Tests never touch the DATABASE_URL database. Tokens are signed with a
throwaway EC key and verified by the real TokenVerifier through a fake JWKS
client, so authentication is exercised end to end.
"""

import os
import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app import models  # noqa: E402,F401  (registers tables)
from app.auth import TokenVerifier, get_verifier_dependency  # noqa: E402
from app.catalog.pipeline import run_import  # noqa: E402
from app.catalog.providers.base import SourceInfo  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
GEAR_TABLES = [
    table for name, table in Base.metadata.tables.items()
    if name.startswith(("catalog_", "gear_setup"))
    or name in ("user_gear_items", "profiles", "saved_trails", "trails", "trail_seasonal_conditions",
                "backcountry_parks", "backcountry_sites", "trail_campgrounds", "trail_booking_systems",
                "availability_alerts", "availability_cache", "provider_request_budget", "job_locks",
                "trip_plans", "trip_plan_nights")
]


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # pysqlite's own transaction handling breaks SAVEPOINT; let SQLAlchemy drive it.
    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _begin(connection):
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine, tables=GEAR_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


class StaticProvider:
    def __init__(self, records, slug="test-source", kind="manual"):
        self.source = SourceInfo(slug=slug, name=f"Test source {slug}", kind=kind)
        self._records = records

    def records(self):
        yield from self._records


def make_record(**overrides):
    record = {
        "source_record_id": "test:big-agnes-copper-spur-hv-ul2",
        "brand": "Big Agnes",
        "name": "Copper Spur HV UL2",
        "category": "tents",
        "official_url": "https://www.bigagnes.com/products/copper-spur-hv-ul2",
        "source_url": "https://www.bigagnes.com/products/copper-spur-hv-ul2",
        "verified_at": "2026-10-13",
        "weight": {"text": "2 lb 14 oz", "basis": "minimum"},
        "specs": {"capacity_persons": 2, "freestanding": True, "doors": 2},
    }
    record.update(overrides)
    return record


SAMPLE_RECORDS = [
    make_record(),
    make_record(
        source_record_id="test:nemo-tensor-all-season",
        brand="NEMO",
        brand_aliases=["NEMO Equipment"],
        name="Tensor All-Season",
        category="sleeping-pads",
        aliases=["Tensor Insulated"],
        official_url="https://www.nemoequipment.com/products/tensor-all-season",
        source_url="https://www.nemoequipment.com/products/tensor-all-season",
        weight=None,
        specs={"r_value": 5.4, "pad_type": "air"},
        variants=[
            {"name": "Regular Mummy", "weight": {"text": "14.1 oz", "basis": "minimum"}},
            {"name": "Long Wide", "weight": {"text": "1 lb 4 oz", "basis": "minimum"}},
        ],
    ),
    make_record(
        source_record_id="test:msr-pocketrocket-deluxe",
        brand="MSR",
        brand_aliases=["Mountain Safety Research"],
        name="PocketRocket Deluxe",
        category="stoves",
        official_url="https://cascadedesigns.com/products/pocketrocket-deluxe-stove",
        source_url="https://cascadedesigns.com/products/pocketrocket-deluxe-stove",
        weight={"value": "83", "unit": "g", "basis": "minimum"},
        specs={"fuel_type": "canister", "boil_time_min": 3.3, "piezo_ignition": True},
    ),
    make_record(
        source_record_id="test:arcteryx-beta-ar",
        brand="Arc'teryx",
        brand_aliases=["Arcteryx"],
        name="Beta AR Jacket",
        category="rainwear",
        status="discontinued",
        official_url=None,
        source_url="https://arcteryx.com/us/en/shop/beta-ar-jacket",
        weight=None,
        specs={},
    ),
]


@pytest.fixture
def seeded(db):
    report = run_import(db, StaticProvider(SAMPLE_RECORDS))
    assert report.status == "succeeded", report.errors
    return db


class FakeJWKSClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return type("SigningKey", (), {"key": self.public_key})()


@pytest.fixture(scope="session")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def make_token(signing_key):
    def _make(user_id=None, **claims):
        now = int(time.time())
        payload = {
            "sub": str(user_id or uuid.uuid4()),
            "aud": "authenticated",
            "iss": ISSUER,
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
        }
        payload.update(claims)
        payload = {key: value for key, value in payload.items() if value is not None}
        return jwt.encode(payload, signing_key, algorithm="ES256", headers={"kid": "test"})

    return _make


@pytest.fixture
def client(session_factory, seeded, signing_key):
    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    verifier = TokenVerifier(SUPABASE_URL, jwks_client=FakeJWKSClient(signing_key.public_key()))
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_verifier_dependency] = lambda: verifier
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(make_token):
    def _headers(user_id):
        return {"Authorization": f"Bearer {make_token(user_id)}"}

    return _headers
