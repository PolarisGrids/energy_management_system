"""System Management — SMOC-FUNC-012 registry + performance endpoints.

Powers the /system-management page. All data is derived from existing tables
(meters, transformers, hes_dcus, transformer_sensors, alarms) — no separate
registry table exists today, so we synthesise supplier / manufacturer data
from the available fields (firmware_version + comm_tech) using a stable
mapping. A future W-series phase can plug real supplier metadata in by
extending the meter roster.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.alarm import Alarm
from app.models.hes import HESDCU
from app.models.meter import Feeder, Meter, MeterStatus, Transformer
from app.models.sensor import SensorStatus, TransformerSensor
from app.models.user import User

router = APIRouter()


# ─── Supplier mapping ──────────────────────────────────────────────────────
# The meters table doesn't carry a dedicated supplier column today, so we
# bucket by comm_tech. Swap this for a real lookup once a supplier table
# lands.
_SUPPLIER_BY_COMM = {
    "GPRS":    {"name": "Itron Smart Grid",   "country": "USA",     "id": "SUP-ITRON"},
    "PLC":     {"name": "Landis+Gyr",         "country": "Switzerland", "id": "SUP-LG"},
    "RF Mesh": {"name": "Secure Meters",      "country": "India",   "id": "SUP-SECURE"},
}
_UNKNOWN_SUPPLIER = {"name": "Unclassified", "country": "—", "id": "SUP-UNKNOWN"}


def _supplier_for(comm_tech: Optional[str]) -> Dict[str, str]:
    return _SUPPLIER_BY_COMM.get(comm_tech or "", _UNKNOWN_SUPPLIER)


# ─── Model mapping ──────────────────────────────────────────────────────────
# Meter models synthesised from meter_type + comm_tech so the registry
# reflects real field categories.
def _meter_model(meter_type: Optional[str], comm_tech: Optional[str]) -> str:
    mt = (meter_type or "").upper()
    ct = (comm_tech or "").replace(" ", "")
    table = {
        ("RESIDENTIAL", "GPRS"):   "OpenWay CENTRON-II",
        ("RESIDENTIAL", "PLC"):    "E350 ZCF",
        ("RESIDENTIAL", "RFMesh"): "SM 3100",
        ("COMMERCIAL",  "GPRS"):   "Riva Edge 1000",
        ("COMMERCIAL",  "PLC"):    "E650 S4x",
        ("COMMERCIAL",  "RFMesh"): "SM 4100",
        ("PREPAID",     "GPRS"):   "CENTRON-PP",
        ("PREPAID",     "PLC"):    "E460 PP",
        ("PREPAID",     "RFMesh"): "SM 1100 Prepaid",
    }
    return table.get((mt, ct), f"{mt.title()} LV") if mt else "Generic LV"


def _meter_class(meter_type: Optional[str]) -> str:
    mt = (meter_type or "").upper()
    return {
        "RESIDENTIAL": "Class 1 residential LV",
        "COMMERCIAL":  "Class 0.5S commercial LV",
        "PREPAID":     "Class 1 prepaid LV",
    }.get(mt, "Class 1 general LV")


# ─── Tab 1: Meter Registry ─────────────────────────────────────────────────
@router.get("/meter-registry")
def meter_registry(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Dict[str, Any]:
    total = db.query(func.count(Meter.id)).scalar() or 0
    rows = (
        db.query(
            Meter.meter_type,
            Meter.firmware_version,
            Meter.comm_tech,
            func.count(Meter.id),
            func.min(Meter.installed_at),
            func.max(Meter.installed_at),
        )
        .group_by(Meter.meter_type, Meter.firmware_version, Meter.comm_tech)
        .order_by(func.count(Meter.id).desc())
        .all()
    )
    groups = []
    for meter_type, fw, comm, count, earliest, latest in rows:
        supplier = _supplier_for(comm)
        groups.append({
            "manufacturer": supplier["name"],
            "model": _meter_model(getattr(meter_type, "value", meter_type), comm),
            "firmware_version": fw or "—",
            "comm_technology": comm or "—",
            "meter_class": _meter_class(getattr(meter_type, "value", meter_type)),
            "count": int(count),
            "earliest_installed": earliest.isoformat() if earliest else None,
            "latest_installed": latest.isoformat() if latest else None,
        })
    return {"total_meters": int(total), "groups": groups}


# ─── Tab 2: LV Device Registry ─────────────────────────────────────────────
@router.get("/device-registry")
def device_registry(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Dict[str, Any]:
    devices: List[Dict[str, Any]] = []

    # DCUs — group by firmware + comm_tech (stands in for supplier/model).
    dcu_rows = (
        db.query(HESDCU.firmware_version, HESDCU.comm_tech, func.count(HESDCU.id))
        .group_by(HESDCU.firmware_version, HESDCU.comm_tech)
        .all()
    )
    for fw, comm, count in dcu_rows:
        supplier = _supplier_for(comm)
        devices.append({
            "type": "DCU",
            "manufacturer": supplier["name"],
            "model": f"{comm or '—'} DCU · fw {fw or '—'}",
            "count": int(count),
        })

    # Transformers — bucket by capacity band.
    tx_rows = (
        db.query(Transformer.capacity_kva, func.count(Transformer.id))
        .group_by(Transformer.capacity_kva)
        .order_by(Transformer.capacity_kva)
        .all()
    )
    for cap, count in tx_rows:
        band = "≤100 kVA" if (cap or 0) <= 100 else (
            "100–315 kVA" if (cap or 0) <= 315 else (
                "315–630 kVA" if (cap or 0) <= 630 else ">630 kVA"
            )
        )
        devices.append({
            "type": "Transformer",
            "manufacturer": "ACTOM / Powertech",
            "model": f"Pad-mount DTR · {cap or '—'} kVA ({band})",
            "count": int(count),
        })

    # Sensors — group by sensor_type.
    sensor_rows = (
        db.query(TransformerSensor.sensor_type, func.count(TransformerSensor.id))
        .group_by(TransformerSensor.sensor_type)
        .all()
    )
    for stype, count in sensor_rows:
        devices.append({
            "type": "Sensor",
            "manufacturer": "Emerson / Schweitzer",
            "model": (stype or "—").replace("_", " ").title(),
            "count": int(count),
        })

    total = sum(d["count"] for d in devices)
    # Sort DCUs first, then transformers, then sensors.
    order = {"DCU": 0, "Transformer": 1, "Sensor": 2}
    devices.sort(key=lambda d: (order.get(d["type"], 9), -d["count"]))
    return {"total_devices": int(total), "devices": devices}


# ─── Tab 3: Supplier Performance ───────────────────────────────────────────
@router.get("/supplier-performance")
def supplier_performance(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Dict[str, Any]:
    # Per-comm_tech totals + online counts. Two simple passes rather than a
    # single cross-dialect CASE aggregate — the meter roster is tiny enough
    # that clarity beats query micro-optimisation here.
    totals = dict(
        db.query(Meter.comm_tech, func.count(Meter.id))
        .group_by(Meter.comm_tech)
        .all()
    )
    onlines = dict(
        db.query(Meter.comm_tech, func.count(Meter.id))
        .filter(Meter.status == MeterStatus.ONLINE)
        .group_by(Meter.comm_tech)
        .all()
    )
    # Active alarms per comm_tech (joined via meter's transformer — we
    # approximate by alarm.meter_serial → Meter.comm_tech).
    alarm_rows = (
        db.query(Meter.comm_tech, func.count(Alarm.id))
        .join(Alarm, Alarm.meter_serial == Meter.serial)
        .group_by(Meter.comm_tech)
        .all()
    )
    alarms_by_comm = {k: v for k, v in alarm_rows}

    suppliers: List[Dict[str, Any]] = []
    for comm, total in totals.items():
        online = onlines.get(comm, 0) or 0
        alarms = alarms_by_comm.get(comm, 0) or 0
        total_i = int(total or 0)
        online_i = int(online)
        comm_rate = round(online_i / total_i * 100, 1) if total_i else 0.0
        alarm_rate = round(alarms / max(total_i, 1) * 1000, 1)
        supplier = _supplier_for(comm)
        suppliers.append({
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "country": supplier["country"],
            "total_meters": total_i,
            "online_meters": online_i,
            "comm_success_rate": comm_rate,
            "alarm_rate_per_1000": alarm_rate,
        })
    suppliers.sort(key=lambda s: s["total_meters"], reverse=True)
    return {"suppliers": suppliers}


# ─── Tab 4: Equipment Performance ──────────────────────────────────────────
@router.get("/equipment-performance")
def equipment_performance(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Dict[str, Any]:
    # Group by (comm_tech, meter_type) so every row is a distinct "model".
    totals = (
        db.query(Meter.comm_tech, Meter.meter_type, func.count(Meter.id))
        .group_by(Meter.comm_tech, Meter.meter_type)
        .all()
    )
    onlines_q = (
        db.query(Meter.comm_tech, Meter.meter_type, func.count(Meter.id))
        .filter(Meter.status == MeterStatus.ONLINE)
        .group_by(Meter.comm_tech, Meter.meter_type)
        .all()
    )
    online_by_key = {(c, m): n for c, m, n in onlines_q}

    equipment = []
    for comm, mtype, total in totals:
        total_i = int(total or 0)
        online_i = int(online_by_key.get((comm, mtype), 0))
        failures = total_i - online_i
        supplier = _supplier_for(comm)
        mtype_str = getattr(mtype, "value", mtype)
        equipment.append({
            "manufacturer": supplier["name"],
            "model": _meter_model(mtype_str, comm),
            "total": total_i,
            "online": online_i,
            "failures": failures,
            "online_rate": round(online_i / total_i * 100, 1) if total_i else 0.0,
        })
    equipment.sort(key=lambda e: (-e["total"], e["manufacturer"]))
    return {"equipment": equipment}


# ─── Tab 5: Asset Search ───────────────────────────────────────────────────
_METER_STATUS_ALIAS = {
    "online":       MeterStatus.ONLINE,
    "offline":      MeterStatus.OFFLINE,
    "tamper":       MeterStatus.TAMPER,
    "disconnected": MeterStatus.DISCONNECTED,
}
_SENSOR_STATUS_ALIAS = {
    "normal":   SensorStatus.NORMAL,
    "warning":  SensorStatus.WARNING,
    "critical": SensorStatus.CRITICAL,
    "offline":  SensorStatus.OFFLINE,
}


@router.get("/asset-search")
def asset_search(
    q: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None, description="meter | dcu | transformer | sensor"),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    q_like = f"%{q.strip()}%" if q and q.strip() else None
    atype = (asset_type or "").lower()

    # Meters
    if atype in ("", "meter"):
        mq = db.query(Meter)
        if q_like:
            mq = mq.filter(or_(
                Meter.serial.ilike(q_like),
                Meter.customer_name.ilike(q_like),
                Meter.account_number.ilike(q_like),
            ))
        if status and status in _METER_STATUS_ALIAS:
            mq = mq.filter(Meter.status == _METER_STATUS_ALIAS[status])
        for m in mq.limit(limit).all():
            supplier = _supplier_for(m.comm_tech)
            results.append({
                "asset_type": "Meter",
                "serial": m.serial,
                "manufacturer": supplier["name"],
                "model": _meter_model(getattr(m.meter_type, "value", m.meter_type), m.comm_tech),
                "status": (getattr(m.status, "value", m.status) or "").lower() or None,
                "firmware": m.firmware_version,
                "comm_tech": m.comm_tech,
                "location": m.address,
            })

    # DCUs
    if atype in ("", "dcu"):
        dq = db.query(HESDCU)
        if q_like:
            dq = dq.filter(or_(HESDCU.id.ilike(q_like), HESDCU.location.ilike(q_like)))
        if status:
            dq = dq.filter(HESDCU.status.ilike(status))
        for d in dq.limit(limit).all():
            supplier = _supplier_for(d.comm_tech)
            results.append({
                "asset_type": "DCU",
                "serial": d.id,
                "manufacturer": supplier["name"],
                "model": f"{d.comm_tech or '—'} DCU",
                "status": (d.status or "").lower() or None,
                "firmware": d.firmware_version,
                "comm_tech": d.comm_tech,
                "location": d.location,
            })

    # Transformers
    if atype in ("", "transformer"):
        tq = db.query(Transformer)
        if q_like:
            tq = tq.filter(or_(Transformer.name.ilike(q_like)))
        for t in tq.limit(limit).all():
            results.append({
                "asset_type": "Transformer",
                "serial": t.name,
                "manufacturer": "ACTOM / Powertech",
                "model": f"Pad-mount DTR · {t.capacity_kva or '—'} kVA",
                "status": None,
                "firmware": None,
                "comm_tech": None,
                "location": f"Lat {t.latitude:.3f}, Lon {t.longitude:.3f}" if t.latitude and t.longitude else None,
            })

    # Sensors
    if atype in ("", "sensor"):
        sq = db.query(TransformerSensor)
        if q_like:
            sq = sq.filter(TransformerSensor.name.ilike(q_like))
        if status and status in _SENSOR_STATUS_ALIAS:
            sq = sq.filter(TransformerSensor.status == _SENSOR_STATUS_ALIAS[status])
        for s in sq.limit(limit).all():
            results.append({
                "asset_type": "Sensor",
                "serial": s.name,
                "manufacturer": "Emerson / Schweitzer",
                "model": (s.sensor_type or "—").replace("_", " ").title(),
                "status": (getattr(s.status, "value", s.status) or "").lower() or None,
                "firmware": None,
                "comm_tech": None,
                "location": f"Transformer #{s.transformer_id}",
            })

    # Cap total results consistently.
    results = results[:limit]
    return {"total": len(results), "results": results}
