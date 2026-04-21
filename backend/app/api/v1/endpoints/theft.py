"""Theft Analysis API — consumed by the `/theft` frontend page.

Endpoints:

  GET  /api/v1/theft/summary              — tier + detector counts, last-run info
  GET  /api/v1/theft/meters               — ranked suspect list (filters + paging)
  GET  /api/v1/theft/meters/{serial}      — full drill-down (scores + evidence +
                                            HH consumption curve + tamper events)
  POST /api/v1/theft/recompute            — manual scorer trigger

All reads consult the persisted ``theft_score`` table; drill-down additionally
pulls live half-hourly + daily + tamper data straight from MDMS for the chart.
Persistence is refreshed by the background loop in :mod:`app.main` lifespan
so the suspect list stays fresh without blocking request threads.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.theft import TheftRunLog, TheftScore
from app.models.user import User
from app.services.theft_analysis import mdms_client as theft_mdms
from app.services.theft_analysis.runner import run_once

log = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────────────

class EvidenceChip(BaseModel):
    id: str
    label: str
    severity: str
    score: float


class MeterSuspect(BaseModel):
    device_identifier: str
    meter_type: Optional[str] = None
    account_id: Optional[str] = None
    manufacturer: Optional[str] = None
    sanctioned_load_kw: Optional[float] = None
    score: float
    risk_tier: str
    fired_detectors: List[str]
    top_evidence: List[EvidenceChip]
    computed_at: datetime


class SuspectListOut(BaseModel):
    total: int
    items: List[MeterSuspect]
    page: int
    page_size: int


class TierCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int


class DetectorFireCount(BaseModel):
    detector_id: str
    count: int


class RunStatus(BaseModel):
    run_id: Optional[int]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    trigger: Optional[str]
    error: Optional[str]


class TheftSummary(BaseModel):
    as_of: datetime
    total_meters: int
    tiers: TierCounts
    detectors: List[DetectorFireCount]
    last_run: Optional[RunStatus]


class HHPoint(BaseModel):
    ts: datetime
    import_wh: Optional[float]
    export_wh: Optional[float]
    avg_current: Optional[float]
    avg_voltage: Optional[float]


class DailyPoint(BaseModel):
    ts: datetime
    import_wh: Optional[float]
    export_wh: Optional[float]
    md_w: Optional[float]


class TamperEventOut(BaseModel):
    event_code: int
    event_label: str
    event_source: str
    event_ts: Optional[datetime]


class MeterDrillDown(BaseModel):
    device_identifier: str
    meter_type: Optional[str]
    account_id: Optional[str]
    manufacturer: Optional[str]
    sanctioned_load_kw: Optional[float]
    score: float
    risk_tier: str
    fired_detectors: List[str]
    top_evidence: List[EvidenceChip]
    detector_results: List[Dict[str, Any]]
    hh_series: List[HHPoint]
    daily_series: List[DailyPoint]
    tamper_events: List[TamperEventOut]
    computed_at: datetime


class RecomputeOut(BaseModel):
    run_id: int
    meters_scored: int
    duration_ms: int
    critical: int
    high: int
    medium: int
    low: int
    trigger: str


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _score_to_suspect(row: TheftScore) -> MeterSuspect:
    return MeterSuspect(
        device_identifier=row.device_identifier,
        meter_type=row.meter_type,
        account_id=row.account_id,
        manufacturer=row.manufacturer,
        sanctioned_load_kw=row.sanctioned_load_kw,
        score=row.score,
        risk_tier=row.risk_tier,
        fired_detectors=list(row.fired_detectors or []),
        top_evidence=[EvidenceChip(**e) for e in (row.top_evidence or [])],
        computed_at=row.computed_at,
    )


def _last_run(db: Session) -> Optional[RunStatus]:
    row = (
        db.query(TheftRunLog)
        .order_by(TheftRunLog.started_at.desc())
        .limit(1)
        .first()
    )
    if row is None:
        return None
    return RunStatus(
        run_id=row.id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        trigger=row.trigger,
        error=row.error,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=TheftSummary)
def theft_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TheftSummary:
    tiers_q = (
        db.query(TheftScore.risk_tier, func.count(TheftScore.device_identifier))
        .group_by(TheftScore.risk_tier)
        .all()
    )
    tier_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for tier, cnt in tiers_q:
        if tier in tier_counts:
            tier_counts[tier] = int(cnt)

    total = sum(tier_counts.values())

    # Detector fire counts — JSONB array membership via materialised expand.
    # Works on both Postgres and SQLite: read the rows and count in Python.
    det_counter: Dict[str, int] = {}
    for (fired,) in db.query(TheftScore.fired_detectors).all():
        for d in fired or []:
            det_counter[d] = det_counter.get(d, 0) + 1
    detectors = sorted(
        (DetectorFireCount(detector_id=k, count=v) for k, v in det_counter.items()),
        key=lambda x: x.count,
        reverse=True,
    )

    return TheftSummary(
        as_of=datetime.now(timezone.utc),
        total_meters=total,
        tiers=TierCounts(**tier_counts),
        detectors=detectors,
        last_run=_last_run(db),
    )


@router.get("/meters", response_model=SuspectListOut)
def theft_meters(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    risk_tier: Optional[str] = Query(
        None, pattern="^(critical|high|medium|low)$",
        description="Filter to a single tier",
    ),
    detector: Optional[str] = Query(
        None, description="Only meters where this detector_id fired",
    ),
    q: Optional[str] = Query(
        None, description="Substring match on device_identifier or account_id",
    ),
    min_score: Optional[float] = Query(
        None, ge=0, le=100,
        description="Return only meters with score ≥ this",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> SuspectListOut:
    qry = db.query(TheftScore)
    if risk_tier:
        qry = qry.filter(TheftScore.risk_tier == risk_tier)
    if min_score is not None:
        qry = qry.filter(TheftScore.score >= min_score)
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (TheftScore.device_identifier.ilike(like))
            | (TheftScore.account_id.ilike(like))
        )

    # JSONB array-contains is dialect-specific; to keep SQLite parity we
    # post-filter in Python for the `detector` predicate.
    qry = qry.order_by(TheftScore.score.desc(), TheftScore.device_identifier)

    all_rows: List[TheftScore] = qry.all()
    if detector:
        all_rows = [r for r in all_rows if detector in (r.fired_detectors or [])]
    total = len(all_rows)

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = all_rows[start:end]
    return SuspectListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[_score_to_suspect(r) for r in page_rows],
    )


@router.get("/meters/{device_identifier}", response_model=MeterDrillDown)
def theft_meter_detail(
    device_identifier: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    hh_days: int = Query(7, ge=1, le=30),
    events_days: int = Query(30, ge=1, le=90),
) -> MeterDrillDown:
    row = (
        db.query(TheftScore)
        .filter(TheftScore.device_identifier == device_identifier)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="theft_score_not_found")

    now = datetime.now(timezone.utc)
    hh = theft_mdms.fetch_hh_window(
        period_start=now - timedelta(days=hh_days),
        period_end=now,
        device_identifiers=[device_identifier],
    )
    daily = theft_mdms.fetch_daily_window(
        period_start=now - timedelta(days=max(hh_days, 14)),
        period_end=now,
        device_identifiers=[device_identifier],
    )
    events = theft_mdms.fetch_tamper_events(
        period_start=now - timedelta(days=events_days),
        period_end=now,
        device_identifiers=[device_identifier],
    )

    return MeterDrillDown(
        device_identifier=row.device_identifier,
        meter_type=row.meter_type,
        account_id=row.account_id,
        manufacturer=row.manufacturer,
        sanctioned_load_kw=row.sanctioned_load_kw,
        score=row.score,
        risk_tier=row.risk_tier,
        fired_detectors=list(row.fired_detectors or []),
        top_evidence=[EvidenceChip(**e) for e in (row.top_evidence or [])],
        detector_results=list(row.detector_results or []),
        hh_series=[
            HHPoint(
                ts=r.ts,
                import_wh=r.import_wh,
                export_wh=r.export_wh,
                avg_current=r.avg_current,
                avg_voltage=r.avg_voltage,
            )
            for r in hh
        ],
        daily_series=[
            DailyPoint(
                ts=r.ts,
                import_wh=r.import_wh,
                export_wh=r.export_wh,
                md_w=r.md_w,
            )
            for r in daily
        ],
        tamper_events=[
            TamperEventOut(
                event_code=e.event_code,
                event_label=e.event_label,
                event_source=e.event_source,
                event_ts=e.event_ts,
            )
            for e in events
        ],
        computed_at=row.computed_at,
    )


@router.post("/recompute", response_model=RecomputeOut)
def theft_recompute(
    _: User = Depends(get_current_user),
) -> RecomputeOut:
    """Manually re-score every meter. Blocks up to a few seconds.

    For larger rosters this should be moved to a task queue — at 174
    meters the full run takes ~1.5s which is fine inline.
    """
    try:
        out = run_once(trigger="manual")
    except Exception as exc:
        log.exception("manual theft recompute failed")
        raise HTTPException(status_code=500, detail=f"recompute_failed: {exc}") from exc
    return RecomputeOut(**out)


__all__ = ["router"]
