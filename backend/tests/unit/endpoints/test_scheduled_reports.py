"""W4.T10 — scheduled_report CRUD + run-now tests."""
from __future__ import annotations

import pytest


def test_scheduled_report_create_list(client):
    r = client.post(
        "/api/v1/reports/scheduled",
        json={
            "name": "Daily energy audit",
            "report_ref": "egsm:energy-audit:feeder-loss-summary",
            "params": {"from": "today-1d"},
            "schedule_cron": "0 6 * * *",
            "recipients": ["ops@example.com"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Daily energy audit"
    assert body["enabled"] is True
    assert body["recipients"] == ["ops@example.com"]

    r = client.get("/api/v1/reports/scheduled")
    assert r.status_code == 200
    names = [x["name"] for x in r.json()]
    assert "Daily energy audit" in names


def test_scheduled_report_update_delete(client):
    r = client.post(
        "/api/v1/reports/scheduled",
        json={
            "name": "Weekly",
            "report_ref": "egsm:reliability-indices:weekly",
            "schedule_cron": "0 0 * * 1",
            "recipients": [],
        },
    )
    rid = r.json()["id"]

    r = client.put(
        f"/api/v1/reports/scheduled/{rid}",
        json={"name": "Weekly v2", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Weekly v2"
    assert r.json()["enabled"] is False

    r = client.delete(f"/api/v1/reports/scheduled/{rid}")
    assert r.status_code == 204


def test_scheduled_report_run_now_calls_worker(client, monkeypatch):
    """run-now returns the worker's result envelope."""
    from app.services import scheduled_report_worker
    from app.schemas.app_builder import ScheduledReportRunResult
    from datetime import datetime, timezone

    called = {}

    async def _fake_run_once(rid: str):
        called["id"] = rid
        now = datetime.now(timezone.utc)
        return ScheduledReportRunResult(
            scheduled_report_id=rid,
            status="ok",
            started_at=now,
            finished_at=now,
            recipients_sent=0,
        )

    monkeypatch.setattr(scheduled_report_worker, "run_once", _fake_run_once)

    r = client.post(
        "/api/v1/reports/scheduled",
        json={
            "name": "Ad-hoc",
            "report_ref": "egsm:loss-analytics:feeder",
            "schedule_cron": "0 0 * * *",
            "recipients": ["a@b"],
        },
    )
    rid = r.json()["id"]

    r = client.post(f"/api/v1/reports/scheduled/{rid}/run-now")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    assert called["id"] == rid
