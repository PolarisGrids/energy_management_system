from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.reading import MeterReading
from pydantic import BaseModel

router = APIRouter()


class ReadingOut(BaseModel):
    id: int
    meter_serial: str
    timestamp: datetime
    energy_import_kwh: float
    energy_export_kwh: float
    demand_kw: float
    voltage_v: Optional[float]
    current_a: Optional[float]
    power_factor: Optional[float]
    frequency_hz: float
    thd_percent: Optional[float]
    is_estimated: int

    model_config = {"from_attributes": True}


@router.get("/{serial}/interval", response_model=List[ReadingOut])
def get_interval_readings(
    serial: str,
    hours: int = Query(24, le=168),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return (
        db.query(MeterReading)
        .filter(MeterReading.meter_serial == serial, MeterReading.timestamp >= since)
        .order_by(MeterReading.timestamp)
        .all()
    )


@router.get("/{serial}/latest", response_model=ReadingOut)
def get_latest_reading(
    serial: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    reading = (
        db.query(MeterReading)
        .filter(MeterReading.meter_serial == serial)
        .order_by(MeterReading.timestamp.desc())
        .first()
    )
    if not reading:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No readings found")
    return reading
