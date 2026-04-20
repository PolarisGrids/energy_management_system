"""W3.T5 — GIS GeoJSON layer endpoints.

Uses a narrow FastAPI TestClient that mounts only the ``gis`` router to
avoid touching Agent H / Agent J sibling modules that may still be landing.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
from app.api.v1.endpoints import gis
from app.core.deps import get_current_user
from app.models.alarm import Alarm, AlarmSeverity, AlarmStatus, AlarmType
from app.models.meter import (
    Feeder,
    Meter,
    MeterStatus,
    MeterType,
    RelayState,
    Transformer,
)
from app.models.user import User, UserRole


# ── Local app + DB (avoid the full project router to sidestep other agents) ──


def _build_app():
    # Only create the specific tables we need — skip anything with PostgreSQL-only
    # types (e.g. ARRAY) to keep the SQLite test DB compilable.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Feeder.__table__.create(engine)
    Transformer.__table__.create(engine)
    Meter.__table__.create(engine)
    Alarm.__table__.create(engine)
    # For the heatmap test the Alarm FK to transformers is satisfied by the
    # transformer row; no extra tables needed.
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    fake_user = User(
        id=1,
        username="t",
        email="t@x",
        full_name="T",
        hashed_password="x",
        role=UserRole.OPERATOR,
        is_active=True,
    )

    app = FastAPI()
    app.include_router(gis.router, prefix="/gis")

    def _override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_base.get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return app, SessionLocal


@pytest.fixture
def app_client():
    app, SessionLocal = _build_app()
    with TestClient(app) as c:
        yield c, SessionLocal


def _seed_feeder_with_dtrs(SessionLocal):
    s = SessionLocal()
    feeder = Feeder(
        name="FDR-A", substation="SS-1", voltage_kv=11.0, capacity_kva=500.0,
        current_load_kw=250.0,
    )
    s.add(feeder)
    s.flush()
    t1 = Transformer(
        name="DTR-1", feeder_id=feeder.id, latitude=26.0, longitude=75.0,
        capacity_kva=100.0, current_load_kw=50.0, loading_percent=50.0,
    )
    t2 = Transformer(
        name="DTR-2", feeder_id=feeder.id, latitude=26.1, longitude=75.1,
        capacity_kva=100.0, current_load_kw=90.0, loading_percent=90.0,
    )
    s.add_all([t1, t2])
    s.flush()
    s.add_all(
        [
            Meter(
                serial="M-1", transformer_id=t1.id, latitude=26.01, longitude=75.01,
                status=MeterStatus.ONLINE, relay_state=RelayState.CONNECTED,
                meter_type=MeterType.RESIDENTIAL, customer_name="Alice",
            ),
            Meter(
                serial="M-2", transformer_id=t1.id, latitude=26.02, longitude=75.02,
                status=MeterStatus.OFFLINE, relay_state=RelayState.CONNECTED,
                meter_type=MeterType.RESIDENTIAL, customer_name="Bob",
            ),
            Meter(
                serial="M-FAR", transformer_id=t2.id, latitude=40.0, longitude=-74.0,
                status=MeterStatus.ONLINE, relay_state=RelayState.CONNECTED,
                meter_type=MeterType.RESIDENTIAL,
            ),
        ]
    )
    s.commit()
    s.close()


# ── Tests ──


def test_layer_meter_returns_feature_collection(app_client):
    client, SessionLocal = app_client
    _seed_feeder_with_dtrs(SessionLocal)

    resp = client.get("/gis/layers", params={"layer": "meter", "limit": 100})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    feat = body["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    assert feat["properties"]["layer"] == "meter"
    assert feat["properties"]["serial"] in {"M-1", "M-2", "M-FAR"}


def test_layer_meter_bbox_filters(app_client):
    client, SessionLocal = app_client
    _seed_feeder_with_dtrs(SessionLocal)

    resp = client.get(
        "/gis/layers",
        params={"layer": "meter", "bbox": "74.9,25.9,75.5,26.5"},
    )
    assert resp.status_code == 200
    serials = {f["properties"]["serial"] for f in resp.json()["features"]}
    # M-FAR is in NYC coords and MUST be excluded.
    assert "M-FAR" not in serials
    assert {"M-1", "M-2"}.issubset(serials)


def test_layer_dtr(app_client):
    client, SessionLocal = app_client
    _seed_feeder_with_dtrs(SessionLocal)

    resp = client.get("/gis/layers", params={"layer": "dtr"})
    assert resp.status_code == 200
    feats = resp.json()["features"]
    assert len(feats) == 2
    assert all(f["properties"]["layer"] == "dtr" for f in feats)
    assert any(f["properties"]["loading_pct"] == 90.0 for f in feats)


def test_layer_feeder_synthesizes_line(app_client):
    client, SessionLocal = app_client
    _seed_feeder_with_dtrs(SessionLocal)

    resp = client.get("/gis/layers", params={"layer": "feeder"})
    assert resp.status_code == 200
    feats = resp.json()["features"]
    assert len(feats) == 1
    assert feats[0]["geometry"]["type"] == "LineString"
    assert feats[0]["properties"]["name"] == "FDR-A"
    assert feats[0]["properties"]["loading_pct"] is not None


def test_layer_pole_returns_empty_when_no_table(app_client):
    client, SessionLocal = app_client
    resp = client.get("/gis/layers", params={"layer": "pole"})
    assert resp.status_code == 200
    assert resp.json() == {"type": "FeatureCollection", "features": []}


def test_layer_invalid_layer(app_client):
    client, _ = app_client
    resp = client.get("/gis/layers", params={"layer": "nope"})
    assert resp.status_code == 400


def test_layer_invalid_bbox(app_client):
    client, _ = app_client
    resp = client.get("/gis/layers", params={"layer": "meter", "bbox": "1,2,3"})
    assert resp.status_code == 400


def test_heatmap_alarms_aggregates(app_client):
    client, SessionLocal = app_client
    _seed_feeder_with_dtrs(SessionLocal)

    s = SessionLocal()
    s.add_all(
        [
            Alarm(
                alarm_type=AlarmType.TAMPER,
                severity=AlarmSeverity.CRITICAL,
                status=AlarmStatus.ACTIVE,
                meter_serial="M-1",
                title="Tamper on M-1",
                latitude=26.01,
                longitude=75.01,
            ),
            Alarm(
                alarm_type=AlarmType.TAMPER,
                severity=AlarmSeverity.HIGH,
                status=AlarmStatus.ACTIVE,
                meter_serial="M-2",
                title="Tamper on M-2",
                latitude=26.015,
                longitude=75.015,
            ),
            Alarm(
                alarm_type=AlarmType.OUTAGE,
                severity=AlarmSeverity.MEDIUM,
                status=AlarmStatus.RESOLVED,  # filtered out
                meter_serial="M-1",
                title="Old outage",
                latitude=26.01,
                longitude=75.01,
            ),
        ]
    )
    s.commit()
    s.close()

    resp = client.get("/gis/heatmap/alarms", params={"grid_deg": 0.1})
    assert resp.status_code == 200
    cells = resp.json()["cells"]
    # Two active alarms falling in the same 0.1° bucket.
    assert len(cells) == 1
    c = cells[0]
    assert c["count"] == 2
    assert c["critical"] == 1
    assert c["high"] == 1
