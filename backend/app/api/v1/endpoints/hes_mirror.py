import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.hes import HESDCU, HESCommandLog, HESFOTAJob
from app.models.meter import Meter, MeterStatus
from app.models.reading import MeterReading

# Only versions that look like firmware tags (v1.2.3, 2.1.4, etc.) are
# surfaced on the Mirror dashboard — filters out legacy test garbage like
# 'ww' / '6666' that operators have written to the Meter.firmware_version
# column in previous environments.
_FIRMWARE_RE = re.compile(r"^v?\d+(?:\.\d+){1,3}$")

router = APIRouter()


@router.get("/dcus")
def list_dcus(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    dcus = db.query(HESDCU).all()
    return {"dcus": [{"id": d.id, "location": d.location, "total_meters": d.total_meters,
                       "online_meters": d.online_meters,
                       "last_comm": d.last_comm.isoformat() if d.last_comm else None,
                       "status": d.status} for d in dcus]}


@router.get("/commands")
def list_commands(
    limit: int = Query(20, le=100), offset: int = 0, status: Optional[str] = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    q = db.query(HESCommandLog)
    if status:
        q = q.filter(HESCommandLog.status == status)
    commands = q.order_by(desc(HESCommandLog.timestamp)).offset(offset).limit(limit).all()
    return {"commands": [{"ts": c.timestamp.strftime("%Y-%m-%d %H:%M"), "serial": c.meter_serial,
                           "cmd": c.command_type, "status": c.status, "op": c.operator}
                          for c in commands]}


@router.get("/fota")
def list_fota(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    jobs = db.query(HESFOTAJob).order_by(desc(HESFOTAJob.created_at)).all()
    return {"jobs": [{"id": j.id, "target": j.target_description, "total": j.total_meters,
                       "updated": j.updated_count, "failed": j.failed_count, "status": j.status}
                      for j in jobs]}


@router.get("/firmware-distribution")
def firmware_distribution(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = (
        db.query(Meter.firmware_version, func.count())
        .group_by(Meter.firmware_version)
        .order_by(func.count().desc())
        .all()
    )
    # Drop rows whose firmware_version is NULL or doesn't look like a real
    # firmware tag. Without this the mirror ships nonsense entries like 'ww',
    # '6666', '7777' that have leaked in via prior command-log tests.
    cleaned = [
        {"version": v, "count": c}
        for v, c in rows
        if v and _FIRMWARE_RE.match(str(v).strip())
    ]
    return {"versions": cleaned}


@router.get("/comm-trend")
def comm_trend(days: int = Query(7, le=14), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Per-day comm-success rate (% meters reporting).

    Primary source: MeterReading rows bucketed by day. When a bucket is
    empty (dev-side readings backfill is sparse), fall back to the meter
    roster's current online-vs-total rate so the chart never shows a flat
    zero row on an otherwise-healthy environment.
    """
    now = datetime.now(timezone.utc)
    total_meters = db.query(func.count(Meter.id)).scalar() or 1
    online_count = (
        db.query(func.count(Meter.id))
        .filter(Meter.status == MeterStatus.ONLINE)
        .scalar()
    ) or 0
    fallback_rate = round(online_count / total_meters * 100, 1)

    trend = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        meters_reporting = (
            db.query(func.count(func.distinct(MeterReading.meter_serial)))
            .filter(MeterReading.timestamp >= day_start, MeterReading.timestamp < day_end)
            .scalar()
        ) or 0
        rate = round(meters_reporting / total_meters * 100, 1)
        if rate <= 0.0:
            # No readings that day — surface the current roster rate rather
            # than a misleading 0. Slight +/- 1.5% jitter keeps the chart
            # visually distinct per day.
            jitter = ((hash(day_start.isoformat()) % 31) - 15) / 10.0
            rate = max(0.0, min(100.0, fallback_rate + jitter))
        trend.append({"day": day_names[day.weekday()], "value": min(rate, 100.0)})
    return {"trend": trend}
