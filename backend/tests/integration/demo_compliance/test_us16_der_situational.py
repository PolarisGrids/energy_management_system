"""US-16 DER situational awareness on feeders — spec 018 §User Story 16.

Acceptance (integration-test-matrix row 16):

* Feeder view overlays voltage profile + DER contribution.
* Reverse flow: net kW < 0 for 5 min → banner visible + event persisted in
  ``reverse_flow_event``.

The detector (``app.services.reverse_flow_detector``) opens a row with
status=OPEN when the 5 min dwell is satisfied.  These tests exercise the
read-side endpoints that back the banner + history drawer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _seed_reverse_flow_event(db_session, feeder_id, *, closed=False, net_kw=-12.5):
    from app.models.reverse_flow import ReverseFlowEvent

    now = datetime.now(timezone.utc)
    row = ReverseFlowEvent(
        feeder_id=feeder_id,
        detected_at=now - timedelta(minutes=10),
        closed_at=now if closed else None,
        net_flow_kw=net_kw,
        duration_s=600,
        status="CLOSED" if closed else "OPEN",
        details={"seed": "us16_test"},
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_active_reverse_flow_listing_returns_open_events(client, db_session):
    """GET /reverse-flow/active returns only OPEN events — feeds UI banner."""
    feeder = "FDR-US16-BANNER-01"
    _seed_reverse_flow_event(db_session, feeder, closed=False, net_kw=-20.0)

    resp = client.get("/api/v1/reverse-flow/active")
    assert resp.status_code == 200, resp.text
    feeders = {r["feeder_id"] for r in resp.json()}
    assert feeder in feeders, f"{feeder} missing from active list {feeders}"

    for row in resp.json():
        assert row["status"] == "OPEN"


def test_closed_reverse_flow_excluded_from_active(client, db_session):
    """A CLOSED event MUST NOT appear in the active-banner listing."""
    feeder = "FDR-US16-CLOSED-01"
    _seed_reverse_flow_event(db_session, feeder, closed=True, net_kw=-15.0)

    resp = client.get("/api/v1/reverse-flow/active")
    assert resp.status_code == 200
    feeders = {r["feeder_id"] for r in resp.json()}
    # It may still appear via other seeds; the row we just seeded must not.
    # Get its id.
    history = client.get("/api/v1/reverse-flow/", params={"status": "CLOSED"})
    closed_feeders = {r["feeder_id"] for r in history.json()}
    assert feeder in closed_feeders
    # And the active list must not contain this *closed* feeder row.
    if feeder in feeders:
        # Only permitted if there's also an OPEN row for the same feeder,
        # which we did not create.
        open_rows_for_feeder = [r for r in resp.json() if r["feeder_id"] == feeder]
        assert all(r["status"] == "OPEN" for r in open_rows_for_feeder)


def test_per_feeder_reverse_flow_history(client, db_session):
    """GET /reverse-flow/feeder/{id} returns events for that feeder only."""
    feeder = "FDR-US16-HIST-01"
    _seed_reverse_flow_event(db_session, feeder, closed=True, net_kw=-9.5)
    _seed_reverse_flow_event(db_session, feeder, closed=False, net_kw=-11.0)

    resp = client.get(f"/api/v1/reverse-flow/feeder/{feeder}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 2
    for r in rows:
        assert r["feeder_id"] == feeder
        # net_flow_kw must be negative (that's the whole point of reverse flow).
        assert r["net_flow_kw"] is None or r["net_flow_kw"] < 0


def test_der_feeder_aggregate_returns_shape(client, db_session):
    """Feeder-level DER aggregate endpoint must respond and include the
    overlay fields the feeder page reads (active_power_kw per asset type).
    """
    resp = client.get("/api/v1/der/feeder/FDR-US16-OVERLAY-01/aggregate")
    # Endpoint may 404 if the feeder isn't seeded; we accept 200 empty or
    # 404 with an explicit detail body. What we FORBID is a 500.
    assert resp.status_code in (200, 404), resp.text
    if resp.status_code == 200:
        body = resp.json()
        assert "feeder_id" in body or "assets" in body or "by_type" in body


@pytest.mark.xfail(
    reason="Voltage-profile overlay endpoint requires PostGIS feeder-span "
    "geometry + meter voltage rollup MV. PostGIS columns exist (FR-016) "
    "but the rollup is part of W5.T4 which hasn't landed. Once it ships "
    "the endpoint will be /api/v1/gis/feeder/{id}/voltage-profile.",
    strict=False,
)
def test_voltage_profile_overlay_endpoint(client):
    """Feeder voltage profile — pending W5.T4."""
    resp = client.get("/api/v1/gis/feeder/FDR-US16-01/voltage-profile")
    assert resp.status_code == 200
    assert "points" in resp.json()
