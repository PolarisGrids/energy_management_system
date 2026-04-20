"""W2.T10 — FOTA create / detail / rollback."""
from __future__ import annotations

import pytest

from app.models.fota import FotaJob, FotaJobMeterStatus


def test_firmware_presign_returns_uri(client):
    resp = client.post("/api/v1/fota/firmware/presign?firmware_name=meter-v2.5.0.bin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_url"]
    assert body["image_uri"]
    # In the unit-test env boto3 is unconfigured, so we expect a file:// URI.
    assert body["image_uri"].startswith(("file://", "s3://"))


def test_create_job_persists_and_calls_hes(client, fake_hes, db):
    resp = client.post(
        "/api/v1/fota/jobs",
        json={
            "firmware_name": "meter-v2.5.0.bin",
            "firmware_version": "2.5.0",
            "image_uri": "file:///tmp/fw.bin",
            "target_meter_serials": ["M-A", "M-B", "M-C"],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_meters"] == 3
    assert body["status"] in ("SUBMITTED", "QUEUED")
    # HES was called with a create_fota_job.
    assert any(c[0] == "create_fota_job" for c in fake_hes.calls)

    job_id = body["id"]
    assert db.query(FotaJob).filter(FotaJob.id == job_id).count() == 1
    assert (
        db.query(FotaJobMeterStatus)
        .filter(FotaJobMeterStatus.job_id == job_id)
        .count()
        == 3
    )


def test_get_job_detail_lists_per_meter_status(client, fake_hes, db):
    # First create.
    resp = client.post(
        "/api/v1/fota/jobs",
        json={
            "firmware_name": "fw.bin",
            "image_uri": "file:///tmp/fw.bin",
            "target_meter_serials": ["M-1", "M-2"],
        },
    )
    job_id = resp.json()["id"]

    detail = client.get(f"/api/v1/fota/jobs/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    serials = sorted([m["meter_serial"] for m in body["meters"]])
    assert serials == ["M-1", "M-2"]


def test_rollback_requires_meter_in_job(client, fake_hes):
    resp = client.post(
        "/api/v1/fota/jobs/00000000-0000-0000-0000-000000000000/rollback/MISSING"
    )
    assert resp.status_code == 404
