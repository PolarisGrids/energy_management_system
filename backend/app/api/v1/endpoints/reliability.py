"""Reliability-index endpoints — spec 016 US3 (MVP)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import (
    RELIABILITY_MANAGE,
    REPORTS_GENERATE,
    require_permission,
)
from app.db.base import get_db
from app.models.notifications import ReliabilityMonthly
from app.models.user import User
from app.services.reliability_calc import compute_monthly

router = APIRouter()


class ReliabilityRow(BaseModel):
    feeder_id: int
    year_month: str
    saidi: Optional[float]
    saifi: Optional[float]
    caidi: Optional[float]
    maifi: Optional[float]
    total_customers: Optional[int]
    computed_at: datetime

    class Config:
        from_attributes = True


@router.get("/indices", response_model=list[ReliabilityRow])
def list_indices(
    month: Optional[str] = Query(default=None, description="YYYY-MM"),
    feeder: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(REPORTS_GENERATE)),
):
    q = db.query(ReliabilityMonthly)
    if month:
        q = q.filter(ReliabilityMonthly.year_month == month)
    if feeder is not None:
        q = q.filter(ReliabilityMonthly.feeder_id == feeder)
    return q.order_by(ReliabilityMonthly.year_month.desc(), ReliabilityMonthly.feeder_id).all()


@router.post("/compute")
def trigger_compute(
    month: str = Query(..., description="YYYY-MM"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(RELIABILITY_MANAGE)),
):
    """Admin-only: compute + upsert reliability indices for a given month."""
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    written = compute_monthly(db, month)
    return {"month": month, "feeders_written": written}
