"""SLA KPIs for the dashboard.

    GET /api/v1/sla/kpis  — month-to-date SLA per metrology profile

SLA definition: ``valid_records / (valid + invalid + estimated)`` from the
MDMS `validation_rules.data_availability` table, aggregated from the first
of the current month (UTC). Returns one row per profile_type plus device
counts (meters from MDMS CIS; DTR/feeders from local system tables) so the
dashboard can show the SLA alongside the population it is measured against.

When either upstream is unavailable the endpoint degrades gracefully:
missing SLA rows come back as an empty `profiles` list rather than 500.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.meter import Feeder, Transformer
from app.models.user import User
from app.services import mdms_cis_client as cis
from app.services import mdms_validation_client as val

router = APIRouter()


class ProfileSlaOut(BaseModel):
    profile_type: str
    label: str
    valid: int
    invalid: int
    estimated: int
    expected: int
    received: int
    sla_pct: Optional[float]


class DeviceCountsOut(BaseModel):
    meters: int       # from MDMS CIS consumer_master_data
    dtrs: int         # local transformers table
    feeders: int      # local feeders table


class SlaKpisOut(BaseModel):
    period_start: datetime
    period_end: datetime
    devices: DeviceCountsOut
    profiles: List[ProfileSlaOut]
    sources: dict     # {"sla": "mdms|unavailable", "meters": "mdms|unavailable"}


@router.get("/kpis", response_model=SlaKpisOut)
def sla_kpis(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SlaKpisOut:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    rows = val.profile_sla(period_start=start, period_end=now)
    profiles = [
        ProfileSlaOut(
            profile_type=r.profile_type,
            label=r.label,
            valid=r.valid,
            invalid=r.invalid,
            estimated=r.estimated,
            expected=r.expected,
            received=r.received,
            sla_pct=r.sla_pct,
        )
        for r in rows
    ]

    meters = cis.count_consumers()
    dtrs = int(db.query(func.count(Transformer.id)).scalar() or 0)
    feeders = int(db.query(func.count(Feeder.id)).scalar() or 0)

    return SlaKpisOut(
        period_start=start,
        period_end=now,
        devices=DeviceCountsOut(meters=meters, dtrs=dtrs, feeders=feeders),
        profiles=profiles,
        sources={
            "sla": "mdms" if profiles else "unavailable",
            "meters": "mdms" if meters else "unavailable",
        },
    )
