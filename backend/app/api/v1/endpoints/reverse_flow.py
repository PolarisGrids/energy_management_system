"""Reverse-flow read endpoints — spec 018 W3.T13.

Exposes the `reverse_flow_event` table maintained by
`app.services.reverse_flow_detector`.

Endpoints:
    GET  /api/v1/reverse-flow/active           → all OPEN events (UI banner)
    GET  /api/v1/reverse-flow/feeder/{id}      → latest event(s) for feeder
    GET  /api/v1/reverse-flow/                 → history (filters + paging)
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.reverse_flow import ReverseFlowEvent
from app.models.user import User

router = APIRouter()


class ReverseFlowEventOut(BaseModel):
    id: int
    feeder_id: str
    detected_at: datetime
    closed_at: Optional[datetime] = None
    net_flow_kw: Optional[float] = None
    duration_s: Optional[int] = None
    status: str
    details: Optional[dict] = None

    model_config = {"from_attributes": True}


def _to_out(row: ReverseFlowEvent) -> ReverseFlowEventOut:
    return ReverseFlowEventOut(
        id=row.id,
        feeder_id=row.feeder_id,
        detected_at=row.detected_at,
        closed_at=row.closed_at,
        net_flow_kw=float(row.net_flow_kw) if row.net_flow_kw is not None else None,
        duration_s=row.duration_s,
        status=row.status,
        details=row.details,
    )


@router.get("/active", response_model=List[ReverseFlowEventOut])
def list_active_reverse_flow(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return all currently-OPEN reverse-flow events (used for UI banner)."""
    rows = (
        db.query(ReverseFlowEvent)
        .filter(ReverseFlowEvent.status == "OPEN")
        .order_by(ReverseFlowEvent.detected_at.desc())
        .all()
    )
    return [_to_out(r) for r in rows]


@router.get("/feeder/{feeder_id}", response_model=List[ReverseFlowEventOut])
def list_feeder_reverse_flow(
    feeder_id: str,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(ReverseFlowEvent)
        .filter(ReverseFlowEvent.feeder_id == feeder_id)
        .order_by(ReverseFlowEvent.detected_at.desc())
        .limit(limit)
        .all()
    )
    return [_to_out(r) for r in rows]


@router.get("/", response_model=List[ReverseFlowEventOut])
def list_reverse_flow_events(
    status: Optional[str] = Query(None, description="OPEN or CLOSED"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(ReverseFlowEvent)
    if status:
        q = q.filter(ReverseFlowEvent.status == status.upper())
    rows = q.order_by(ReverseFlowEvent.detected_at.desc()).offset(offset).limit(limit).all()
    return [_to_out(r) for r in rows]
