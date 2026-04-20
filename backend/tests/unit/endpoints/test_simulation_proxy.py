"""Spec 018 W3.T14 — scenario API proxy tests.

Mocks the resilient HTTP client used by `simulation_proxy` to verify that
inbound paths map to the expected simulator paths and that trace-context /
authorization headers are forwarded.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base


_TABLES_FOR_SUITE = ("users", "feeders", "transformers", "meters")


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_FOR_SUITE if t in Base.metadata.tables]
    Base.metadata.create_all(eng, tables=tables)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def SessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.cfg = type("Cfg", (), {"base_url": "http://fake-simulator:9200"})()
        self.next_response = _FakeResp({"scenarios": ["solar_overvoltage"]})

    async def request(self, method, path, params=None, json=None, headers=None):
        self.calls.append({
            "method": method, "path": path,
            "params": params, "json": json,
            "headers": headers or {},
        })
        return self.next_response


@pytest.fixture
def fake_simulator(monkeypatch):
    fake = _FakeClient()
    from app.api.v1.endpoints import simulation_proxy as sp

    monkeypatch.setattr(sp, "_get_client", lambda: fake)
    return fake


def test_list_scenarios_forwards_get(client, fake_simulator):
    r = client.get("/api/v1/simulation-proxy/scenarios")
    assert r.status_code == 200
    assert fake_simulator.calls[-1]["method"] == "GET"
    assert fake_simulator.calls[-1]["path"] == "/scenarios"
    # ems_correlation_id is stamped on every response
    assert r.headers.get("ems-correlation-id")


def test_scenario_start_posts_to_simulator(client, fake_simulator):
    fake_simulator.next_response = _FakeResp({"status": "RUNNING", "step": 0})
    r = client.post(
        "/api/v1/simulation-proxy/scenarios/solar_overvoltage/start",
        json={"preset": "demo"},
        headers={"traceparent": "00-abc-def-01"},
    )
    assert r.status_code == 200
    call = fake_simulator.calls[-1]
    assert call["method"] == "POST"
    assert call["path"] == "/scenarios/solar_overvoltage/start"
    assert call["json"] == {"preset": "demo"}
    assert call["headers"].get("traceparent") == "00-abc-def-01"


def test_scenario_step_forwards_path(client, fake_simulator):
    fake_simulator.next_response = _FakeResp({"step": 3, "voltage_pu": 1.05})
    r = client.post("/api/v1/simulation-proxy/scenarios/solar_overvoltage/step")
    assert r.status_code == 200
    assert fake_simulator.calls[-1]["path"] == "/scenarios/solar_overvoltage/step"


def test_scenario_stop_forwards_path(client, fake_simulator):
    r = client.post("/api/v1/simulation-proxy/scenarios/solar_overvoltage/stop")
    assert r.status_code == 200
    assert fake_simulator.calls[-1]["path"] == "/scenarios/solar_overvoltage/stop"


def test_sequence_start_forwards_path(client, fake_simulator):
    r = client.post("/api/v1/simulation-proxy/sequences/demo/start")
    assert r.status_code == 200
    assert fake_simulator.calls[-1]["path"] == "/sequences/demo/start"


def test_simulator_unreachable_returns_503(client, fake_simulator, monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(fake_simulator, "request", _boom)
    r = client.get("/api/v1/simulation-proxy/scenarios")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "simulator_unreachable"
