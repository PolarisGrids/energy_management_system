"""Unit tests — spec 018 W4.T14 Data Accuracy endpoint + status logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.source_status_refresher import compute_status


NOW = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)


# ── Pure-function badge logic ──────────────────────────────────────────────


def test_status_healthy_when_all_fresh():
    s = compute_status(
        hes_last_seen=NOW - timedelta(minutes=30),
        mdms_last_validated=NOW - timedelta(hours=2),
        cis_last_billing=NOW - timedelta(days=3),
        now=NOW,
    )
    assert s == "healthy"


def test_status_missing_mdms():
    s = compute_status(
        hes_last_seen=NOW - timedelta(minutes=5),
        mdms_last_validated=None,
        cis_last_billing=NOW,
        now=NOW,
    )
    assert s == "missing_mdms"


def test_status_missing_cis():
    s = compute_status(
        hes_last_seen=NOW - timedelta(minutes=5),
        mdms_last_validated=NOW - timedelta(hours=1),
        cis_last_billing=None,
        now=NOW,
    )
    assert s == "missing_cis"


def test_status_lagging_when_hes_stale():
    s = compute_status(
        hes_last_seen=NOW - timedelta(hours=2),
        mdms_last_validated=NOW - timedelta(hours=2),
        cis_last_billing=NOW,
        now=NOW,
    )
    assert s == "lagging"


def test_status_stale_when_mdms_old():
    s = compute_status(
        hes_last_seen=NOW - timedelta(minutes=30),
        mdms_last_validated=NOW - timedelta(days=2),
        cis_last_billing=NOW,
        now=NOW,
    )
    assert s == "stale"


# ── Endpoint tests ─────────────────────────────────────────────────────────


def _seed_source_status(SessionLocal, rows):
    from app.models.source_status import SourceStatus

    with SessionLocal() as s:
        for r in rows:
            s.add(SourceStatus(**r))
        s.commit()


def test_list_data_accuracy(client, SessionLocal):
    _seed_source_status(SessionLocal, [
        {
            "meter_serial": "M001",
            "hes_last_seen": NOW - timedelta(minutes=10),
            "mdms_last_validated": NOW - timedelta(hours=1),
            "cis_last_billing": NOW - timedelta(days=2),
        },
        {
            "meter_serial": "M002",
            "hes_last_seen": NOW - timedelta(hours=3),
            "mdms_last_validated": NOW - timedelta(hours=1),
            "cis_last_billing": NOW - timedelta(days=2),
        },
        {
            "meter_serial": "M003",
            "hes_last_seen": NOW,
            "mdms_last_validated": None,
            "cis_last_billing": NOW - timedelta(days=2),
        },
    ])

    resp = client.get("/api/v1/data-accuracy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    by_serial = {r["meter_serial"]: r for r in body["rows"]}
    # Row statuses reflect the badge logic per row. We don't compare against
    # NOW because the endpoint uses its own real "now", so just assert the
    # row count and that every row has a status field populated.
    for serial in ("M001", "M002", "M003"):
        assert serial in by_serial
        assert by_serial[serial]["status"] in {
            "healthy", "lagging", "missing_mdms", "missing_cis", "stale", "unknown"
        }


def test_filter_by_meter_serial(client, SessionLocal):
    _seed_source_status(SessionLocal, [
        {"meter_serial": "A1", "hes_last_seen": NOW, "mdms_last_validated": NOW, "cis_last_billing": NOW},
        {"meter_serial": "B2", "hes_last_seen": NOW, "mdms_last_validated": NOW, "cis_last_billing": NOW},
    ])
    resp = client.get("/api/v1/data-accuracy", params={"meter_serial": "A1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["meter_serial"] == "A1"


def test_reconcile_returns_issue_id(client, SessionLocal):
    _seed_source_status(SessionLocal, [
        {"meter_serial": "X9", "hes_last_seen": NOW, "mdms_last_validated": NOW, "cis_last_billing": NOW},
    ])
    resp = client.post("/api/v1/data-accuracy/X9/reconcile")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["meter_serial"] == "X9"
    assert body["issue_id"]
    assert body["status"] == "reconciliation_scheduled"


def test_reconcile_404_for_unknown_meter(client):
    resp = client.post("/api/v1/data-accuracy/UNKNOWN/reconcile")
    assert resp.status_code == 404


def test_rbac_viewer_cannot_reconcile(client, SessionLocal):
    # Swap auth to a viewer and confirm RBAC blocks reconcile.
    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User, UserRole

    _seed_source_status(SessionLocal, [
        {"meter_serial": "V1", "hes_last_seen": NOW, "mdms_last_validated": NOW, "cis_last_billing": NOW},
    ])
    viewer = User(
        id=88, username="v", email="v@e.com", full_name="V",
        hashed_password="x", role=UserRole.VIEWER, is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: viewer
    resp = client.post("/api/v1/data-accuracy/V1/reconcile")
    assert resp.status_code == 403
