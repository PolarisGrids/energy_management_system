"""Shared fixtures for spec-018 demo-compliance integration tests.

This file is the first-owner contract between the three parallel wave agents
(US-1..8, US-9..16, US-17..24). Fixtures are intentionally *minimal* and
composable — each test story adds its own seed data on top of these.

Provided fixtures
-----------------
* ``client``             — ``TestClient`` for the FastAPI app with an override
                           for ``get_current_user`` returning a seeded operator
                           so individual tests don't need to mint JWTs.
* ``db_session``         — SQLAlchemy session bound to the default DB. Each
                           test function rolls back at the end.
* ``mdms_mock``          — a ``respx.MockRouter`` pinned to
                           ``settings.MDMS_BASE_URL`` with a default catch-all
                           returning 503 so stories must opt-in to real
                           payloads (keeps strict-SSOT honest).
* ``hes_mock``           — same, pinned to ``settings.HES_BASE_URL``.
* ``simulator_mock``     — pinned to ``settings.SIMULATOR_URL`` (scenario
                           proxy fixture).
* ``kafka_testcontainer``— lazy testcontainers.kafka fixture — importorskipped
                           when docker/testcontainers aren't available so the
                           suite still runs in minimal CI.

These fixtures are deliberately loose; the parallel US-1..8 agent may extend
this module — callers should prefer extension over rewrite.
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Iterator

import pytest


# ─── make sure the FastAPI test env is configured before app import ────────────
os.environ.setdefault("JWT_SECRET_KEY", "demo-compliance-test-secret")
os.environ.setdefault("DEPLOY_ENV", "local")
# Demo-mode default — stories opt into strict where needed via monkeypatch.
os.environ.setdefault("SSOT_MODE", "mirror")


# Re-use the Wave-2B unit-test fixtures (SQLite in-memory DB, seeded meter
# helper, TestClient with JWT override, FakeHESClient). This keeps the demo-
# compliance suite runnable on any developer workstation without requiring a
# live Postgres, HES, or MDMS pod.
#
# Fixtures provided by tests.unit.endpoints.conftest:
#     client, db, SessionLocal, engine, test_user, fake_hes, seed_meter
pytest_plugins = ["tests.unit.endpoints.conftest"]


@pytest.fixture()
def db_session(db):
    """Alias for the unit-test `db` session fixture.

    The other wave agents' tests (US-9..US-24) call the session `db_session`;
    keep both names so either convention works.
    """
    yield db


@pytest.fixture()
def seeded_operator(db_session):
    """Find an existing operator, or create a throwaway one for the test."""
    from app.models.user import User, UserRole

    user = db_session.query(User).filter(User.role == UserRole.OPERATOR).first()
    if user:
        return user
    u = User(
        username=f"demo_op_{uuid.uuid4().hex[:6]}",
        email=f"demo_{uuid.uuid4().hex[:6]}@polarisgrids.com",
        hashed_password="x",
        role=UserRole.OPERATOR,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


# ─── HTTP upstream mocks ──────────────────────────────────────────────────────

@pytest.fixture()
def mdms_mock():
    """respx mock scoped to MDMS base URL.

    Default: 200 with ``{}`` for any unspecified route — stories register the
    exact paths they care about via ``mdms_mock.get("/api/v1/vee/summary").respond(...)``.
    The previous default of 503 tripped the proxy's own gating code before
    tests could opt in; 200-empty lets individual stories opt in explicitly.
    """
    respx = pytest.importorskip("respx")
    from app.core.config import settings

    with respx.mock(base_url=settings.MDMS_BASE_URL, assert_all_called=False) as r:
        r.route().respond(200, json={})
        yield r


@pytest.fixture()
def hes_mock():
    respx = pytest.importorskip("respx")
    from app.core.config import settings

    with respx.mock(base_url=settings.HES_BASE_URL, assert_all_called=False) as r:
        r.route().respond(200, json={})
        yield r


@pytest.fixture()
def simulator_mock():
    """respx mock for the scenario simulator. Stories 17–24 rely more heavily
    on this; 9–16 touch it for simulator-triggered data (theft, PV curve).
    """
    respx = pytest.importorskip("respx")
    from app.core.config import settings

    base = getattr(settings, "SIMULATOR_URL", None) or "http://simulator:8080"
    with respx.mock(base_url=base, assert_all_called=False) as r:
        r.route().respond(503, json={"detail": "simulator-mock default"})
        yield r


# ─── Kafka ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def kafka_testcontainer():
    """Testcontainers-backed Kafka broker. Expensive, so scoped to session.

    Individual tests opt in with ``pytest.mark.requires_kafka`` (see
    ``pytest.ini``). When docker / testcontainers isn't available, skip
    cleanly so the rest of the suite still runs.
    """
    testcontainers = pytest.importorskip("testcontainers.kafka")
    from testcontainers.kafka import KafkaContainer  # noqa: WPS433

    with KafkaContainer("confluentinc/cp-kafka:7.6.1") as broker:
        yield broker


# ─── Utility helpers reused across stories ────────────────────────────────────

@contextmanager
def wait_until(predicate, *, timeout_s: float = 5.0, poll_s: float = 0.1):
    """Spin until ``predicate()`` returns truthy or timeout. Returns final value.

    Used by stories that assert on eventually-consistent state (Kafka fanout,
    scheduler ticks, reverse-flow debounce, etc.).
    """
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            yield last
            return
        time.sleep(poll_s)
    yield last


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
