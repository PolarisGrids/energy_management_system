"""Energy endpoints — spec 018 no-mock-data refactor.

Legacy ``/api/v1/energy/load-profile`` and ``/api/v1/energy/daily-summary``
used to read purely from EMS-local seed tables (``meter_reading`` /
``energy_daily_summary``). They now attempt the MDMS analytics / EGSM-report
upstream first and fall back to the local tables only when MDMS is unavailable
(or ``MDMS_ENABLED`` is off — dev convenience).

The response envelope now carries a ``source`` flag (``"mdms"`` | ``"ems-local"``)
so the frontend can surface an "aggregate pending" banner — identical to the
convention used by ``/api/v1/ntl/*`` and the new ``/api/v1/consumption/*``
endpoints.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.energy import EnergyDailySummary
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.user import User
from app.services.mdms_client import CircuitBreakerError, mdms_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _mdms_on() -> bool:
    return bool(settings.MDMS_ENABLED)


@router.get("/load-profile")
async def load_profile(
    hours: int = Query(24, le=168),
    tariff_class: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """24h (up to 168h) hourly load profile grouped by tariff class.

    Attempts MDMS ``/api/v1/analytics/load-profile`` first; falls back to
    ``meter_reading`` grouped by ``extract(hour)`` when MDMS is off/failing.
    """
    source = "ems-local"
    if _mdms_on():
        try:
            params = {"hours": hours, "group_by": "tariff_class"}
            if tariff_class:
                params["tariff_class"] = tariff_class
            upstream = await mdms_client.load_profile(params)
            if isinstance(upstream, dict) and ("total" in upstream or "series" in upstream or "hours" in upstream):
                upstream.setdefault("source", "mdms")
                return upstream
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS load-profile call failed, falling back: %s", exc)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = (
        db.query(
            func.extract("hour", MeterReading.timestamp).label("hour"),
            Meter.tariff_class,
            func.sum(MeterReading.demand_kw).label("total_kw"),
        )
        .join(Meter, Meter.serial == MeterReading.meter_serial)
        .filter(MeterReading.timestamp >= cutoff)
    )
    if tariff_class:
        q = q.filter(Meter.tariff_class == tariff_class)
    q = q.group_by("hour", Meter.tariff_class).order_by("hour")
    rows = q.all()

    hour_labels = [f"{h:02d}:00" for h in range(24)]
    residential = [0.0] * 24
    commercial = [0.0] * 24
    prepaid = [0.0] * 24
    for hour_val, tc, total_kw in rows:
        h = int(hour_val)
        if tc == "Residential":
            residential[h] += float(total_kw or 0)
        elif tc == "Commercial":
            commercial[h] += float(total_kw or 0)
        else:
            prepaid[h] += float(total_kw or 0)
    total = [round(residential[i] + commercial[i] + prepaid[i], 1) for i in range(24)]
    return {
        "hours": hour_labels,
        "residential": [round(v, 1) for v in residential],
        "commercial": [round(v, 1) for v in commercial],
        "prepaid": [round(v, 1) for v in prepaid],
        "total": total,
        "source": source,
    }


@router.get("/daily-summary")
async def daily_summary(
    days: int = Query(7, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Last-N-days aggregate (import/export/net/peak/pf).

    Tries the MDMS EGSM ``energy-audit/daily-consumption`` report first; on
    failure or when the upstream is off, reads the local
    ``energy_daily_summary`` table.
    """
    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "energy-audit", "daily-consumption", params={"days": days}
            )
            rows = None
            if isinstance(upstream, dict):
                rows = upstream.get("rows") or upstream.get("data")
            if isinstance(rows, list) and rows:
                return {
                    "source": "mdms",
                    "data": [
                        {
                            "date": r.get("date"),
                            "total_import_kwh": float(r.get("total_import_kwh", 0) or 0),
                            "total_export_kwh": float(r.get("total_export_kwh", 0) or 0),
                            "net_kwh": float(r.get("net_kwh", 0) or 0),
                            "peak_demand_kw": float(r.get("peak_demand_kw", 0) or 0),
                            "avg_power_factor": float(r.get("avg_power_factor", 0) or 0),
                        }
                        for r in rows
                    ],
                }
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS daily-summary call failed, falling back: %s", exc)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    rows = (
        db.query(EnergyDailySummary)
        .filter(EnergyDailySummary.date >= cutoff)
        .order_by(EnergyDailySummary.date)
        .all()
    )
    return {
        "source": "ems-local",
        "data": [
            {
                "date": r.date.strftime("%d %b %Y"),
                "total_import_kwh": r.total_import_kwh,
                "total_export_kwh": r.total_export_kwh,
                "net_kwh": r.net_kwh,
                "peak_demand_kw": r.peak_demand_kw,
                "avg_power_factor": r.avg_power_factor,
            }
            for r in rows
        ],
    }


@router.get("/meter-status")
def meter_status(
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    meters = db.query(Meter).offset(offset).limit(limit).all()
    now = datetime.now(timezone.utc)
    result = []
    for m in meters:
        if m.last_seen:
            delta = now - m.last_seen
            minutes = int(delta.total_seconds() / 60)
            last_coll = f"{minutes}m ago" if minutes < 60 else f"{minutes // 60}h {minutes % 60}m ago"
        else:
            last_coll = "—"
        result.append({
            "serial": m.serial,
            "customer_name": m.customer_name,
            "last_collection": last_coll,
            "online": m.status.value == "online",
            "collection_status": "success" if m.status.value == "online" else "failed",
        })
    return {"meters": result}
