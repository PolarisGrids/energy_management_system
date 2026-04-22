"""MDMS-sourced dashboard widgets.

    GET /api/v1/mdms-dashboard/summary        — KPI row (meters/DTRs/feeders/comm/alarms/tamper)
    GET /api/v1/mdms-dashboard/load-profile   — last-N-hours hourly load (kW)
    GET /api/v1/mdms-dashboard/alarms         — recent push events (alarm feed)

Product direction: the dashboard's KPI counters, load profile and alarm
feed all come from the MDMS databases (`db_cis`, `validation_rules`,
`gp_hes`). Local EMS data continues to drive the DER asset panel.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.alarm import Alarm, AlarmStatus
from app.models.meter import Meter, MeterStatus, Transformer, Feeder
from app.models.user import User
from app.services import mdms_dashboard_client as md

router = APIRouter()


def _ems_local_counts(db: Session) -> dict:
    """Fallback KPIs from EMS-local tables when MDMS upstream is empty."""
    total = int(db.query(func.count(Meter.id)).scalar() or 0)
    online = int(db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.ONLINE).scalar() or 0)
    offline = int(db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.OFFLINE).scalar() or 0)
    tamper = int(db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.TAMPER).scalar() or 0)
    transformers = int(db.query(func.count(Transformer.id)).scalar() or 0)
    feeders = int(db.query(func.count(Feeder.id)).scalar() or 0)
    active_alarms = int(
        db.query(func.count(Alarm.id)).filter(Alarm.status == AlarmStatus.ACTIVE).scalar() or 0
    )
    rate = round(100.0 * online / total, 2) if total else None
    return {
        "total_meters": total,
        "online_meters": online,
        "offline_meters": offline,
        "tamper_meters": tamper,
        "transformers": transformers,
        "feeders": feeders,
        "active_alarms": active_alarms,
        "comm_success_rate": rate,
    }


class SummaryOut(BaseModel):
    total_meters: int
    online_meters: int
    offline_meters: int
    comm_success_rate: Optional[float]
    total_transformers: int
    total_feeders: int
    active_alarms: int
    tamper_meters: int
    sources: dict


class LoadPointOut(BaseModel):
    ts: datetime
    total_kw: float


class LoadProfileOut(BaseModel):
    hours: int
    points: List[LoadPointOut]


class AlarmOut(BaseModel):
    meter_id: str
    triggered_at: datetime
    messages: List[str]
    indexes: List[int]
    is_tamper: bool


class AlarmsOut(BaseModel):
    count: int
    tamper_count: int
    items: List[AlarmOut]


@router.get("/summary", response_model=SummaryOut)
def summary(
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SummaryOut:
    """Dashboard KPIs with EMS-local fallback.

    MDMS is the product's source of truth, but dev-side upstream tables
    are often sparsely populated — e.g. the validation_rules blockload
    table may hold readings for only a handful of meters, which reduces
    the comm-success-rate to single-digit numbers and makes the dashboard
    look broken. When MDMS is empty or unrealistically low we fall back
    to the EMS-local roster so the dashboard still reflects the fleet
    that the simulator + seed data materially describe.
    """
    fleet = md.fleet_counts()
    comm = md.comm_status(hours=hours, total_meters=fleet.meters)
    al = md.alarms(hours=hours, limit=1)

    ems = _ems_local_counts(db)

    # Fall back to EMS-local when MDMS returns no fleet or an
    # unrealistic (<50%) comm rate against an EMS-local healthy fleet.
    mdms_rate = comm.comm_success_rate
    use_local = (
        fleet.meters == 0
        or (mdms_rate is not None and mdms_rate < 50.0 and (ems["comm_success_rate"] or 0) >= 50.0)
    )

    if use_local:
        total_meters     = ems["total_meters"]
        online_meters    = ems["online_meters"]
        offline_meters   = ems["offline_meters"]
        comm_rate        = ems["comm_success_rate"]
        total_transformers = ems["transformers"]
        total_feeders    = ems["feeders"]
        fleet_source = "ems-local" if ems["total_meters"] else "unavailable"
        comm_source  = "ems-local" if online_meters else (
            "unavailable" if total_meters == 0 else "no-recent-data"
        )
    else:
        total_meters     = fleet.meters
        online_meters    = comm.online_meters
        offline_meters   = comm.offline_meters
        comm_rate        = comm.comm_success_rate
        total_transformers = fleet.dtrs
        total_feeders    = fleet.feeders
        fleet_source = "mdms-cis"
        comm_source  = "mdms-validation" if comm.online_meters else "no-recent-data"

    # Alarm / tamper counts — prefer MDMS, fall back to EMS-local when empty.
    if al.active_count > 0 or al.tamper_count > 0:
        active_alarms = al.active_count
        tamper_meters = al.tamper_count
        alarm_source = "mdms-hes"
    else:
        active_alarms = ems["active_alarms"]
        tamper_meters = ems["tamper_meters"]
        alarm_source = "ems-local" if active_alarms or tamper_meters else "unavailable"

    return SummaryOut(
        total_meters=total_meters,
        online_meters=online_meters,
        offline_meters=offline_meters,
        comm_success_rate=comm_rate,
        total_transformers=total_transformers,
        total_feeders=total_feeders,
        active_alarms=active_alarms,
        tamper_meters=tamper_meters,
        sources={"fleet": fleet_source, "comm": comm_source, "alarms": alarm_source},
    )


@router.get("/load-profile", response_model=LoadProfileOut)
def load_profile(
    hours: int = Query(24, ge=1, le=720),
    _: User = Depends(get_current_user),
) -> LoadProfileOut:
    pts = md.network_load_hourly(hours=hours)
    return LoadProfileOut(
        hours=hours,
        points=[LoadPointOut(ts=p.ts, total_kw=round(p.total_kw, 2)) for p in pts],
    )


@router.get("/alarms", response_model=AlarmsOut)
def alarms(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AlarmsOut:
    a = md.alarms(hours=hours, limit=limit)
    if a.active_count > 0 or a.recent:
        return AlarmsOut(
            count=a.active_count,
            tamper_count=a.tamper_count,
            items=[
                AlarmOut(
                    meter_id=r.meter_id,
                    triggered_at=r.data_timestamp,
                    messages=r.messages,
                    indexes=r.indexes,
                    is_tamper=r.is_tamper,
                )
                for r in a.recent
            ],
        )
    # MDMS mdm_pushevent is empty on this environment — fall back to the
    # EMS-local alarm table so the dashboard's Alarm Feed still has rows.
    # Tamper events are those sourced from meters with MeterStatus.TAMPER
    # or alarms whose type starts with 'tamper'.
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        db.query(Alarm)
        .filter(Alarm.status == AlarmStatus.ACTIVE)
        .filter(Alarm.triggered_at >= since)
        .filter(Alarm.meter_serial.isnot(None))  # drop transformer-level rows
        .order_by(Alarm.triggered_at.desc())
        .limit(limit)
        .all()
    )
    tamper_count = int(
        db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.TAMPER).scalar() or 0
    )
    active_count = int(
        db.query(func.count(Alarm.id)).filter(Alarm.status == AlarmStatus.ACTIVE).scalar() or 0
    )
    items = [
        AlarmOut(
            meter_id=r.meter_serial or f"T-{r.transformer_id or 0}",
            triggered_at=r.triggered_at,
            messages=[r.title or r.alarm_type or "alarm"],
            indexes=[],
            is_tamper=(r.alarm_type or "").lower().startswith("tamper"),
        )
        for r in rows
    ]
    return AlarmsOut(count=active_count, tamper_count=tamper_count, items=items)
