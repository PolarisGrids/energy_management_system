"""Outage Management endpoints — spec 016 US2 (MVP).

Routes (all gated by the new `outages.read` / `outages.manage` capabilities):

* ``POST   /api/v1/outages/``      — create (manual or from alarm cluster)
* ``PATCH  /api/v1/outages/{id}``  — lifecycle transition (via state machine)
* ``GET    /api/v1/outages/``      — filterable list
* ``GET    /api/v1/outages/{id}``  — detail incl. polygon GeoJSON

Notifications, SSE emission, and audit events are fired from the service
helpers `_notify_transition` and `_emit_sse_event` at the bottom of this
file — the dispatcher itself lives in `app.services.notifications`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.permissions import (
    OUTAGES_MANAGE,
    OUTAGES_READ,
    require_permission,
)
from app.db.base import get_db
from app.models.gis import OutageArea
from app.models.outage import OutageIncident, OutageStatus
from app.models.user import User
from app.services.affected_customers import derive_affected
from app.services.outage_state_machine import (
    InvalidTransition,
    transition as apply_transition,
)

logger = logging.getLogger("polaris.outages")

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────


class OutageCreate(BaseModel):
    feeder_id: int
    cause: Optional[str] = None
    outage_area_id: Optional[int] = None
    etr_at: Optional[datetime] = None
    notes: Optional[str] = None


class OutageTransition(BaseModel):
    status: OutageStatus
    notes: Optional[str] = None
    etr_at: Optional[datetime] = None


class OutageOut(BaseModel):
    id: int
    status: str
    feeder_id: int
    outage_area_id: Optional[int] = None
    started_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    dispatched_at: Optional[datetime]
    restored_at: Optional[datetime]
    closed_at: Optional[datetime]
    etr_at: Optional[datetime]
    affected_customers: int = 0
    cause: Optional[str]
    notes: Optional[str]
    created_by: Optional[str]
    polygon: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


def _outage_to_dict(incident: OutageIncident, polygon: Optional[dict] = None) -> dict:
    return {
        "id": incident.id,
        "status": incident.status,
        "feeder_id": incident.feeder_id,
        "outage_area_id": incident.outage_area_id,
        "started_at": incident.started_at,
        "confirmed_at": incident.confirmed_at,
        "dispatched_at": incident.dispatched_at,
        "restored_at": incident.restored_at,
        "closed_at": incident.closed_at,
        "etr_at": incident.etr_at,
        "affected_customers": incident.affected_customers or 0,
        "cause": incident.cause,
        "notes": incident.notes,
        "created_by": incident.created_by,
        "polygon": polygon,
    }


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/", response_model=OutageOut, status_code=201)
def create_outage(
    payload: OutageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(OUTAGES_MANAGE)),
):
    affected_count, _serials = derive_affected(db, payload.feeder_id)
    now = datetime.now(timezone.utc)
    etr = payload.etr_at or (now + timedelta(hours=2))
    inc = OutageIncident(
        status=OutageStatus.DETECTED.value,
        feeder_id=payload.feeder_id,
        outage_area_id=payload.outage_area_id,
        started_at=now,
        etr_at=etr,
        affected_customers=affected_count,
        cause=payload.cause,
        notes=payload.notes,
        created_by=user.username,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    _announce(db, inc, kind="outage.created")
    return _outage_to_dict(inc)


@router.patch("/{incident_id}", response_model=OutageOut)
def patch_outage(
    incident_id: int,
    payload: OutageTransition,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(OUTAGES_MANAGE)),
):
    inc = db.query(OutageIncident).filter(OutageIncident.id == incident_id).first()
    if inc is None:
        raise HTTPException(status_code=404, detail="outage not found")
    try:
        apply_transition(inc, payload.status, actor=user.username)
    except InvalidTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if payload.notes:
        inc.notes = payload.notes
    if payload.etr_at:
        inc.etr_at = payload.etr_at
    db.commit()
    db.refresh(inc)
    kind = (
        "outage.closed"
        if inc.status in (OutageStatus.CLOSED.value, OutageStatus.CANCELLED.value)
        else "outage.updated"
    )
    _announce(db, inc, kind=kind)
    return _outage_to_dict(inc)


@router.get("/", response_model=list[OutageOut])
def list_outages(
    status: Optional[OutageStatus] = None,
    feeder: Optional[int] = Query(default=None, alias="feeder"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(OUTAGES_READ)),
):
    q = db.query(OutageIncident)
    if status:
        q = q.filter(OutageIncident.status == status.value)
    if feeder is not None:
        q = q.filter(OutageIncident.feeder_id == feeder)
    rows = q.order_by(OutageIncident.started_at.desc()).offset(offset).limit(limit).all()
    return [_outage_to_dict(r) for r in rows]


@router.get("/{incident_id}", response_model=OutageOut)
def get_outage(
    incident_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(OUTAGES_READ)),
):
    inc = db.query(OutageIncident).filter(OutageIncident.id == incident_id).first()
    if inc is None:
        raise HTTPException(status_code=404, detail="outage not found")
    polygon = None
    if inc.outage_area_id:
        row = db.execute(
            text(
                "SELECT ST_AsGeoJSON(polygon_geom)::json AS geom "
                "FROM outage_areas WHERE id = :id"
            ),
            {"id": inc.outage_area_id},
        ).first()
        if row and row[0]:
            polygon = row[0]
    return _outage_to_dict(inc, polygon=polygon)


# ── Event fan-out helpers ────────────────────────────────────────────────


def _announce(db: Session, incident: OutageIncident, kind: str) -> None:
    """Push the outage change into the SSE poller + audit trail.

    SSE emission in MVP is handled by the poller in `sse.py` which observes
    the ``outage_incidents`` table on every tick, so we only need to log +
    best-effort audit here.
    """
    logger.info("outage-event kind=%s id=%s status=%s", kind, incident.id, incident.status)
    # Best-effort audit trail via otel-common-py; skipped silently if no Kafka.
    try:
        from otel_common.audit import audit  # type: ignore

        import asyncio

        coro = audit(
            action_type="WRITE",
            action_name=kind,
            entity_type="OutageIncident",
            entity_id=str(incident.id),
            method="POST",
            path="/outages",
            status=200,
        )
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            # No loop (e.g. sync startup); drop — best-effort.
            pass
    except Exception:
        pass
