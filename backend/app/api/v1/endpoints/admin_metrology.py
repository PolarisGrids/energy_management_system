"""Admin endpoint: POST /admin/metrology/backfill.

Inline async implementation for MVP — pulls blockload rows from MDMS VEE
and upserts into meter_reading_interval. Returns processed_rows summary.
RBAC hardening deferred (TODO 013-mvp-phase2).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.metrology import MeterReadingInterval
from app.models.user import User
from app.services.metrology_ingest import mdms_vee_reader

router = APIRouter()


class BackfillRequest(BaseModel):
    from_: datetime = Field(..., alias="from")
    to: datetime
    meters: Optional[List[str]] = None

    model_config = {"populate_by_name": True}


class BackfillResult(BaseModel):
    processed_rows: int
    source: str
    started_at: datetime
    completed_at: datetime


@router.post("/backfill", response_model=BackfillResult)
async def run_backfill(
    payload: BackfillRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BackfillResult:
    # TODO(013-mvp-phase2): proper admin RBAC; for MVP require an authenticated user.
    started = datetime.now(timezone.utc)
    try:
        rows = await mdms_vee_reader.fetch_blockload(
            meter_serials=payload.meters,
            from_ts=payload.from_,
            to_ts=payload.to,
            limit=100000,
        )
    except mdms_vee_reader.MdmsVeeUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"metrology source unavailable: {exc}")

    mapped = []
    for r in rows:
        meter_serial = r.get("meter_serial")
        ts = r.get("ts")
        if not meter_serial or not ts:
            continue
        import_wh = r.get("import_wh") or 0.0
        export_wh = r.get("export_wh") or 0.0
        mapped.append({
            "meter_serial": str(meter_serial),
            "ts": ts,
            "channel": 0,
            "value": float(import_wh),
            "quality": "estimated" if r.get("is_estimated") else (
                "valid" if r.get("is_valid") else "raw"
            ),
            "source": "MDMS_VEE_BACKFILL",
            "source_priority": 25,
            "energy_kwh": float(import_wh) / 1000.0 if import_wh else 0.0,
            "energy_export_kwh": float(export_wh) / 1000.0 if export_wh else 0.0,
            "voltage": r.get("avg_voltage"),
            "current": r.get("avg_current"),
            "frequency": r.get("frequency"),
            "is_estimated": bool(r.get("is_estimated")),
            "is_edited": bool(r.get("is_edited")),
            "is_validated": bool(r.get("is_valid")),
            "ingested_at": datetime.now(timezone.utc),
            "trace_id": None,
        })

    processed = 0
    if mapped:
        # Chunk to keep statement sizes sane.
        chunk = 1000
        for i in range(0, len(mapped), chunk):
            batch = mapped[i : i + chunk]
            stmt = pg_insert(MeterReadingInterval).values(batch)
            update_cols = {
                c.name: getattr(stmt.excluded, c.name)
                for c in MeterReadingInterval.__table__.columns
                if c.name not in {"meter_serial", "ts", "channel"}
            }
            stmt = stmt.on_conflict_do_update(
                constraint="pk_mri_serial_ts_ch",
                set_=update_cols,
                where=(
                    MeterReadingInterval.source_priority
                    <= stmt.excluded.source_priority
                ),
            )
            db.execute(stmt)
            processed += len(batch)
        db.commit()

    completed = datetime.now(timezone.utc)
    return BackfillResult(
        processed_rows=processed,
        source="MDMS_VEE_BACKFILL",
        started_at=started,
        completed_at=completed,
    )
