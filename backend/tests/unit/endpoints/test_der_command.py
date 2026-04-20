"""W2.T12 — DER command via HES with feature-flag gating."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.der_ems import DERAssetEMS, DERCommandEMS


@pytest.fixture
def seed_der(db):
    asset = DERAssetEMS(id="PV-TEST-1", type="pv", name="PV 1", capacity_kw=50.0)
    db.add(asset)
    db.commit()
    return asset


def test_der_command_feature_flag_off_returns_503(client, seed_der, monkeypatch):
    monkeypatch.setattr(settings, "SMART_INVERTER_COMMANDS_ENABLED", False)
    resp = client.post(
        "/api/v1/der/PV-TEST-1/command",
        json={"command_type": "DER_CURTAIL", "setpoint": 25.0},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "feature disabled"


def test_der_command_publishes_and_persists(client, fake_hes, seed_der, db):
    resp = client.post(
        "/api/v1/der/PV-TEST-1/command",
        json={"command_type": "DER_CURTAIL", "setpoint": 25.0},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["command_type"] == "DER_CURTAIL"
    assert body["status"] == "QUEUED"

    assert any(c[0] == "post_command" for c in fake_hes.calls)
    row = db.query(DERCommandEMS).filter(DERCommandEMS.id == body["command_id"]).first()
    assert row is not None
    assert row.asset_id == "PV-TEST-1"


def test_der_command_unknown_asset_404(client, fake_hes):
    resp = client.post(
        "/api/v1/der/PV-MISSING/command",
        json={"command_type": "DER_CURTAIL", "setpoint": 25.0},
    )
    assert resp.status_code == 404
