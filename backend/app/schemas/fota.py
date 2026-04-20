"""FOTA schemas (spec 018 W2B.T10)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class FotaJobCreate(BaseModel):
    firmware_name: str
    firmware_version: Optional[str] = None
    image_uri: str  # s3:// or file:// — see FOTAService.upload_firmware
    target_meter_serials: list[str] = Field(min_length=1, max_length=5000)


class FotaMeterStatusOut(BaseModel):
    meter_serial: str
    status: str
    progress_pct: int = 0
    last_error: Optional[str] = None
    applied_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FotaJobOut(BaseModel):
    id: str
    hes_job_id: Optional[str] = None
    firmware_name: str
    firmware_version: Optional[str] = None
    image_uri: str
    total_meters: int
    succeeded: int
    failed: int
    in_progress: int
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FotaJobDetail(FotaJobOut):
    meters: list[FotaMeterStatusOut] = []


class FotaRollbackResponse(BaseModel):
    success: bool
    job_id: str
    meter_serial: str
    command_id: Optional[str] = None
    detail: Optional[str] = None


class PresignedUploadOut(BaseModel):
    upload_url: str
    image_uri: str
    expires_in: int
