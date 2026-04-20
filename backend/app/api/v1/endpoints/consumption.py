"""Consumption endpoints — spec 018 no-mock-data closure.

These endpoints serve the metrology surfaces that previously rendered hardcoded
arrays or seeded-local-DB rows in the EMS frontend (``EnergyMonitoring``,
``Reports``, ``Dashboard``). They delegate to the MDMS ``mdms-reports`` EGSM
catalogue whenever an authoritative aggregate exists upstream; otherwise they
fall back to the local ``meter_reading`` / ``energy_daily_summary`` tables and
flag ``source: "ems-local"`` so the UI can surface a "MDMS aggregate pending"
banner.

All responses follow a common envelope::

    {
        "ok": true,
        "data": <payload>,
        "source": "mdms" | "ems-local" | "partial",
        "as_of": "2026-04-18T10:30:00+00:00"
    }

Every route takes the common filter block parsed by ``get_common_filters``
(meter / consumer / dtr / feeder / tariff_class / from / to / interval).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, Date, func
from sqlalchemy.orm import Session

from app.api.v1._filters import CommonFilters, get_common_filters
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.energy import EnergyDailySummary
from app.models.meter import Feeder, Meter, Transformer
from app.models.reading import MeterReading
from app.models.user import User
from app.services.mdms_client import CircuitBreakerError, mdms_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(data: Any, source: str) -> Dict[str, Any]:
    return {"ok": True, "data": data, "source": source, "as_of": _now_iso()}


def _mdms_on() -> bool:
    return bool(settings.MDMS_ENABLED)


# ── 1. /consumption/summary ────────────────────────────────────────────────────


@router.get("/summary")
async def consumption_summary(
    f: CommonFilters = Depends(get_common_filters),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aggregate kWh / kW / PF for the requested scope + window.

    Delegates to MDMS ``energy-audit/monthly-consumption`` when available; on
    any upstream error we compute from local ``meter_reading`` rows (filtered
    by the scope we can honour locally) and flag ``source: "ems-local"``.
    """
    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "energy-audit", "monthly-consumption", params=f.to_mdms_params()
            )
            # MDMS returns either {rows:[...]} or a summary dict. Reduce to a
            # flat summary so the frontend has one contract.
            rows = upstream.get("rows") if isinstance(upstream, dict) else None
            if rows is None and isinstance(upstream, dict):
                rows = upstream.get("data")
            if isinstance(rows, list) and rows:
                imp = sum(float(r.get("total_import_kwh", 0) or 0) for r in rows)
                exp = sum(float(r.get("total_export_kwh", 0) or 0) for r in rows)
                peak = max((float(r.get("peak_demand_kw", 0) or 0) for r in rows), default=0.0)
                pfs = [float(r.get("avg_power_factor", 0) or 0) for r in rows if r.get("avg_power_factor")]
                pf_avg = round(sum(pfs) / len(pfs), 3) if pfs else None
                return _envelope(
                    {
                        "import_kwh": round(imp, 2),
                        "export_kwh": round(exp, 2),
                        "net_kwh": round(imp - exp, 2),
                        "peak_kw": round(peak, 2),
                        "pf_avg": pf_avg,
                        "scope": f.scope,
                        "from": f.from_iso,
                        "to": f.to_iso,
                    },
                    "mdms",
                )
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover — network
            logger.warning("MDMS monthly-consumption call failed, falling back: %s", exc)

    # Local fallback from EnergyDailySummary (dev seed) + meter_reading.
    q = db.query(EnergyDailySummary).filter(
        EnergyDailySummary.date >= f.from_dt.date(),
        EnergyDailySummary.date <= f.to_dt.date(),
    )
    rows = q.all()
    if rows:
        imp = sum(r.total_import_kwh or 0 for r in rows)
        exp = sum(r.total_export_kwh or 0 for r in rows)
        peak = max((r.peak_demand_kw or 0 for r in rows), default=0.0)
        pfs = [r.avg_power_factor for r in rows if r.avg_power_factor]
        pf_avg = round(sum(pfs) / len(pfs), 3) if pfs else None
    else:
        imp = exp = peak = 0.0
        pf_avg = None
    return _envelope(
        {
            "import_kwh": round(float(imp), 2),
            "export_kwh": round(float(exp), 2),
            "net_kwh": round(float(imp - exp), 2),
            "peak_kw": round(float(peak), 2),
            "pf_avg": pf_avg,
            "scope": f.scope,
            "from": f.from_iso,
            "to": f.to_iso,
            "banner": "MDMS aggregate pending — showing EMS-local fallback",
        },
        "ems-local",
    )


