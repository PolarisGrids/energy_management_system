"""W4 / no-mock-data — consumption endpoints.

Confirms the {ok, data, source, as_of} envelope shape and that the source flag
flips between ``"mdms"`` (happy path, upstream returns rows) and ``"ems-local"``
(fallback — upstream disabled or raised).
"""
from __future__ import annotations

import pytest

from app.core.config import settings


class _FakeMDMS:
    def __init__(self):
        self.next: dict | None = None
        self.raise_exc: Exception | None = None
        self.calls: list[tuple[str, str, dict]] = []

    async def list_egsm_report(self, category: str, report: str, params=None):
        self.calls.append((category, report, dict(params or {})))
        if self.raise_exc:
            raise self.raise_exc
        return self.next or {"rows": []}


@pytest.fixture
def fake_mdms(monkeypatch):
    fake = _FakeMDMS()
    import app.api.v1.endpoints.consumption as consumption_ep

    monkeypatch.setattr(consumption_ep, "mdms_client", fake)
    monkeypatch.setattr(settings, "MDMS_ENABLED", True)
    yield fake


# ── /summary ─────────────────────────────────────────────────────────────────


def test_summary_source_mdms_when_upstream_has_rows(client, fake_mdms):
    fake_mdms.next = {
        "rows": [
            {"total_import_kwh": 100, "total_export_kwh": 20, "peak_demand_kw": 8, "avg_power_factor": 0.95},
            {"total_import_kwh": 150, "total_export_kwh": 30, "peak_demand_kw": 12, "avg_power_factor": 0.93},
        ]
    }
    r = client.get("/api/v1/consumption/summary", params={"feeder": "F1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["source"] == "mdms"
    assert "as_of" in body
    assert body["data"]["import_kwh"] == 250.0
    assert body["data"]["export_kwh"] == 50.0
    assert body["data"]["net_kwh"] == 200.0
    # Upstream called with feeder scope.
    assert fake_mdms.calls[0][0] == "energy-audit"
    assert fake_mdms.calls[0][1] == "monthly-consumption"
    assert fake_mdms.calls[0][2]["feeder"] == "F1"


def test_summary_source_ems_local_on_upstream_empty(client, fake_mdms):
    fake_mdms.next = {"rows": []}
    r = client.get("/api/v1/consumption/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "ems-local"
    assert "banner" in body["data"]


def test_summary_source_ems_local_on_upstream_error(client, fake_mdms):
    fake_mdms.raise_exc = RuntimeError("MDMS down")
    r = client.get("/api/v1/consumption/summary")
    assert r.status_code == 200
    assert r.json()["source"] == "ems-local"


def test_summary_mdms_disabled_goes_local(client, fake_mdms, monkeypatch):
    monkeypatch.setattr(settings, "MDMS_ENABLED", False)
    r = client.get("/api/v1/consumption/summary")
    assert r.status_code == 200
    assert r.json()["source"] == "ems-local"
    # When MDMS is off we must not call the client.
    assert fake_mdms.calls == []


# ── /load-profile ─────────────────────────────────────────────────────────────


def test_load_profile_mdms_series_shape(client, fake_mdms):
    fake_mdms.next = {
        "series": [
            {"ts": "2026-04-18T00:00:00Z", "kw_import": 12.5, "kw_export": 1.2, "kvarh": 0.3},
            {"ts": "2026-04-18T01:00:00Z", "kw_import": 10.0, "kw_export": 0.5, "kvarh": 0.1},
        ]
    }
    r = client.get("/api/v1/consumption/load-profile", params={"meter": "M001", "interval": "1h"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mdms"
    assert len(body["data"]["points"]) == 2
    assert body["data"]["points"][0]["kw_import"] == 12.5


def test_load_profile_fallback_envelope_shape(client, fake_mdms):
    fake_mdms.raise_exc = RuntimeError("boom")
    r = client.get("/api/v1/consumption/load-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "ems-local"
    assert "points" in body["data"]
    assert "interval" in body["data"]


# ── /feeder-breakdown ─────────────────────────────────────────────────────────


def test_feeder_breakdown_mdms(client, fake_mdms):
    fake_mdms.next = {
        "rows": [
            {"feeder_id": 1, "feeder_name": "FDR-1", "total_kwh": 1000, "loss_kwh": 50, "loss_pct": 5.0},
            {"feeder_id": 2, "feeder_name": "FDR-2", "total_kwh": 800, "loss_kwh": 30, "loss_pct": 3.75},
        ]
    }
    r = client.get("/api/v1/consumption/feeder-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mdms"
    assert body["data"]["rows"][0]["feeder"] == "FDR-1"
    assert body["data"]["rows"][0]["kwh"] == 1000.0


def test_feeder_breakdown_fallback(client, fake_mdms):
    fake_mdms.raise_exc = RuntimeError("nope")
    r = client.get("/api/v1/consumption/feeder-breakdown")
    assert r.status_code == 200
    assert r.json()["source"] == "ems-local"


# ── /by-class ─────────────────────────────────────────────────────────────────


def test_by_class_mdms(client, fake_mdms):
    fake_mdms.next = {
        "rows": [
            {"tariff_class": "Residential", "kwh": 650, "pct": 65},
            {"tariff_class": "Commercial", "kwh": 250, "pct": 25},
        ]
    }
    r = client.get("/api/v1/consumption/by-class", params={"period": "month"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mdms"
    assert body["data"]["rows"][0]["tariff_class"] == "Residential"


def test_by_class_rejects_bad_period(client, fake_mdms):
    r = client.get("/api/v1/consumption/by-class", params={"period": "year"})
    assert r.status_code == 422


# ── /monthly ──────────────────────────────────────────────────────────────────


def test_monthly_mdms(client, fake_mdms):
    fake_mdms.next = {
        "rows": [
            {"billing_month": "2026-01", "total_import_kwh": 4800, "total_export_kwh": 120},
            {"billing_month": "2026-02", "total_import_kwh": 5100, "total_export_kwh": 140},
        ]
    }
    r = client.get("/api/v1/consumption/monthly", params={"months": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mdms"
    assert body["data"]["rows"][0]["month"] == "2026-01"
    assert body["data"]["rows"][0]["import_kwh"] == 4800.0
