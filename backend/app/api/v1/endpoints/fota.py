"""FOTA API endpoints (spec 018 W2.T10).

Endpoints:
  POST   /api/v1/fota/firmware/presign            — presigned PUT URL (S3 or local)
  POST   /api/v1/fota/jobs                        — create job (uploads already-done)
  GET    /api/v1/fota/jobs                        — list
  GET    /api/v1/fota/jobs/{job_id}               — detail with per-meter rows
  POST   /api/v1/fota/jobs/{job_id}/poll          — force a poll tick (tests/ops)
  POST   /api/v1/fota/jobs/{job_id}/rollback/{serial} — single-meter rollback
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_FOTA_MANAGE
from app.db.base import get_db
from app.models.fota import FotaJob, FotaJobMeterStatus
from app.models.user import User
from app.schemas.fota import (
    FotaJobCreate,
    FotaJobDetail,
    FotaJobOut,
    FotaMeterStatusOut,
    FotaRollbackResponse,
    PresignedUploadOut,
)
from app.services.fota_service import fota_service

try:
    from otel_common.audit import audit  # type: ignore
except ImportError:  # pragma: no cover
    async def audit(**_kwargs):
        return None


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/firmware/presign",
    response_model=PresignedUploadOut,
    dependencies=[Depends(require_permission(P_FOTA_MANAGE))],
)
def presign_firmware_upload(
    firmware_name: str,
    _: User = Depends(get_current_user),
):
    return PresignedUploadOut(**fota_service.presign_upload(firmware_name))


@router.post(
    "/jobs",
    response_model=FotaJobOut,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(P_FOTA_MANAGE))],
)
async def create_fota_job(
    payload: FotaJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled",
        )
    job = await fota_service.create_job(
        db=db,
        firmware_name=payload.firmware_name,
        firmware_version=payload.firmware_version,
        image_uri=payload.image_uri,
        target_meter_serials=payload.target_meter_serials,
        issuer_user_id=str(current_user.id),
        trace_id=current_trace_id(),
    )
    await audit(
        action_type="WRITE",
        action_name="fota_job_create",
        entity_type="FotaJob",
        entity_id=job.id,
        request_data={
            "firmware_name": payload.firmware_name,
            "meter_count": len(payload.target_meter_serials),
        },
        status=201,
        method="POST",
        path="/api/v1/fota/jobs",
        user_id=str(current_user.id),
    )
    return FotaJobOut.model_validate(job, from_attributes=True)


@router.get("/jobs", response_model=List[FotaJobOut])
def list_fota_jobs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(FotaJob)
        .order_by(FotaJob.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
        .all()
    )
    return [FotaJobOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/jobs/{job_id}", response_model=FotaJobDetail)
def get_fota_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    job = db.query(FotaJob).filter(FotaJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="FOTA job not found")
    meters = (
        db.query(FotaJobMeterStatus).filter(FotaJobMeterStatus.job_id == job_id).all()
    )
    out = FotaJobDetail.model_validate(job, from_attributes=True)
    out.meters = [FotaMeterStatusOut.model_validate(m, from_attributes=True) for m in meters]
    return out


@router.post(
    "/jobs/{job_id}/poll",
    response_model=FotaJobOut,
    dependencies=[Depends(require_permission(P_FOTA_MANAGE))],
)
async def poll_fota_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    job = await fota_service.poll_job(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="FOTA job not found")
    return FotaJobOut.model_validate(job, from_attributes=True)


@router.post(
    "/jobs/{job_id}/rollback/{meter_serial}",
    response_model=FotaRollbackResponse,
    dependencies=[Depends(require_permission(P_FOTA_MANAGE))],
)
async def rollback_meter(
    job_id: str,
    meter_serial: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled",
        )
    command_id, err = await fota_service.rollback(
        db=db,
        job_id=job_id,
        meter_serial=meter_serial,
        issuer_user_id=str(current_user.id),
    )
    await audit(
        action_type="WRITE",
        action_name="fota_rollback",
        entity_type="FotaJob",
        entity_id=job_id,
        request_data={"meter_serial": meter_serial, "command_id": command_id},
        status=200 if err is None else 503,
        method="POST",
        path=f"/api/v1/fota/jobs/{job_id}/rollback/{meter_serial}",
        user_id=str(current_user.id),
    )
    if err and "not part of job" in err:
        raise HTTPException(status_code=404, detail=err)
    return FotaRollbackResponse(
        success=err is None,
        job_id=job_id,
        meter_serial=meter_serial,
        command_id=command_id if command_id else None,
        detail=err,
    )