# ── 2. /consumption/load-profile ───────────────────────────────────────────────


@router.get("/load-profile")
async def consumption_load_profile(
    f: CommonFilters = Depends(get_common_filters),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Hourly / half-hourly timeseries of kW import / export / kvarh."""
    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "load-management", "hourly-load", params=f.to_mdms_params()
            )
            series = None
            if isinstance(upstream, dict):
                series = upstream.get("series") or upstream.get("rows") or upstream.get("data")
            if isinstance(series, list):
                return _envelope(
                    {
                        "interval": f.interval,
                        "scope": f.scope,
                        "points": [
                            {
                                "ts": p.get("ts") or p.get("timestamp"),
                                "kw_import": float(p.get("kw_import", p.get("demand_kw", 0)) or 0),
                                "kw_export": float(p.get("kw_export", 0) or 0),
                                "kvarh": float(p.get("kvarh", 0) or 0),
                            }
                            for p in series
                        ],
                    },
                    "mdms",
                )
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS hourly-load call failed, falling back: %s", exc)

    # Local fallback: aggregate meter_reading by hour within window.
    q = (
        db.query(
            func.date_trunc("hour", MeterReading.timestamp).label("ts"),
            func.sum(MeterReading.demand_kw).label("kw_import"),
        )
        .filter(
            MeterReading.timestamp >= f.from_dt,
            MeterReading.timestamp <= f.to_dt,
        )
    )
    if f.meter:
        q = q.filter(MeterReading.meter_serial == f.meter)
    q = q.group_by("ts").order_by("ts")
    try:
        rows = q.all()
    except Exception:  # SQLite may not support date_trunc — degrade gracefully.
        rows = []

    points = [
        {
            "ts": (r.ts.isoformat() if hasattr(r.ts, "isoformat") else str(r.ts)),
            "kw_import": round(float(r.kw_import or 0), 2),
            "kw_export": 0.0,
            "kvarh": 0.0,
        }
        for r in rows
    ]
    return _envelope(
        {
            "interval": f.interval,
            "scope": f.scope,
            "points": points,
            "banner": "MDMS load-profile pending — showing EMS-local fallback",
        },
        "ems-local",
    )


# ── 3. /consumption/feeder-breakdown ───────────────────────────────────────────


@router.get("/feeder-breakdown")
async def consumption_feeder_breakdown(
    date: Optional[str] = Query(None, description="ISO date; defaults to today (UTC)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Per-feeder kWh totals for ``date`` (default = today)."""
    day = date or datetime.now(timezone.utc).date().isoformat()
    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "energy-audit", "feeder-loss-summary", params={"date": day}
            )
            rows = None
            if isinstance(upstream, dict):
                rows = upstream.get("rows") or upstream.get("data")
            if isinstance(rows, list):
                out = [
                    {
                        "feeder": r.get("feeder_name") or r.get("feeder") or r.get("feeder_id"),
                        "feeder_id": r.get("feeder_id"),
                        "kwh": round(float(r.get("total_kwh", r.get("downstream_kwh", 0)) or 0), 2),
                        "loss_kwh": round(float(r.get("loss_kwh", 0) or 0), 2),
                        "loss_pct": round(float(r.get("loss_pct", 0) or 0), 2),
                    }
                    for r in rows
                ]
                return _envelope({"date": day, "rows": out}, "mdms")
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS feeder-loss-summary call failed, falling back: %s", exc)

    # Local fallback — sum meter_reading.energy_import_kwh per feeder.
    q = (
        db.query(
            Feeder.id.label("feeder_id"),
            Feeder.name.label("feeder_name"),
            func.coalesce(func.sum(MeterReading.energy_import_kwh), 0.0).label("kwh"),
        )
        .outerjoin(Transformer, Transformer.feeder_id == Feeder.id)
        .outerjoin(Meter, Meter.transformer_id == Transformer.id)
        .outerjoin(MeterReading, MeterReading.meter_serial == Meter.serial)
        .group_by(Feeder.id, Feeder.name)
        .order_by(Feeder.id)
    )
    rows = [
        {"feeder": r.feeder_name, "feeder_id": r.feeder_id, "kwh": round(float(r.kwh or 0), 2), "loss_kwh": 0.0, "loss_pct": 0.0}
        for r in q.all()
    ]
    return _envelope(
        {
            "date": day,
            "rows": rows,
            "banner": "MDMS feeder aggregate pending — showing EMS-local fallback",
        },
        "ems-local",
    )


