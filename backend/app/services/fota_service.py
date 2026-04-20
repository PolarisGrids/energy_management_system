"""FOTA job orchestration (spec 018 W2.T10).

Pipeline:
  1. Client (or another service) uploads firmware image to S3 via a
     pre-signed PUT URL returned by `presign_upload()`. If `FOTA_S3_BUCKET`
     is unset we fall back to a local-disk URI (`file://`) so dev/unit tests
     can exercise the rest of the flow without boto3.
  2. `create_job(...)` persists a `fota_job` row + one `fota_job_meter_status`
     row per target meter, then calls HES `POST /api/v1/firmware-upgrade` with
     `{firmware_uri, targets: [...]}` and stores the returned `hes_job_id`.
  3. A background task (`poll_job`) pulls HES every
     `settings.FOTA_POLL_INTERVAL_SECONDS` and updates per-meter progress.
  4. `rollback(job_id, meter_serial)` issues an HES `FIRMWARE_ROLLBACK`
     command for one meter (published as a normal command_log entry).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.fota import FotaJob, FotaJobMeterStatus
from app.services.hes_client import CircuitBreakerError, hes_client

logger = logging.getLogger(__name__)


class FOTAService:
    def __init__(self):
        self._poll_tasks: dict[str, asyncio.Task] = {}

    # ── Firmware upload ──
    def presign_upload(self, firmware_name: str) -> dict:
        """Return (upload_url, image_uri) so the client can PUT the binary.

        Production → S3 presigned PUT; dev → a local file path we guarantee
        exists. Never raises if boto3 is missing — degrades to local.
        """
        key = f"{uuid.uuid4()}-{firmware_name}"
        if settings.FOTA_S3_BUCKET:
            try:
                import boto3  # type: ignore

                s3 = boto3.client("s3", region_name=settings.FOTA_S3_REGION)
                url = s3.generate_presigned_url(
                    "put_object",
                    Params={"Bucket": settings.FOTA_S3_BUCKET, "Key": key},
                    ExpiresIn=settings.FOTA_PRESIGN_EXPIRY_SECONDS,
                )
                return {
                    "upload_url": url,
                    "image_uri": f"s3://{settings.FOTA_S3_BUCKET}/{key}",
                    "expires_in": settings.FOTA_PRESIGN_EXPIRY_SECONDS,
                }
            except Exception as exc:  # pragma: no cover — boto3 missing in unit env
                logger.warning("FOTA S3 presign failed; falling back to local: %s", exc)

        # Local fallback.
        local_dir = Path(settings.FOTA_LOCAL_DIR)
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / key
        return {
            "upload_url": f"file://{local_path}",
            "image_uri": f"file://{local_path}",
            "expires_in": settings.FOTA_PRESIGN_EXPIRY_SECONDS,
        }

    # ── Job lifecycle ──
    async def create_job(
        self,
        *,
        db: Session,
        firmware_name: str,
        firmware_version: Optional[str],
        image_uri: str,
        target_meter_serials: Iterable[str],
        issuer_user_id: Optional[str],
        trace_id: Optional[str],
    ) -> FotaJob:
        targets = list(target_meter_serials)
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        job = FotaJob(
            id=job_id,
            firmware_name=firmware_name,
            firmware_version=firmware_version,
            image_uri=image_uri,
            total_meters=len(targets),
            in_progress=len(targets),
            status="QUEUED",
            issuer_user_id=issuer_user_id,
            trace_id=trace_id,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        for serial in targets:
            db.add(
                FotaJobMeterStatus(
                    job_id=job_id, meter_serial=serial, status="PENDING", progress_pct=0
                )
            )
        db.commit()
        db.refresh(job)

        # Submit to HES.
        try:
            resp = await hes_client.create_fota_job(
                {
                    "job_id": job_id,
                    "firmware_name": firmware_name,
                    "firmware_version": firmware_version,
                    "image_uri": image_uri,
                    "target_meters": targets,
                }
            )
            body = resp.json() if hasattr(resp, "json") else {}
            job.hes_job_id = body.get("hes_job_id") or body.get("job_id") or job_id
            job.status = "SUBMITTED"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
        except CircuitBreakerError as exc:
            job.status = "FAILED"
            job.updated_at = datetime.now(timezone.utc)
            job.poll_cursor = {"error": "circuit_open", "detail": str(exc)}
            db.commit()
        except Exception as exc:  # pragma: no cover — defensive
            job.status = "FAILED"
            job.updated_at = datetime.now(timezone.utc)
            job.poll_cursor = {"error": "transport", "detail": str(exc)[:500]}
            db.commit()
        return job

    async def poll_job(self, *, db: Session, job_id: str) -> FotaJob | None:
        """Single poll tick — fetch HES job and update per-meter rows.

        Returns the refreshed FotaJob row or None if not found. Exposed as a
        method (rather than a looping task) so callers / tests can step it.
        """
        job = db.query(FotaJob).filter(FotaJob.id == job_id).first()
        if not job or not job.hes_job_id:
            return job
        if job.status in ("COMPLETED", "FAILED", "PARTIAL"):
            return job
        try:
            resp = await hes_client.get_fota_job(job.hes_job_id)
            body = resp.json() if hasattr(resp, "json") else {}
        except Exception as exc:
            job.poll_cursor = {"error": str(exc)[:500]}
            db.commit()
            return job

        job.poll_cursor = body
        overall_status = body.get("status", "RUNNING")
        per_meter = body.get("meters") or body.get("targets") or []
        for rec in per_meter:
            serial = rec.get("meter_serial") or rec.get("serial")
            if not serial:
                continue
            row = (
                db.query(FotaJobMeterStatus)
                .filter(
                    FotaJobMeterStatus.job_id == job.id,
                    FotaJobMeterStatus.meter_serial == serial,
                )
                .first()
            )
            if row is None:
                continue
            row.status = rec.get("status", row.status)
            row.progress_pct = int(rec.get("progress_pct", row.progress_pct or 0))
            if rec.get("error"):
                row.last_error = str(rec["error"])[:2000]
            if row.status == "APPLIED" and not row.applied_at:
                row.applied_at = datetime.now(timezone.utc)

        # Aggregate counts.
        succeeded = sum(
            1
            for r in db.query(FotaJobMeterStatus)
            .filter(FotaJobMeterStatus.job_id == job.id)
            .all()
            if r.status == "APPLIED"
        )
        failed = sum(
            1
            for r in db.query(FotaJobMeterStatus)
            .filter(FotaJobMeterStatus.job_id == job.id)
            .all()
            if r.status in ("FAILED", "ROLLED_BACK")
        )
        job.succeeded = succeeded
        job.failed = failed
        job.in_progress = max(job.total_meters - succeeded - failed, 0)
        job.status = overall_status
        if overall_status in ("COMPLETED", "FAILED"):
            job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        return job

    async def rollback(
        self, *, db: Session, job_id: str, meter_serial: str, issuer_user_id: Optional[str]
    ) -> tuple[str, Optional[str]]:
        """Issue FIRMWARE_ROLLBACK to HES; flip per-meter status to ROLLED_BACK.

        Returns (command_id, error_detail).
        """
        row = (
            db.query(FotaJobMeterStatus)
            .filter(
                FotaJobMeterStatus.job_id == job_id,
                FotaJobMeterStatus.meter_serial == meter_serial,
            )
            .first()
        )
        if row is None:
            return "", f"meter {meter_serial} not part of job {job_id}"

        command_id = str(uuid.uuid4())
        try:
            await hes_client.post_command(
                type_="FIRMWARE_ROLLBACK",
                meter_serial=meter_serial,
                payload={"job_id": job_id, "command_id": command_id},
            )
            row.status = "ROLLED_BACK"
            row.last_error = None
            db.commit()
            return command_id, None
        except CircuitBreakerError as exc:
            return command_id, f"HES circuit open: {exc}"
        except Exception as exc:  # pragma: no cover
            return command_id, f"HES transport failure: {exc}"


fota_service = FOTAService()
