from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.hes import HESDCU, HESCommandLog, HESFOTAJob
from app.models.meter import Meter
from app.models.reading import MeterReading

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
    rows = db.query(Meter.firmware_version, func.count()).group_by(Meter.firmware_version).order_by(func.count().desc()).all()
    return {"versions": [{"version": v, "count": c} for v, c in rows]}


@router.get("/comm-trend")
def comm_trend(days: int = Query(7, le=14), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    total_meters = db.query(func.count(Meter.id)).scalar() or 1
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
        trend.append({"day": day_names[day.weekday()], "value": min(rate, 100.0)})
    return {"trend": trend}
