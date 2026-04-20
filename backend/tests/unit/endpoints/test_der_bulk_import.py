"""W2.T8.5 — DER bulk-import from simulator."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.der_ems import DERAssetEMS


@pytest.fixture
def sim_headers(monkeypatch):
    monkeypatch.setattr(settings, "SIMULATOR_API_KEY", "secret-sim-key")
    return {"Authorization": "Bearer secret-sim-key"}


def _asset(id_: str, type_: str = "pv", dtr: str | None = None) -> dict:
    return {
        "id": id_,
        "type": type_,
        "name": f"Asset {id_}",
        "dtr_id": dtr,
        "capacity_kw": 50.0,
        "lat": -26.26,
        "lon": 27.85,
        "metadata": {"note": "test"},
    }


def test_bulk_import_inserts_and_updates(client, sim_headers, db):
    payload = {
        "preset": "demo-21-apr-2026",
        "assets": [_asset("PV-001"), _asset("BESS-001", "bess")],
    }
    resp = client.post("/api/v1/der/bulk-import", json=payload, headers=sim_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 2
    assert body["updated"] == 0
    assert body["preset"] == "demo-21-apr-2026"
    assert db.query(DERAssetEMS).count() == 2

    # Re-post same payload → becomes updates.
    resp2 = client.post("/api/v1/der/bulk-import", json=payload, headers=sim_headers)
    b2 = resp2.json()
    assert b2["inserted"] == 0
    assert b2["updated"] == 2


def test_bulk_import_soft_dtr_validation(client, sim_headers, db):
    payload = {
        "preset": "demo",
        "assets": [_asset("PV-X", dtr="DTR-UNKNOWN")],
    }
    resp = client.post("/api/v1/der/bulk-import", json=payload, headers=sim_headers)
    # Unknown DTR → warning-only; still 200 + inserted.
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert len(body["errors"]) == 0  # no known DTRs at all → skip validation


def test_bulk_import_rejects_missing_bearer(client):
    resp = client.post(
        "/api/v1/der/bulk-import",
        json={"preset": "x", "assets": [_asset("PV-Z")]},
    )
    assert resp.status_code == 401


def test_bulk_import_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setattr(settings, "SIMULATOR_API_KEY", "correct")
    resp = client.post(
        "/api/v1/der/bulk-import",
        json={"preset": "x", "assets": [_asset("PV-Z")]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401