# ── 4. /consumption/by-class ──────────────────────────────────────────────────


@router.get("/by-class")
async def consumption_by_class(
    period: str = Query("month", pattern="^(day|week|month)$"),
    date: Optional[str] = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Consumption aggregate broken down by tariff class."""
    as_of = date or datetime.now(timezone.utc).date().isoformat()
    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "energy-audit", "consumption-by-class", params={"period": period, "date": as_of}
            )
            rows = None
            if isinstance(upstream, dict):
                rows = upstream.get("rows") or upstream.get("data")
            if isinstance(rows, list):
                out = [
                    {
                        "tariff_class": r.get("tariff_class") or r.get("class"),
                        "kwh": round(float(r.get("kwh", r.get("total_kwh", 0)) or 0), 2),
                        "pct": round(float(r.get("pct", 0) or 0), 2),
                    }
                    for r in rows
                ]
                return _envelope({"period": period, "date": as_of, "rows": out}, "mdms")
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS consumption-by-class call failed, falling back: %s", exc)

    # Local fallback — group local readings joined to meters by tariff_class.
    q = (
        db.query(
            Meter.tariff_class.label("tariff_class"),
            func.coalesce(func.sum(MeterReading.energy_import_kwh), 0.0).label("kwh"),
        )
        .outerjoin(MeterReading, MeterReading.meter_serial == Meter.serial)
        .group_by(Meter.tariff_class)
    )
    raw = q.all()
    total = sum(float(r.kwh or 0) for r in raw) or 1.0
    rows = [
        {
            "tariff_class": r.tariff_class or "Unknown",
            "kwh": round(float(r.kwh or 0), 2),
            "pct": round(100.0 * float(r.kwh or 0) / total, 2),
        }
        for r in raw
    ]
    return _envelope(
        {
            "period": period,
            "date": as_of,
            "rows": rows,
            "banner": "MDMS class breakdown pending — showing EMS-local fallback",
        },
        "ems-local",
    )


# ── 5. /consumption/monthly ───────────────────────────────────────────────────


@router.get("/monthly")
async def consumption_monthly(
    months: int = Query(6, ge=1, le=24),
    tariff_class: Optional[str] = Query(None),
    feeder: Optional[str] = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Last-N months kWh totals."""
    params = {"months": months}
    if tariff_class:
        params["tariff_class"] = tariff_class
    if feeder:
        params["feeder"] = feeder

    if _mdms_on():
        try:
            upstream = await mdms_client.list_egsm_report(
                "energy-audit", "monthly-consumption", params=params
            )
            rows = None
            if isinstance(upstream, dict):
                rows = upstream.get("rows") or upstream.get("data")
            if isinstance(rows, list):
                out = [
                    {
                        "month": r.get("billing_month") or r.get("month"),
                        "import_kwh": round(float(r.get("total_import_kwh", r.get("kwh", 0)) or 0), 2),
                        "export_kwh": round(float(r.get("total_export_kwh", 0) or 0), 2),
                    }
                    for r in rows
                ]
                return _envelope({"months": months, "rows": out}, "mdms")
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS monthly-consumption call failed, falling back: %s", exc)

    # Local fallback — group EnergyDailySummary by month.
    rows = (
        db.query(
            func.to_char(EnergyDailySummary.date, "YYYY-MM").label("month"),
            func.coalesce(func.sum(EnergyDailySummary.total_import_kwh), 0.0).label("imp"),
            func.coalesce(func.sum(EnergyDailySummary.total_export_kwh), 0.0).label("exp"),
        )
        .group_by("month")
        .order_by("month")
        .all()
        if _supports_to_char(db)
        else []
    )
    out = [
        {"month": r.month, "import_kwh": round(float(r.imp or 0), 2), "export_kwh": round(float(r.exp or 0), 2)}
        for r in rows[-months:]
    ]
    return _envelope(
        {
            "months": months,
            "rows": out,
            "banner": "MDMS monthly aggregate pending — showing EMS-local fallback",
        },
        "ems-local",
    )


def _supports_to_char(db: Session) -> bool:
    """SQLite (used in unit tests) lacks ``to_char``; guard so local fallback
    still returns a shaped envelope under the test harness."""
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    return dialect == "postgresql"
