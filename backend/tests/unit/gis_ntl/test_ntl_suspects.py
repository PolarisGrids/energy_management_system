"""W3.T8 / W3.T10 — NTL suspect scoring + energy-balance endpoints.

Stand-alone FastAPI app mounting only ``app.api.v1.endpoints.ntl`` so the tests
don't depend on the shared `conftest.py` that imports the full router (which
pulls in Agent H / J modules still landing in parallel).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
from app.api.v1.endpoints import ntl
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.alarm import Alarm
from app.models.meter import (
    Feeder,
    Meter,
    MeterStatus,
    MeterType,
    RelayState,
    Transformer,
)
from app.models.meter_event import MeterEventLog
from app.models.reading import MeterReading
from app.models.user import User, UserRole


def _build_app(monkeypatch_local):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Feeder.__table__.create(engine)
    Transformer.__table__.create(engine)
    Meter.__table__.create(engine)
    Alarm.__table__.create(engine)
    MeterEventLog.__table__.create(engine)
    MeterReading.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    user = User(
        id=1, username="op", email="op@x", full_name="Op",
        hashed_password="x", role=UserRole.OPERATOR, is_active=True,
    )

    app = FastAPI()
    app.include_router(ntl.router, prefix="/ntl")

    def _override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_base.get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user

    # Force local path by default — each test can flip MDMS_NTL_ENABLED on.
    monkeypatch_local.setattr(settings, "MDMS_NTL_ENABLED", False)
    monkeypatch_local.setattr(settings, "MDMS_ENABLED", False)
    return app, SessionLocal


@pytest.fixture
def app_client(monkeypatch):
    app, SessionLocal = _build_app(monkeypatch)
    with TestClient(app) as c:
        yield c, SessionLocal


def _seed_dtr_with_meters(SessionLocal, *, include_events: bool = True,
                          include_readings: bool = True):
    s = SessionLocal()
    feeder = Feeder(
        name="FDR", substation="SS", voltage_kv=11.0, capacity_kva=500.0,
        current_load_kw=100.0,
    )
    s.add(feeder)
    s.flush()
    tx = Transformer(
        name="DTR-X", feeder_id=feeder.id, latitude=26.0, longitude=75.0,
        capacity_kva=200.0, current_load_kw=150.0, loading_percent=75.0,
    )
    s.add(tx)
    s.flush()
    m1 = Meter(
        serial="NTL-01", transformer_id=tx.id, latitude=26.01, longitude=75.01,
        status=MeterStatus.ONLINE, relay_state=RelayState.CONNECTED,
        meter_type=MeterType.RESIDENTIAL, customer_name="Suspect Alice",
        account_number="A-001",
    )
    m2 = Meter(
        serial="NTL-02", transformer_id=tx.id, latitude=26.02, longitude=75.02,
        status=MeterStatus.ONLINE, relay_state=RelayState.CONNECTED,
        meter_type=MeterType.RESIDENTIAL, customer_name="Honest Bob",
        account_number="A-002",
    )
    s.add_all([m1, m2])
    s.flush()

    now = datetime.now(timezone.utc)
    if include_events:
        # Explicit ids — SQLite's autoincrement on BigInteger is flaky via ORM.
        s.add_all(
            [
                MeterEventLog(
                    id=i + 1,
                    event_id=f"E-{i}", meter_serial="NTL-01",
                    event_type="magnet_tamper", dlms_event_code=201,
                    event_ts=now - timedelta(hours=i),
                )
                for i in range(2)
            ]
        )
        s.add(
            MeterEventLog(
                id=100,
                event_id="E-rev", meter_serial="NTL-01",
                event_type="reverse_energy", dlms_event_code=209,
                event_ts=now - timedelta(hours=1),
            )
        )
    if include_readings:
        # Simulate a 24h baseline of downstream consumption + aggregate.
        for hour in range(24):
            ts = now - timedelta(hours=24 - hour)
            s.add_all(
                [
                    MeterReading(
                        meter_serial="NTL-01", timestamp=ts,
                        energy_import_kwh=0.5, demand_kw=0.5,
                    ),
                    MeterReading(
                        meter_serial="NTL-02", timestamp=ts,
                        energy_import_kwh=0.8, demand_kw=0.8,
                    ),
                    # Aggregate meter at DTR boundary (feeder input).
                    MeterReading(
                        meter_serial=f"DTR-AGG-{tx.id}", timestamp=ts,
                        energy_import_kwh=2.0, demand_kw=2.0,
                    ),
                ]
            )
    s.commit()
    tx_id = tx.id
    s.close()
    return tx_id


# ── /ntl/suspects (local path) ──


def test_suspects_local_path_computes_score_from_events(app_client):
    client, SessionLocal = app_client
    _seed_dtr_with_meters(SessionLocal, include_readings=False)

    resp = client.get("/ntl/suspects")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "local"
    assert body["scoring_available"] is False
    assert "banner" in body
    items = body["items"]
    assert len(items) == 1
    top = items[0]
    assert top["meter_serial"] == "NTL-01"
    # 2x magnet_tamper (40 each) + 1x reverse_energy (20) = 100
    assert top["score"] == 100
    assert top["dtr_name"] == "DTR-X"
    assert top["event_count_7d"] == 3
    assert top["last_event_type"] in {"magnet_tamper", "reverse_energy"}


def test_suspects_min_score_filter(app_client):
    client, SessionLocal = app_client
    _seed_dtr_with_meters(SessionLocal, include_readings=False)

    # score is capped at 100; with min_score=100 and 2×40 + 20 = 100 → passes.
    # Raise the bar above a single contribution to see filtering kick in.
    resp = client.get("/ntl/suspects", params={"min_score": 10})
    hits = resp.json()["items"]
    assert len(hits) == 1
    assert hits[0]["score"] >= 10
    # Invalid upper bound is rejected by FastAPI.
    assert client.get("/ntl/suspects", params={"min_score": 110}).status_code == 422


def test_suspects_dtr_filter(app_client):
    client, SessionLocal = app_client
    dtr_id = _seed_dtr_with_meters(SessionLocal, include_readings=False)

    # Same dtr → 1 suspect; other dtr → 0.
    r_match = client.get("/ntl/suspects", params={"dtr_id": dtr_id})
    r_miss = client.get("/ntl/suspects", params={"dtr_id": 9999})
    assert r_match.status_code == 200 and len(r_match.json()["items"]) == 1
    assert r_miss.status_code == 200 and r_miss.json()["items"] == []


def test_suspects_empty_when_no_events(app_client):
    client, _ = app_client
    resp = client.get("/ntl/suspects")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── /ntl/energy-balance ──


def test_energy_balance_basic(app_client):
    client, SessionLocal = app_client
    dtr_id = _seed_dtr_with_meters(SessionLocal)

    resp = client.get("/ntl/energy-balance", params={"dtr_id": dtr_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dtr_id"] == dtr_id
    # 24 readings × 2.0 kWh aggregate = 48.0; downstream (0.5 + 0.8) × 24 = 31.2.
    # Default from=now-1d captures ~24 rows.
    assert body["feeder_input_kwh"] > 0
    assert body["downstream_kwh"] > 0
    assert body["gap_kwh"] == round(body["feeder_input_kwh"] - body["downstream_kwh"], 2)
    assert 0 < body["gap_pct"] < 100
    assert body["meter_count"] == 2


def test_energy_balance_unknown_dtr_404(app_client):
    client, _ = app_client
    resp = client.get("/ntl/energy-balance", params={"dtr_id": 98765})
    assert resp.status_code == 404


def test_energy_balance_top(app_client):
    client, SessionLocal = app_client
    _seed_dtr_with_meters(SessionLocal)

    resp = client.get("/ntl/energy-balance/top", params={"limit": 5, "hours": 24})
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) >= 1
    assert all("gap_kwh" in r and "gap_pct" in r for r in rows)
    # Sorted descending.
    gaps = [r["gap_kwh"] for r in rows]
    assert gaps == sorted(gaps, reverse=True)


# ── /ntl/suspects/geojson ──


def test_suspects_geojson_returns_feature_collection(app_client):
    client, SessionLocal = app_client
    _seed_dtr_with_meters(SessionLocal, include_readings=False)

    resp = client.get("/ntl/suspects/geojson", params={"min_score": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    props = body["features"][0]["properties"]
    assert props["layer"] == "ntl_suspect"
    assert props["meter_serial"] == "NTL-01"
