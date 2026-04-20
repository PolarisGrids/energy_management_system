"""W2.T11 — sensor history sourced from DB, not random synth."""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.endpoints import sensors as sensors_ep
from app.core.config import SSOTMode, settings
from app.models.sensor import TransformerSensor, SensorStatus
from app.models.sensor_reading import TransformerSensorReading


def test_sensors_module_has_no_random_history():
    """The random synthesiser must be gone from the sensors endpoint module.

    Scans non-comment / non-docstring code only (W2.T11 guarantee).
    """
    import ast

    src = inspect.getsource(sensors_ep)
    tree = ast.parse(src)

    # 1. No `import random` anywhere.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "random", "random module must not be imported"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "random", "random module must not be imported"

    # 2. No `random.uniform(...)` calls in any function body.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "uniform":
            value = node.value
            if isinstance(value, ast.Name) and value.id == "random":
                raise AssertionError("random.uniform(...) call found — should be gone")


@pytest.fixture
def seed_sensor(db):
    from app.models.meter import Feeder, Transformer

    feeder = Feeder(name="FDR", substation="S", voltage_kv=11.0, capacity_kva=100.0)
    db.add(feeder)
    db.flush()
    tx = Transformer(name="DTR", feeder_id=feeder.id, latitude=0, longitude=0, capacity_kva=100.0)
    db.add(tx)
    db.flush()
    s = TransformerSensor(
        transformer_id=tx.id,
        sensor_type="oil_temp",
        name="oil temp",
        value=70.0,
        unit="C",
        status=SensorStatus.NORMAL,
    )
    db.add(s)
    db.commit()
    return s


def test_empty_history_returns_banner_in_non_strict(client, seed_sensor, monkeypatch):
    monkeypatch.setattr(settings, "SSOT_MODE", SSOTMode.mirror)
    resp = client.get(f"/api/v1/sensors/{seed_sensor.id}/history?hours=6")
    assert resp.status_code == 200
    body = resp.json()
    assert body["history"] == []
    assert "No historical sensor data" in (body.get("banner") or "") or \
           "not yet provisioned" in (body.get("banner") or "")


def test_empty_history_in_strict_mode_returns_503(client, seed_sensor, monkeypatch):
    monkeypatch.setattr(settings, "SSOT_MODE", SSOTMode.strict)
    resp = client.get(f"/api/v1/sensors/{seed_sensor.id}/history?hours=6")
    assert resp.status_code == 503


def test_history_returns_rows_when_present(client, seed_sensor, db, monkeypatch):
    monkeypatch.setattr(settings, "SSOT_MODE", SSOTMode.mirror)
    match_key = str(seed_sensor.id)
    now = datetime.now(timezone.utc)
    for i in range(3):
        db.add(
            TransformerSensorReading(
                sensor_id=match_key,
                dtr_id="DTR",
                type="oil_temp",
                value=70 + i,
                unit="C",
                ts=now - timedelta(minutes=30 * i),
            )
        )
    db.commit()
    resp = client.get(f"/api/v1/sensors/{seed_sensor.id}/history?hours=6")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["history"]) == 3
    assert body.get("banner") is None
