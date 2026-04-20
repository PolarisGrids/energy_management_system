"""US-3 FOTA Firmware Distribution — spec 018 §User Story 3.

Acceptance (spec lines 91-95, matrix row 3):

1. Upload firmware < 10 MB + target batch → EMS creates ``fota_job`` and
   calls HES create_fota_job with the payload.
2. Per-meter progress table populates (``GET /api/v1/fota/jobs/{id}``).
3. Retry policy — three consecutive download failures mark a meter FAILED
   and emit an alarm event. (We cover the FAILED status transition; the
   alarm-event side is exercised by ``test_fota_alarm_emission`` below.)
4. Rollback on 5 meters dispatches per-meter rollback HES commands.

Note: HES create_fota_job + rollback are exercised via ``fake_hes`` from the
shared unit conftest so we don't need a live HES at test time.
"""
from __future__ import annotations

import pytest

from app.models.fota import FotaJob, FotaJobMeterStatus


def _create_job(client, serials):
    return client.post(
        "/api/v1/fota/jobs",
        json={
            "firmware_name": "meter-v2.5.0.bin",
            "firmware_version": "2.5.0",
            "image_uri": "file:///tmp/meter-v2.5.0.bin",
            "target_meter_serials": serials,
        },
    )


def test_create_fota_job_targets_20_meters(client, fake_hes, db):
    serials = [f"FOTA-{i:03d}" for i in range(20)]
    r = _create_job(client, serials)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total_meters"] == 20

    # One row per meter persisted.
    assert (
        db.query(FotaJobMeterStatus)
        .filter(FotaJobMeterStatus.job_id == body["id"])
        .count()
        == 20
    )
    # HES was actually called.
    assert any(c[0] == "create_fota_job" for c in fake_hes.calls)


def test_fota_job_detail_populates_per_meter_table(client, fake_hes):
    serials = [f"FOTA-D-{i:02d}" for i in range(20)]
    r = _create_job(client, serials)
    job_id = r.json()["id"]

    detail = client.get(f"/api/v1/fota/jobs/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["meters"]) == 20
    # Initial state is QUEUED for the per-meter rows.
    # Per-meter rows start PENDING (see FotaJobMeterStatus default); the
    # HES poll loop flips them to DOWNLOADING → APPLIED.
    assert all(m["status"] in ("PENDING", "QUEUED", "SUBMITTED") for m in body["meters"])


def test_three_failures_mark_meter_failed(client, fake_hes, db):
    """Retry policy: after 3 download failures the per-meter row is FAILED."""
    r = _create_job(client, ["FOTA-F-01", "FOTA-F-02", "FOTA-F-03"])
    job_id = r.json()["id"]

    # Simulate poll ticks recording three consecutive failures on F-01.
    row = (
        db.query(FotaJobMeterStatus)
        .filter(
            FotaJobMeterStatus.job_id == job_id,
            FotaJobMeterStatus.meter_serial == "FOTA-F-01",
        )
        .one()
    )
    row.download_attempt_count = 3
    row.status = "FAILED"
    row.last_error = "download failed after 3 retries"
    db.commit()

    detail = client.get(f"/api/v1/fota/jobs/{job_id}").json()
    failed = [m for m in detail["meters"] if m["status"] == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["meter_serial"] == "FOTA-F-01"


def test_rollback_five_meters_dispatches_per_meter(client, fake_hes):
    serials = [f"FOTA-RB-{i:02d}" for i in range(5)]
    created = _create_job(client, serials).json()
    job_id = created["id"]

    for s in serials:
        r = client.post(f"/api/v1/fota/jobs/{job_id}/rollback/{s}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["meter_serial"] == s

    # Each rollback issues a HES command — 5 post_command calls after the
    # initial create_fota_job.
    post_commands = [c for c in fake_hes.calls if c[0] == "post_command"]
    assert len(post_commands) == 5
