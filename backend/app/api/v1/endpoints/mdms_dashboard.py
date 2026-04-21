"""MDMS-sourced dashboard widgets.

    GET /api/v1/mdms-dashboard/summary        — KPI row (meters/DTRs/feeders/comm/alarms/tamper)
    GET /api/v1/mdms-dashboard/load-profile   — last-N-hours hourly load (kW)
    GET /api/v1/mdms-dashboard/alarms         — recent push events (alarm feed)

Product direction: the dashboard's KPI counters, load profile and alarm
feed all come from the MDMS databases (`db_cis`, `validation_rules`,
`gp_hes`). Local EMS data continues to drive the DER asset panel.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.user import User
from app.services import mdms_dashboard_client as md

router = APIRouter()


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
    _: User = Depends(get_current_user),
) -> SummaryOut:
    fleet = md.fleet_counts()
    comm = md.comm_status(hours=hours, total_meters=fleet.meters)
    al = md.alarms(hours=hours, limit=1)   # just need totals here
    return SummaryOut(
        total_meters=fleet.meters,
        online_meters=comm.online_meters,
        offline_meters=comm.offline_meters,
        comm_success_rate=comm.comm_success_rate,
        total_transformers=fleet.dtrs,
        total_feeders=fleet.feeders,
        active_alarms=al.active_count,
        tamper_meters=al.tamper_count,
        sources={
            "fleet": "mdms-cis" if fleet.meters else "unavailable",
            "comm": "mdms-validation" if comm.online_meters else (
                "unavailable" if fleet.meters == 0 else "no-recent-data"
            ),
            "alarms": "mdms-hes" if al.active_count else "unavailable",
        },
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
    _: User = Depends(get_current_user),
) -> AlarmsOut:
    a = md.alarms(hours=hours, limit=limit)
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
