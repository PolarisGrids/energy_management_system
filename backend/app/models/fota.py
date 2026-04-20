"""Spec 018 FOTA job tables (EMS-owned).

Distinct from legacy `hes_fota_jobs` (display mirror). These store EMS's
orchestration state: firmware image blob URL, HES job id, per-meter status,
progress checkpoints polled from HES routing `GET /api/v1/firmware-upgrade/:id`.
"""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


def _json_col():
    return JSON().with_variant(JSONB(), "postgresql")


def _uuid_col():
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")


class FotaJob(Base):
    __tablename__ = "fota_job"

    id = Column(_uuid_col(), primary_key=True)
    hes_job_id = Column(String(100), nullable=True, index=True)
    firmware_name = Column(Text, nullable=False)
    firmware_version = Column(String(50), nullable=True)
    image_uri = Column(Text, nullable=False)  # s3:// or file:// in dev
    total_meters = Column(Integer, default=0)
    succeeded = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    in_progress = Column(Integer, default=0)
    status = Column(String(20), default="QUEUED")
    # QUEUED -> UPLOADED -> SUBMITTED -> RUNNING -> COMPLETED / FAILED / PARTIAL
    issuer_user_id = Column(String(200), nullable=True)
    trace_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    poll_cursor = Column(_json_col(), nullable=True)  # last response shape for resume


class FotaJobMeterStatus(Base):
    __tablename__ = "fota_job_meter_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        _uuid_col(), ForeignKey("fota_job.id", ondelete="CASCADE"), index=True, nullable=False
    )
    meter_serial = Column(String(100), nullable=False, index=True)
    status = Column(String(20), default="PENDING")
    # PENDING -> DOWNLOADING -> APPLIED -> FAILED / ROLLED_BACK
    progress_pct = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
