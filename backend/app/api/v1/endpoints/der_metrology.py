"""DER metrology read endpoint (W5).

Routes mounted under `/der`:

* `GET /der/{asset_id}/metrology?window=24h|7d|30d|custom&from&to`
   — interval reads (recent) + daily rollups (longer windows). Empty arrays
     when no data — never synthesises values.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import P_DER_READ, require_permission
from app.db.base import get_db
from app.models.der_ems import DERAssetEMS
from app.models.der_metrology import DERMetrology, DERMetrologyDaily
from app.models.user import User
from app.schemas.der_metrology import (
    DERMetrologyDailyRow,
    DERMetrologyReading,
    DERMetrologyResponse,
)

router = APIRouter()


_INTERVAL_WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get(
    "/{asset_id}/metrology",
    response_model=DERMetrologyResponse,
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def get_der_metrology(
    asset_id: str,
    window: Literal["24h", "7d", "30d", "custom"] = Query("24h"),
    from_: Optional[datetime] = Query(
        None,
        alias="from",
        description="Custom range start (ISO-8601). Required when window=custom.",
    ),
    to: Optional[datetime] = Query(
        None,
        description="Custom range end (ISO-8601). Defaults to now when omitted.",
    ),
    daily_only: bool = Query(
        False,
        description="Skip the interval payload and only return the daily rollup",
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(DERAssetEMS).filter(DERAssetEMS.id == asset_id).first():
        raise HTTPException(404, detail="asset not found")

    now = datetime.now(timezone.utc)
    if window == "custom":
        if from_ is None:
            raise HTTPException(400, detail="from is required when window=custom")
        start = from_
        end = to or now
        if end < start:
            raise HTTPException(400, detail="to must be >= from")
        if (end - start).days > 365:
            raise HTTPException(400, detail="custom window cannot exceed 365 days")
    else:
        start = now - _INTERVAL_WINDOWS[window]
        end = now

    interval_rows: list[DERMetrology] = []
    if not daily_only:
        # Cap to 5k rows to bound payload — daily rollup is the answer for
        # anything beyond ~3 days at 5-min resolution.
        interval_rows = (
            db.query(DERMetrology)
            .filter(
                DERMetrology.asset_id == asset_id,
                DERMetrology.ts >= start,
                DERMetrology.ts <= end,
            )
            .order_by(DERMetrology.ts.asc())
            .limit(5000)
            .all()
        )

    daily_rows = (
        db.query(DERMetrologyDaily)
        .filter(
            DERMetrologyDaily.asset_id == asset_id,
            DERMetrologyDaily.date >= start.date(),
            DERMetrologyDaily.date <= end.date(),
        )
        .order_by(DERMetrologyDaily.date.asc())
        .all()
    )

    banner: Optional[str] = None
    if not interval_rows and not daily_rows:
        banner = (
            "No DER metrology in window — der_metrology is populated by the "
            "billing-grade ingestion path (DER_TELEMETRY rollup or revenue meter)."
        )

    return DERMetrologyResponse(
        asset_id=asset_id,
        window=window,
        interval=[DERMetrologyReading.model_validate(r) for r in interval_rows],
        daily=[DERMetrologyDailyRow.model_validate(r) for r in daily_rows],
        banner=banner,
    )
