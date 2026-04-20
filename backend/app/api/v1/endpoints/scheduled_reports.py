"""Scheduled report CRUD + run-now — spec 018 W4.T10.

Endpoints (under /api/v1/reports/scheduled):

    GET    /                       — list the caller's scheduled reports
    POST   /                       — create a schedule
    GET    /{id}
    PUT    /{id}
    DELETE /{id}
    POST   /{id}/run-now           — immediate run (no cron tick)

The background APScheduler worker lives in
``app.services.scheduled_report_worker`` and is booted in ``main.py``
lifespan when ``SCHEDULED_REPORTS_ENABLED`` is on.
"""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.app_builder import ScheduledReport
from app.models.user import User
from app.schemas.app_builder import (
    ScheduledReportCreate,
    ScheduledReportOut,
    ScheduledReportRunResult,
    ScheduledReportUpdate,
)
from app.services import scheduled_report_worker

router = APIRouter()


def _uuid() -> str:
    return str(uuid.uuid4())


def _to_schema(row: ScheduledReport) -> dict:
    """Convert ORM row to output shape. Translates the int-encoded `enabled`."""
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "name": row.name,
        "report_ref": row.report_ref,
        "params": row.params or {},
        "schedule_cron": row.schedule_cron,
        "recipients": row.recipients or [],
        "enabled": bool(row.enabled),
        "last_run_at": row.last_run_at,
        "last_status": row.last_status,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _owned_or_404(db: Session, report_id: str, user: User) -> ScheduledReport:
    row = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="scheduled_report not found")
    # Admins can touch any; others only their own.
    is_admin = str(getattr(user, "role", "")).lower().endswith("admin")
    if row.owner_user_id != str(user.id) and not is_admin:
        raise HTTPException(status_code=403, detail="not owner")
    return row


@router.get("", response_model=List[ScheduledReportOut])
def list_scheduled(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ScheduledReport)
        .filter(ScheduledReport.owner_user_id == str(current_user.id))
        .order_by(ScheduledReport.created_at.desc())
        .all()
    )
    return [_to_schema(r) for r in rows]


@router.post("", response_model=ScheduledReportOut, status_code=201)
def create_scheduled(
    payload: ScheduledReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = ScheduledReport(
        id=_uuid(),
        owner_user_id=str(current_user.id),
        name=payload.name,
        report_ref=payload.report_ref,
        params=payload.params,
        schedule_cron=payload.schedule_cron,
        recipients=payload.recipients,
        enabled=1 if payload.enabled else 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    scheduled_report_worker.notify_change()
    return _to_schema(row)


@router.get("/{report_id}", response_model=ScheduledReportOut)
def get_scheduled(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _to_schema(_owned_or_404(db, report_id, current_user))


@router.put("/{report_id}", response_model=ScheduledReportOut)
def update_scheduled(
    report_id: str,
    payload: ScheduledReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_or_404(db, report_id, current_user)
    if payload.name is not None:
        row.name = payload.name
    if payload.report_ref is not None:
        row.report_ref = payload.report_ref
    if payload.params is not None:
        row.params = payload.params
    if payload.schedule_cron is not None:
        row.schedule_cron = payload.schedule_cron
    if payload.recipients is not None:
        row.recipients = payload.recipients
    if payload.enabled is not None:
        row.enabled = 1 if payload.enabled else 0
    db.commit()
    db.refresh(row)
    scheduled_report_worker.notify_change()
    return _to_schema(row)


@router.delete("/{report_id}", status_code=204)
def delete_scheduled(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_or_404(db, report_id, current_user)
    db.delete(row)
    db.commit()
    scheduled_report_worker.notify_change()


@router.post("/{report_id}/run-now", response_model=ScheduledReportRunResult)
async def run_scheduled_now(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_or_404(db, report_id, current_user)
    return await scheduled_report_worker.run_once(row.id)
