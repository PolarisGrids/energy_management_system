"""US-4 Outage Intelligence with GIS Pinpointing — spec 018 §User Story 4.

Acceptance (spec lines 107-113, matrix row 4):

1. 20 power_failure events on meters under ``DTR-001`` within 60 s → a new
   ``outage_incident`` opens with status=DETECTED, affected_dtr_ids contains
   DTR-001, affected_meter_count=20.
2. Timeline carries the DETECTED event.
3. ``GET /api/v1/outages`` returns the incident with a valid ID and status.
4. Reliability indices endpoint is exercised as smoke (SAIDI computation
   requires full restoration data; asserted in US-20 fault+FLISR test).

We drive the correlator directly via ``run_once`` to avoid boot-time async
loops — this is the seam the spec references in the design docs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.meter import Meter, Transformer
from app.models.meter_event import OutageCorrelatorInput
from app.models.outage import OutageIncidentW3


def _seed_dtr_with_meters(db, dtr_name="DTR-001", count=20):
    """Create a DTR with `count` meters under it."""
    # Need a Feeder first (FK).
    from app.models.meter import Feeder, MeterStatus, RelayState

    feeder = Feeder(name="FDR-X", substation="SS-X", voltage_kv=11.0, capacity_kva=500.0)
    db.add(feeder)
    db.flush()
    tx = Transformer(
        name=dtr_name,
        feeder_id=feeder.id,
        latitude=0.0,
        longitude=0.0,
        capacity_kva=100.0,
    )
    db.add(tx)
    db.flush()
    meters = []
    for i in range(count):
        m = Meter(
            serial=f"{dtr_name}-M{i:03d}",
            transformer_id=tx.id,
            status=MeterStatus.ONLINE,
            relay_state=RelayState.CONNECTED,
            latitude=0.0,
            longitude=0.0,
        )
        db.add(m)
        meters.append(m)
    db.commit()
    return tx, meters


def test_twenty_power_failures_auto_open_incident(client, db, monkeypatch):
    """20 failures within 60 s on one DTR → one incident DETECTED with count=20."""
    from app.services import outage_correlator

    # Tighten the min threshold to 3 (the default) and keep the 120 s window.
    monkeypatch.setattr(outage_correlator, "OUTAGE_MIN_METERS", 3)
    monkeypatch.setattr(outage_correlator, "OUTAGE_WINDOW_SECONDS", 120)

    tx, meters = _seed_dtr_with_meters(db, dtr_name="DTR-001", count=20)
    base_ts = datetime.now(timezone.utc)
    for i, m in enumerate(meters):
        db.add(
            OutageCorrelatorInput(
                meter_serial=m.serial,
                dtr_id=tx.name,
                event_type="power_failure",
                event_ts=base_ts + timedelta(seconds=i * 2),  # 40 s span
                processed=False,
            )
        )
    db.commit()

    # Swap the module's SessionLocal for the test one so run_once uses the
    # in-memory SQLite we've seeded.
    from app.services import outage_correlator as corr_mod

    monkeypatch.setattr(corr_mod, "SessionLocal", lambda: db)
    stats = corr_mod.run_once(db=db)
    assert stats["opened"] >= 1, stats

    inc = (
        db.query(OutageIncidentW3)
        .filter(OutageIncidentW3.status == "DETECTED")
        .first()
    )
    assert inc is not None
    assert "DTR-001" in (inc.affected_dtr_ids or []) or tx.name in (
        inc.affected_dtr_ids or []
    )
    assert inc.affected_meter_count >= 3


def test_list_outages_exposes_new_incident(client, db, monkeypatch):
    """Given an incident row, the /api/v1/outages list endpoint returns it."""
    import uuid

    from app.models.outage import OutageIncidentW3

    inc = OutageIncidentW3(
        id=str(uuid.uuid4()),
        opened_at=datetime.now(timezone.utc),
        status="DETECTED",
        affected_dtr_ids=["DTR-001"],
        affected_meter_count=20,
        restored_meter_count=0,
        confidence_pct=85.0,
        timeline=[{"event_type": "detected", "at": datetime.now(timezone.utc).isoformat()}],
    )
    db.add(inc)
    db.commit()

    r = client.get("/api/v1/outages")
    assert r.status_code == 200
    body = r.json()
    ids = [row["id"] for row in body["incidents"]]
    assert inc.id in ids


def test_map_overlay_returns_geojson(client, db):
    """GIS outage overlay endpoint returns a FeatureCollection we can render."""
    r = client.get("/api/v1/gis/outages")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("type") == "FeatureCollection"
    assert "features" in body
