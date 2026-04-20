from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.energy import EnergyDailySummary
from app.models.reading import MeterReading
from app.models.meter import Meter

router = APIRouter()


@router.get("/consumption")
def consumption_report(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    feeder: Optional[str] = None,
    tariff_class: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(EnergyDailySummary)
    if from_date:
        q = q.filter(EnergyDailySummary.date >= from_date)
    if to_date:
        q = q.filter(EnergyDailySummary.date <= to_date)
    rows = q.order_by(EnergyDailySummary.date).all()
    return {
        "rows": [
            {"date": r.date.strftime("%d %b %Y"), "import": r.total_import_kwh,
             "export": r.total_export_kwh, "net": r.net_kwh,
             "peak": r.peak_demand_kw, "pf": r.avg_power_factor}
            for r in rows
        ]
    }


@router.get("/meter-readings")
def meter_readings_report(
    meter_serial: str = Query(...),
    days: int = Query(14, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    meter = db.query(Meter).filter(Meter.serial == meter_serial).first()
    customer = meter.customer_name if meter else "Unknown"
    rows = (
        db.query(
            cast(MeterReading.timestamp, Date).label("day"),
            func.sum(MeterReading.energy_import_kwh).label("reading"),
            func.max(MeterReading.demand_kw).label("demand"),
            func.avg(MeterReading.voltage_v).label("voltage"),
            func.avg(MeterReading.power_factor).label("pf"),
            func.sum(MeterReading.is_estimated).label("est_count"),
        )
        .filter(MeterReading.meter_serial == meter_serial)
        .filter(MeterReading.timestamp >= cutoff)
        .group_by("day")
        .order_by("day")
        .all()
    )
    result = []
    cum = 0.0
    for r in rows:
        daily = float(r.reading or 0)
        cum += daily
        result.append({
            "date": r.day.strftime("%d %b"), "reading": round(cum, 2),
            "delta": round(daily, 2), "demand": round(float(r.demand or 0), 1),
            "voltage": round(float(r.voltage or 230), 1),
            "pf": round(float(r.pf or 0.95), 2),
            "estimated": "Y" if (r.est_count or 0) > 0 else "N",
        })
    return {"serial": meter_serial, "customer": customer, "readings": result}


@router.get("/top-consumers")
def top_consumers(
    limit: int = Query(10, le=50),
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(MeterReading.meter_serial, func.sum(MeterReading.energy_import_kwh).label("kwh"))
        .filter(MeterReading.timestamp >= cutoff)
        .group_by(MeterReading.meter_serial)
        .order_by(func.sum(MeterReading.energy_import_kwh).desc())
        .limit(limit)
        .all()
    )
    result = []
    for r in rows:
        meter = db.query(Meter).filter(Meter.serial == r.meter_serial).first()
        result.append({"meter": r.meter_serial, "customer": meter.customer_name if meter else "Unknown", "kwh": round(float(r.kwh or 0), 0)})
    return {"consumers": result}
