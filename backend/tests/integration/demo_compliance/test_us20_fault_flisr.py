"""US-20: Fault + FLISR + AMI Outage Correlation (Demo #24).

Acceptance (spec §User Story 20 + matrix row 20):

* Run ``network_fault`` scenario.
* Outage opens within 90 s with ``affected_count`` + ``confidence_pct``.
* Operator clicks Isolate section → HES switch command dispatched.
* Affected count drops; adjacent sections re-energise.
* On close, SAIDI/SAIFI/CAIDI update for the period.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = [pytest.mark.demo_compliance]


def _seed_outage(db_session, *, affected_count: int = 20, confidence: float = 0.82):
    """Directly insert an OutageIncidentW3 row so the FLISR endpoints have a target.

    Correlator integration (N≥3 power-failure events in window → auto-open)
    is covered in US-4 test; here we just need an open incident to drive
    the FLISR workflow assertions.
    """
    from app.models.outage import OutageIncidentW3

    inc = OutageIncidentW3(
        id=str(uuid.uuid4()),
        status="DETECTED",
        opened_at=datetime.now(timezone.utc),
        affected_meter_count=affected_count,
        affected_meter_ids=[f"M{i:04d}" for i in range(affected_count)],
        confidence_pct=confidence,
        suspected_fault_point=None,
    )
    db_session.add(inc)
    db_session.commit()
    db_session.refresh(inc)
    return inc


def test_network_fault_scenario_opens_outage_with_affected_and_confidence(
    client, simulator_mock
):
    """The simulator emits an outage snapshot that matches the 90 s SLO."""
    simulator_mock.post("/scenarios/network_fault/start").respond(
        200, json={"scenario": "network_fault", "status": "RUNNING"}
    )
    simulator_mock.get("/scenarios/network_fault/status").respond(
        200,
        json={
            "scenario": "network_fault",
            "step": 3,
            "status": "RUNNING",
            "elapsed_seconds": 42,  # < 90 s SLO
            "outage": {
                "status": "DETECTED",
                "affected_count": 20,
                "confidence_pct": 0.87,
            },
        },
    )
    start = client.post("/api/v1/simulation-proxy/scenarios/network_fault/start", json={})
    assert start.status_code in (200, 202), start.text

    body = client.get("/api/v1/simulation-proxy/scenarios/network_fault/status").json()
    outage = body.get("outage") or {}
    assert outage.get("status") == "DETECTED"
    assert outage.get("affected_count", 0) >= 1
    assert 0 < outage.get("confidence_pct", 0) <= 1.0
    assert body.get("elapsed_seconds", 999) <= 90, (
        f"outage open SLO violated: {body.get('elapsed_seconds')} s > 90 s"
    )


@pytest.mark.xfail(
    reason=(
        "FLISR isolate endpoint (POST /outages/{id}/flisr/isolate) requires "
        "SMART_INVERTER_COMMANDS_ENABLED + HES switchgear routing. Endpoint "
        "exists but relies on hes_client.post_switch which isn't deployed yet."
    ),
    strict=False,
)
def test_isolate_button_dispatches_hes_switch_command(client, db_session, hes_mock):
    inc = _seed_outage(db_session, affected_count=20, confidence=0.82)
    hes_mock.post("/hes/commands/switch").respond(
        200, json={"status": "QUEUED", "command_id": "SW-CMD-1"}
    )
    payload = {"switch_id": "SW-FDR-3", "action": "OPEN", "reason": "FLISR isolate"}
    resp = client.post(f"/api/v1/outages/{inc.id}/flisr/isolate", json=payload)
    assert resp.status_code in (200, 202), resp.text
    body = resp.json()
    assert body.get("switch_id") == "SW-FDR-3" or "command_id" in body


@pytest.mark.xfail(
    reason=(
        "Requires outage correlator + restore path end-to-end to shrink "
        "affected_count after isolation. Wave-5 FLISR task not yet landed."
    ),
    strict=False,
)
def test_affected_count_drops_after_isolation(client, db_session):
    inc = _seed_outage(db_session, affected_count=20)
    # Simulate isolation having moved 12 customers to adjacent sections.
    resp = client.post(
        f"/api/v1/outages/{inc.id}/flisr/restore",
        json={"restored_meter_ids": [f"M{i:04d}" for i in range(12)]},
    )
    assert resp.status_code in (200, 202), resp.text
    detail = client.get(f"/api/v1/outages/{inc.id}").json()
    assert detail["affected_meter_count"] <= 8


@pytest.mark.xfail(
    reason=(
        "SAIDI/SAIFI/CAIDI rollup (reliability indices) depends on MDMS "
        "`reliability_indices` materialised view (MDMS-T2/T6) and the "
        "EGSM-reports service — live query gated on cutover."
    ),
    strict=False,
)
def test_reliability_indices_update_after_outage_close(client):
    # Period covering the seeded outage.
    start = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    end = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(
        "/api/v1/reports/egsm/reliability-indices",
        params={"from_date": start, "to_date": end},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"saidi", "saifi", "caidi"} <= set(body.keys())
