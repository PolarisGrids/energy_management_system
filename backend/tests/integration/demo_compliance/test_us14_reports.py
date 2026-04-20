"""US-14 Consumption queries & reports — spec 018 §User Story 14.

Acceptance (integration-test-matrix row 14):

* Operator opens ``/reports`` and runs Energy Audit Monthly; rows match
  MDMS ``/egsm-reports/energy-audit/monthly-consumption``.
* Large result set: export CSV → MDMS CSV+S3+SQS pipeline generates,
  EMS polls download-log, download appears in notifications.

Covers the EMS proxy path in ``reports_egsm.py``
(``/api/v1/reports/egsm/:category/:report``) + the download-poll
endpoint (``GET /api/v1/reports/download``).
"""
from __future__ import annotations

import pytest


def test_egsm_energy_audit_monthly_proxied(client, mdms_mock):
    """Run Energy Audit Monthly → proxy forwards + returns MDMS payload."""
    from app.core.config import settings
    settings.MDMS_ENABLED = True  # type: ignore[attr-defined]

    expected = {
        "report": "monthly-consumption",
        "month": "2026-04",
        "rows": [
            {"date": "2026-04-01", "import_kwh": 1234.0, "export_kwh": 5.0},
            {"date": "2026-04-02", "import_kwh": 1180.5, "export_kwh": 6.0},
        ],
        "total_import_kwh": 2414.5,
    }
    mdms_mock.get("/api/v1/reports/egsm/energy-audit/monthly-consumption").respond(
        200, json=expected
    )

    resp = client.get(
        "/api/v1/reports/egsm/energy-audit/monthly-consumption",
        params={"month": "2026-04", "dtr_id": "DTR-001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Proxy must forward payload unchanged.
    assert body == expected


def test_egsm_report_download_poll_proxied(client, mdms_mock):
    """Download polling endpoint must round-trip MDMS's pending/ready state."""
    from app.core.config import settings
    settings.MDMS_ENABLED = True  # type: ignore[attr-defined]

    mdms_mock.get("/api/v1/reports/download").respond(
        200,
        json={
            "id": "DL-ABCDEF",
            "status": "ready",
            "url": "https://s3.ap-south-1.amazonaws.com/mdms-exports/DL-ABCDEF.csv",
            "row_count": 120_000,
        },
    )

    resp = client.get("/api/v1/reports/download", params={"id": "DL-ABCDEF"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["url"].endswith(".csv")
    assert body["row_count"] == 120_000


def test_egsm_report_proxy_forwards_upstream_5xx(client, mdms_mock):
    """When MDMS is red, the EMS proxy must surface a 5xx (NOT a seeded
    fallback) — this is the SSOT_MODE=strict guarantee.
    """
    from app.core.config import settings
    settings.MDMS_ENABLED = True  # type: ignore[attr-defined]

    mdms_mock.get(
        "/api/v1/reports/egsm/energy-audit/monthly-consumption"
    ).respond(503, json={"detail": "mdms maintenance"})
    resp = client.get(
        "/api/v1/reports/egsm/energy-audit/monthly-consumption",
        params={"month": "2026-04"},
    )
    assert resp.status_code >= 500


@pytest.mark.xfail(
    reason="Scheduled-report worker exercises the APScheduler tick + PDF "
    "renderer. E2E assertion (schedule fires → PDF email dispatched) needs "
    "the SMTP/SES sink stubbed via fakesmtp; not yet wired into this "
    "harness. Backend unit tests cover the PDF renderer and scheduler "
    "independently.",
    strict=False,
)
def test_scheduled_report_runs_and_emails_pdf(client):
    """End-to-end scheduled run → PDF attachment delivered."""
    resp = client.post("/api/v1/reports/scheduled/run-now", json={"id": "sched-test-1"})
    assert resp.status_code == 200
    assert resp.json().get("delivered") is True
