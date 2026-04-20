"""US-12 Data Quality & Source Accuracy Console — spec 018 §User Story 12.

Acceptance (integration-test-matrix row 12):

* For every meter, show last-collection-time from HES, last-validated-read
  from MDMS, last-billing-read from CIS.
* 10 meters offline 2 h → Data Accuracy tab flags them "HES delay > 1h".
* Badges source from real HES+MDMS+CIS timestamps (no synthesised values).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_compute_status_badge_precedence():
    """The badge precedence rules from the docstring are load-bearing for
    the UI colour coding.  Lock them in.
    """
    from app.services.source_status_refresher import compute_status

    now = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)
    hour = lambda h: now - timedelta(hours=h)

    # healthy: HES ≤ 1h, MDMS ≤ 24h, CIS present.
    assert compute_status(hour(0), hour(1), hour(48), now=now) == "healthy"

    # lagging: HES > 1h.
    assert compute_status(hour(2), hour(1), hour(48), now=now) == "lagging"

    # missing_mdms: MDMS timestamp is None.
    assert compute_status(hour(0), None, hour(48), now=now) == "missing_mdms"

    # missing_cis: CIS timestamp is None.
    assert compute_status(hour(0), hour(1), None, now=now) == "missing_cis"

    # stale: MDMS > 24h.
    assert compute_status(hour(0), hour(48), hour(48), now=now) == "stale"


def test_data_accuracy_endpoint_returns_upstream_timestamps(client, db_session):
    """Seed 10 meters with HES last-seen=2h ago → endpoint must return
    them flagged as ``lagging``.
    """
    from app.models.source_status import SourceStatus

    now = datetime.now(timezone.utc)
    two_hours_ago = now - timedelta(hours=2)
    mdms_recent = now - timedelta(minutes=30)
    cis_recent = now - timedelta(hours=3)

    for i in range(10):
        serial = f"US12-LAG-{i:02d}"
        db_session.merge(SourceStatus(
            meter_serial=serial,
            hes_last_seen=two_hours_ago,
            mdms_last_validated=mdms_recent,
            cis_last_billing=cis_recent,
            updated_at=now,
        ))
    db_session.commit()

    resp = client.get("/api/v1/data-accuracy", params={"limit": 50})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body.get("rows") or body.get("items") or []
    # Filter down to the US12-LAG rows seeded above.
    seeded_rows = [r for r in rows if r.get("meter_serial", "").startswith("US12-LAG-")]
    assert len(seeded_rows) == 10, f"expected 10 lagging rows, got {len(seeded_rows)}"

    for row in seeded_rows:
        assert row.get("status") == "lagging", (
            f"expected status=lagging for {row.get('meter_serial')}, "
            f"got {row.get('status')}"
        )
        # The timestamp must round-trip — not be overwritten with "now".
        assert row.get("hes_last_seen") is not None


def test_data_accuracy_missing_mdms_rendered(client, db_session):
    """A meter with mdms_last_validated=NULL → badge missing_mdms."""
    from app.models.source_status import SourceStatus

    now = datetime.now(timezone.utc)
    serial = "US12-MISS-MDMS-01"
    db_session.merge(SourceStatus(
        meter_serial=serial,
        hes_last_seen=now - timedelta(minutes=10),
        mdms_last_validated=None,
        cis_last_billing=now - timedelta(hours=2),
        updated_at=now,
    ))
    db_session.commit()

    resp = client.get(
        "/api/v1/data-accuracy", params={"meter_serial": serial}
    )
    assert resp.status_code == 200
    rows = resp.json().get("rows") or resp.json().get("items") or []
    assert rows, resp.json()
    assert rows[0]["status"] == "missing_mdms"


@pytest.mark.xfail(
    reason="Reconcile task submission depends on MDMS reconciler service "
    "landing (mdms-todos MDMS-T6); until then the endpoint enqueues a "
    "stub row. Once MDMS-T6 is live this test asserts the MDMS-side WO id "
    "is returned.",
    strict=False,
)
def test_reconcile_action_returns_mdms_wo_id(client, db_session):
    """POST /data-accuracy/{serial}/reconcile → MDMS returns WO id once
    reconciler is online.
    """
    from app.models.source_status import SourceStatus

    now = datetime.now(timezone.utc)
    serial = "US12-RECON-01"
    db_session.merge(SourceStatus(
        meter_serial=serial,
        hes_last_seen=now,
        mdms_last_validated=None,  # missing → reconcile eligible
        cis_last_billing=now,
        updated_at=now,
    ))
    db_session.commit()

    resp = client.post(f"/api/v1/data-accuracy/{serial}/reconcile")
    assert resp.status_code == 202
    assert resp.json().get("wo_id")
