"""Shared fixtures for spec 018 W2B endpoint tests.

Uses an in-memory SQLite DB; PostgreSQL-only types (JSONB, UUID, BIGINT) work
against SQLite via SQLAlchemy's dialect fallbacks. The fixture patches
`app.services.hes_client.hes_client` with an async mock so tests don't touch
the real HES routing service.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
from app.api.v1 import router as router_module
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import Base
from app.main import app
from app.models.meter import Feeder, Meter, MeterStatus, RelayState, Transformer
from app.models.user import User, UserRole

# BigInteger PK autoincrement doesn't work on SQLite via the ORM. Install a
# before-insert hook so spec-018 W3 tables (created without an explicit id)
# get a monotonically-increasing synthetic id in tests. Scoped to this conftest.
try:
    from sqlalchemy import event
    from app.models.meter_event import OutageCorrelatorInput
    from app.models.outage import OutageTimelineEvent

    _W3_COUNTERS: dict[str, int] = {
        "OutageCorrelatorInput": 0,
        "OutageTimelineEvent": 0,
    }

    def _w3_bigint_autoincrement(mapper, connection, target):
        cls = type(target).__name__
        if cls in _W3_COUNTERS and getattr(target, "id", None) is None:
            _W3_COUNTERS[cls] += 1
            target.id = _W3_COUNTERS[cls]

    event.listen(OutageCorrelatorInput, "before_insert", _w3_bigint_autoincrement)
    event.listen(OutageTimelineEvent, "before_insert", _w3_bigint_autoincrement)
except Exception:  # pragma: no cover — models may not exist in older branches
    pass


# ── DB setup ──


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def SessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(SessionLocal):
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ── App with overrides ──


@pytest.fixture
def test_user():
    return User(
        id=42,
        username="tester",
        email="tester@example.com",
        full_name="Tester",
        hashed_password="x",
        role=UserRole.ADMIN,
        is_active=True,
    )


@pytest.fixture
def client(SessionLocal, test_user, monkeypatch):
    # Pin feature flags so tests are deterministic.
    monkeypatch.setattr(settings, "HES_ENABLED", True)
    monkeypatch.setattr(settings, "SMART_INVERTER_COMMANDS_ENABLED", True)
    # Don't boot Kafka consumers during tests — we're not integrating with a broker.
    monkeypatch.setattr(settings, "KAFKA_ENABLED", False)

    def _get_db_override():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_base.get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = lambda: test_user

    # Intentionally NOT using `with TestClient(app)` — that would drive the
    # lifespan which boots Kafka / OTel / audit-writer. Those are wave-2A
    # concerns and unrelated to W2B unit tests.
    c = TestClient(app, raise_server_exceptions=True)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


# ── HES client fake ──


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    @property
    def status_code(self) -> int:
        return 200


class FakeHESClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.next_response: dict = {"accepted": True}
        self.raise_exc: Exception | None = None

    async def post_command(self, type_: str, meter_serial: str, payload: dict | None = None):
        self.calls.append(("post_command", {"type": type_, "meter_serial": meter_serial, "payload": payload}))
        if self.raise_exc:
            raise self.raise_exc
        return _FakeResponse(self.next_response)

    async def post_command_batch(self, commands):
        self.calls.append(("post_command_batch", {"commands": commands}))
        if self.raise_exc:
            raise self.raise_exc
        return _FakeResponse({"accepted": len(commands)})

    async def create_fota_job(self, payload):
        self.calls.append(("create_fota_job", payload))
        if self.raise_exc:
            raise self.raise_exc
        return _FakeResponse({"hes_job_id": "HES-JOB-123", **payload})

    async def get_fota_job(self, job_id: str):
        self.calls.append(("get_fota_job", {"job_id": job_id}))
        return _FakeResponse({"status": "RUNNING", "meters": []})


@pytest.fixture
def fake_hes(monkeypatch):
    fake = FakeHESClient()
    # Patch both the module-level symbol used by endpoints and services.
    from app.services import hes_client as hes_mod

    monkeypatch.setattr(hes_mod, "hes_client", fake)
    # Patch consumers that imported hes_client symbol directly.
    import app.api.v1.endpoints.meters as meters_ep
    import app.api.v1.endpoints.der as der_ep
    import app.api.v1.endpoints.fota as fota_ep
    import app.services.fota_service as fota_svc

    monkeypatch.setattr(meters_ep, "hes_client", fake)
    monkeypatch.setattr(der_ep, "hes_client", fake)
    monkeypatch.setattr(fota_ep, "fota_service", fota_svc.FOTAService())  # fresh instance
    monkeypatch.setattr(fota_svc, "hes_client", fake)
    yield fake


# ── Seed helpers ──


@pytest.fixture
def seed_meter(db):
    def _make(serial: str = "M0001") -> Meter:
        feeder = Feeder(name="FDR-1", substation="SS-1", voltage_kv=11.0, capacity_kva=500.0)
        db.add(feeder)
        db.flush()
        tx = Transformer(
            name="DTR-1",
            feeder_id=feeder.id,
            latitude=0.0,
            longitude=0.0,
            capacity_kva=100.0,
        )
        db.add(tx)
        db.flush()
        m = Meter(
            serial=serial,
            transformer_id=tx.id,
            status=MeterStatus.ONLINE,
            relay_state=RelayState.CONNECTED,
            latitude=0.0,
            longitude=0.0,
        )
        db.add(m)
        db.commit()
        return m

    return _make
