"""Data Accuracy console endpoint — spec 018 W4.T14.

Reads from the `source_status` cache (refreshed by the background scheduler
in :mod:`app.services.source_status_refresher`) and computes a per-meter
health badge server-side.

Routes:

    GET  /api/v1/data-accuracy            — list with filter + badge
    POST /api/v1/data-accuracy/{serial}/reconcile  — queue a reconcile action
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import (
    P_DATA_ACCURACY_READ,
    P_DATA_ACCURACY_RECONCILE,
    require_permission,
)
from app.db.base import get_db
from app.models.source_status import SourceStatus
from app.models.user import User
from app.schemas.data_accuracy import (
    DataAccuracyReconcileResponse,
    DataAccuracyResponse,
    DataAccuracyRow,
)
from app.services.audit_publisher import publish_audit
from app.services.source_status_refresher import compute_status, refresh_once

log = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=DataAccuracyResponse,
    dependencies=[Depends(require_permission(P_DATA_ACCURACY_READ))],
)
def list_data_accuracy(
    meter_serial: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="healthy|lagging|missing_mdms|missing_cis|stale"),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(SourceStatus)
    if meter_serial:
        q = q.filter(SourceStatus.meter_serial == meter_serial)
    rows = q.offset(offset).limit(limit).all()

    enriched = []
    for r in rows:
        row_status = compute_status(
            r.hes_last_seen,
            r.mdms_last_validated,
            r.cis_last_billing,
        )
        if status and row_status != status:
            continue
        enriched.append(
            DataAccuracyRow(
                meter_serial=r.meter_serial,
                hes_last_seen=r.hes_last_seen,
                mdms_last_validated=r.mdms_last_validated,
                cis_last_billing=r.cis_last_billing,
                updated_at=r.updated_at,
                status=row_status,
            )
        )

    counts = Counter(r.status for r in enriched)
    return DataAccuracyResponse(
        total=len(enriched),
        rows=enriched,
        counts_by_status=dict(counts),
    )


@router.post(
    "/refresh",
    dependencies=[Depends(require_permission(P_DATA_ACCURACY_RECONCILE))],
)
async def force_refresh(
    current_user: User = Depends(get_current_user),
):
    """Force an ad-hoc refresh pass. Useful for operators after a known upstream blip."""
    start = perf_counter()
    try:
        stats = await refresh_once()
    except Exception as exc:
        log.exception("manual refresh failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    await publish_audit(
        action_type="WRITE",
        action_name="data_accuracy_refresh",
        entity_type="SourceStatus",
        entity_id="batch",
        method="POST",
        path="/api/v1/data-accuracy/refresh",
        response_status=200,
        user_id=str(current_user.id),
        request_data=stats,
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return stats


@router.post(
    "/{meter_serial}/reconcile",
    response_model=DataAccuracyReconcileResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(P_DATA_ACCURACY_RECONCILE))],
)
async def reconcile_meter(
    meter_serial: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a reconciliation issue for a single meter.

    Creates an "issue ID" (audit-trail token) the operator can use to track
    the reconciliation in the standard audit console. The heavy lifting is
    delegated to the MDMS VEE engine out-of-band; here we just record intent.
    """
    start = perf_counter()
    row = db.get(SourceStatus, meter_serial)
    if not row:
        raise HTTPException(status_code=404, detail="meter not in source_status cache")
    issue_id = str(uuid.uuid4())
    await publish_audit(
        action_type="WRITE",
        action_name="reconcile_meter",
        entity_type="SourceStatus",
        entity_id=meter_serial,
        method="POST",
        path=f"/api/v1/data-accuracy/{meter_serial}/reconcile",
        response_status=202,
        user_id=str(current_user.id),
        request_data={"issue_id": issue_id},
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return DataAccuracyReconcileResponse(
        meter_serial=meter_serial,
        issue_id=issue_id,
    )
