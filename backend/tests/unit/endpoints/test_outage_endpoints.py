"""Unit tests for spec 018 W3 outage endpoints.

Exercises:
    * GET /api/v1/outages             — list + status filter
    * GET /api/v1/outages/{id}        — detail + timeline
    * POST /api/v1/outages/{id}/acknowledge
    * POST /api/v1/outages/{id}/note
    * POST /api/v1/outages/{id}/dispatch-crew — WFM_ENABLED gate + happy path
    * POST /api/v1/outages/{id}/flisr/isolate — feature gate + HES call
    * GET /api/v1/gis/outages         — GeoJSON shape
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.models.outage import OutageIncidentW3, OutageTimelineEvent


def _seed_incident(db, *, status: str = "DETECTED", dtr: str = "DTR-1") -> OutageIncidentW3:
    inc = OutageIncidentW3(
        id=str(uuid.uuid4()),
        opened_at=datetime.now(timezone.utc),
        status=status,
        affected_dtr_ids=[dtr],
        affected_meter_count=5,
        restored_meter_count=0,
        confidence_pct=62.5,
        timeline=[],
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


def test_list_outages_empty(client):
    resp = client.get("/api/v1/outages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["incidents"] == []


def test_list_outages_filter(client, db):
    _seed_incident(db, status="DETECTED")
    _seed_incident(db, status="RESTORED")

    resp = client.get("/api/v1/outages", params={"status": "DETECTED"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["incidents"][0]["status"] == "DETECTED"


def test_get_outage_detail_with_timeline(client, db):
    inc = _seed_incident(db)
    db.add(
        OutageTimelineEvent(
            incident_id=inc.id,
            event_type="detected",
            details={"dtr_id": "DTR-1"},
        )
    )
    db.commit()

    resp = client.get(f"/api/v1/outages/{inc.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == inc.id
    assert len(body["timeline"]) == 1
    assert body["timeline"][0]["event_type"] == "detected"


def test_get_outage_not_found(client):
    resp = client.get(f"/api/v1/outages/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_acknowledge_outage(client, db):
    inc = _seed_incident(db)
    resp = client.post(
        f"/api/v1/outages/{inc.id}/acknowledge",
        json={"note": "on it"},
    )
    assert resp.status_code == 200
    events = (
        db.query(OutageTimelineEvent).filter_by(incident_id=inc.id).all()
    )
    assert any(e.event_type == "acknowledged" for e in events)


def test_acknowledge_closed_outage_conflict(client, db):
    inc = _seed_incident(db, status="RESTORED")
    resp = client.post(f"/api/v1/outages/{inc.id}/acknowledge", json={})
    assert resp.status_code == 409


def test_add_note(client, db):
    inc = _seed_incident(db)
    resp = client.post(
        f"/api/v1/outages/{inc.id}/note",
        json={"note": "rerouting feeder"},
    )
    assert resp.status_code == 200


def test_dispatch_crew_wfm_disabled(client, db, monkeypatch):
    monkeypatch.setattr(settings, "WFM_ENABLED", False)
    inc = _seed_incident(db)
    resp = client.post(
        f"/api/v1/outages/{inc.id}/dispatch-crew",
        json={"crew_id": "CREW-7"},
    )
    assert resp.status_code == 503
    assert "WFM" in resp.json()["detail"]


def test_dispatch_crew_happy_path(client, db, monkeypatch):
    monkeypatch.setattr(settings, "WFM_ENABLED", True)

    # Patch the MDMS client used by the endpoint.
    import app.api.v1.endpoints.outage as outage_ep

    class _FakeResp:
        def json(self):
            return {"work_order_id": "WO-123"}

    class _FakeMDMS:
        async def create_wfm_work_order(self, payload):
            self.last = payload
            return _FakeResp()

    fake = _FakeMDMS()
    monkeypatch.setattr(outage_ep, "mdms_client", fake)

    inc = _seed_incident(db)
    resp = client.post(
        f"/api/v1/outages/{inc.id}/dispatch-crew",
        json={"crew_id": "CREW-7", "eta_minutes": 30},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DISPATCHED"
    assert fake.last["crew_id"] == "CREW-7"


def test_flisr_isolate_feature_flag_gate(client, db, monkeypatch):
    monkeypatch.setattr(settings, "SMART_INVERTER_COMMANDS_ENABLED", False)
    inc = _seed_incident(db)
    resp = client.post(f"/api/v1/outages/{inc.id}/flisr/isolate", json={})
    assert resp.status_code == 503


def test_flisr_isolate_happy_path(client, db, monkeypatch, fake_hes):
    monkeypatch.setattr(settings, "SMART_INVERTER_COMMANDS_ENABLED", True)
    monkeypatch.setattr(settings, "HES_ENABLED", True)

    # Make sure the endpoint module picks up our fake HES.
    import app.api.v1.endpoints.outage as outage_ep
    monkeypatch.setattr(outage_ep, "hes_client", fake_hes)
    fake_hes.next_response = {"command_id": "HES-CMD-99", "accepted": True}

    inc = _seed_incident(db)
    resp = client.post(
        f"/api/v1/outages/{inc.id}/flisr/isolate",
        json={"target_switch_id": "SW-42"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "isolate"
    assert body["status"] == "ACCEPTED"
    # HES was called with switch_open
    assert any(
        call[0] == "post_command" and call[1]["type"] == "switch_open"
        for call in fake_hes.calls
    )


def test_gis_outages_overlay(client, db):
    # Seed an incident and its DTR geometry via Transformer lat/lon.
    from app.models.meter import Feeder, Transformer

    feeder = Feeder(name="FDR-X", substation="SS-X", voltage_kv=11.0, capacity_kva=500.0)
    db.add(feeder)
    db.flush()
    tx = Transformer(
        name="DTR-GEO",
        feeder_id=feeder.id,
        latitude=-26.2041,
        longitude=28.0473,
        capacity_kva=100.0,
    )
    db.add(tx)
    db.commit()
    _seed_incident(db, dtr="DTR-GEO")

    resp = client.get("/api/v1/gis/outages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    feat = body["features"][0]
    assert feat["geometry"]["type"] == "Point"
    assert feat["geometry"]["coordinates"] == [28.0473, -26.2041]
    assert feat["properties"]["status"] == "DETECTED"
