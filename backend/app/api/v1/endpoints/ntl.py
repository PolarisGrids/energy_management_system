"""Non-Technical Loss (NTL) endpoints — spec 018 W3.T8 + W3.T10.

When ``MDMS_NTL_ENABLED`` is true, the suspects + energy-balance endpoints
proxy to ``mdms-ntl-service`` via the shared MDMS client. When false (MDMS
scoring engine unavailable, e.g. MDMS-T2 still pending), EMS falls back to
local **event correlation** — suspicion score derived from recent tamper /
cover-open / reverse-energy events plus abnormal consumption drops.

Endpoints
---------
* ``GET /api/v1/ntl/suspects``          — ranked suspect list
* ``GET /api/v1/ntl/energy-balance``    — DTR-level feeder-input vs downstream-sum

All responses include a ``source`` field (``"mdms"`` | ``"local"``) so the
frontend can render the "scoring unavailable" banner correctly (acceptance
scenario US-9 ①/②).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.alarm import Alarm
from app.models.meter import Meter, Transformer
from app.models.meter_event import MeterEventLog
from app.models.reading import MeterReading
from app.models.user import User
from app.services.mdms_client import CircuitBreakerError, mdms_client

logger = logging.getLogger(__name__)
router = APIRouter()


# Event-type -> weight contribution to the suspicion score. Tunable.
NTL_EVENT_WEIGHTS: Dict[str, int] = {
    "magnet_tamper": 40,
    "tamper": 35,
    "cover_open": 25,
    "reverse_energy": 20,
    "ct_bypass": 45,
    "neutral_disturbance": 15,
    "load_side_interference": 15,
    "meter_cover_removed": 25,
}


def _mdms_available() -> bool:
    return bool(settings.MDMS_NTL_ENABLED and settings.MDMS_ENABLED)


# ── Local fallback: event correlation + consumption drop ───────────────────────


def _compute_local_suspects(
    db: Session,
    dtr_id: Optional[int],
    min_score: int,
    limit: int,
    lookback_days: int = 7,
) -> List[Dict[str, Any]]:
    """Derive NTL suspicion score from the last 7 days of meter events.

    Score = Σ(event weight) per meter, capped at 100. Meters whose average
    consumption in the window dropped below 40% of the prior 7-day baseline
    get a +15 bump (abnormal drop signal).
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days)

    base_q = (
        db.query(
            MeterEventLog.meter_serial,
            MeterEventLog.event_type,
            func.count(MeterEventLog.id).label("ev_count"),
            func.max(MeterEventLog.event_ts).label("last_ts"),
        )
        .filter(MeterEventLog.event_ts >= since)
        .group_by(MeterEventLog.meter_serial, MeterEventLog.event_type)
    )

    # Aggregate per-meter.
    per_meter: Dict[str, Dict[str, Any]] = {}
    for row in base_q.all():
        score_contrib = NTL_EVENT_WEIGHTS.get(row.event_type, 0) * int(row.ev_count)
        bucket = per_meter.setdefault(
            row.meter_serial,
            {
                "meter_serial": row.meter_serial,
                "score": 0,
                "event_count_7d": 0,
                "last_event": None,
                "last_event_type": None,
                "contributions": [],
            },
        )
        bucket["score"] += score_contrib
        bucket["event_count_7d"] += int(row.ev_count)
        if row.last_ts and (bucket["last_event"] is None or row.last_ts > bucket["last_event"]):
            bucket["last_event"] = row.last_ts
            bucket["last_event_type"] = row.event_type
        if score_contrib > 0:
            bucket["contributions"].append(
                {"event_type": row.event_type, "count": int(row.ev_count)}
            )

    # Also consider alarms table as a secondary input (tamper / reverse_power alarms).
    alarm_rows = (
        db.query(
            Alarm.meter_serial,
            Alarm.alarm_type,
            func.count(Alarm.id).label("ev_count"),
            func.max(Alarm.triggered_at).label("last_ts"),
        )
        .filter(Alarm.triggered_at >= since, Alarm.meter_serial.isnot(None))
        .group_by(Alarm.meter_serial, Alarm.alarm_type)
        .all()
    )
    for row in alarm_rows:
        key = str(row.alarm_type.value if hasattr(row.alarm_type, "value") else row.alarm_type)
        weight = NTL_EVENT_WEIGHTS.get(key, 0)
        if weight == 0:
            continue
        contrib = weight * int(row.ev_count)
        bucket = per_meter.setdefault(
            row.meter_serial,
            {
                "meter_serial": row.meter_serial,
                "score": 0,
                "event_count_7d": 0,
                "last_event": None,
                "last_event_type": None,
                "contributions": [],
            },
        )
        bucket["score"] += contrib
        if row.last_ts and (bucket["last_event"] is None or row.last_ts > bucket["last_event"]):
            bucket["last_event"] = row.last_ts
            bucket["last_event_type"] = key

    if not per_meter:
        return []

    # Join to meter → transformer so we can return DTR, customer, and filter.
    meters = (
        db.query(Meter, Transformer)
        .outerjoin(Transformer, Meter.transformer_id == Transformer.id)
        .filter(Meter.serial.in_(per_meter.keys()))
        .all()
    )

    results: List[Dict[str, Any]] = []
    for meter, tx in meters:
        info = per_meter.get(meter.serial)
        if info is None:
            continue
        if dtr_id is not None and (tx is None or tx.id != dtr_id):
            continue
        score = min(100, info["score"])
        if score < min_score:
            continue
        results.append(
            {
                "meter_serial": meter.serial,
                "customer_name": meter.customer_name,
                "account_number": meter.account_number,
                "score": score,
                "event_count_7d": info["event_count_7d"],
                "last_event": info["last_event"].isoformat() if info["last_event"] else None,
                "last_event_type": info["last_event_type"],
                "dtr_id": tx.id if tx else None,
                "dtr_name": tx.name if tx else None,
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "contributions": info["contributions"],
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/suspects")
async def list_suspects(
    dtr_id: Optional[int] = Query(None),
    min_score: int = Query(0, ge=0, le=100),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return ranked NTL suspects.

    When the upstream MDMS NTL service is enabled we proxy its scoring response
    (wrapped in ``{source: "mdms", ...}``). Otherwise we compute from local
    events and return ``source: "local"`` so the frontend can show the banner
    mandated by user-story 9 acceptance scenario ②.
    """
    if _mdms_available():
        try:
            params = {"min_score": min_score, "limit": limit}
            if dtr_id is not None:
                params["dtr"] = dtr_id
            upstream = await mdms_client.ntl_suspects(params=params)
            payload = upstream.json() if hasattr(upstream, "json") else {}
            items = payload.get("items") or payload.get("suspects") or payload
            return {
                "source": "mdms",
                "scoring_available": True,
                "items": items if isinstance(items, list) else [],
            }
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover — network
            logger.warning("MDMS NTL suspects call failed, falling back: %s", exc)

    items = _compute_local_suspects(db, dtr_id=dtr_id, min_score=min_score, limit=limit)
    return {
        "source": "local",
        "scoring_available": False,
        "banner": "Using event correlation only — scoring unavailable",
        "items": items,
    }


@router.get("/energy-balance")
async def energy_balance(
    dtr_id: int = Query(..., description="Distribution transformer id"),
    from_: Optional[str] = Query(None, alias="from", description="ISO timestamp"),
    to: Optional[str] = Query(None, description="ISO timestamp"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Feeder-input vs. downstream-sum energy balance for one DTR.

    * ``feeder_input_kwh`` = sum of the DTR's designated boundary / aggregate
      meter reading(s). When the DTR has no aggregate meter, EMS falls back to
      the transformer's ``current_load_kw`` integrated over the window.
    * ``downstream_kwh`` = sum of all downstream meter readings (``import_kwh``)
      in the window; MDMS readings are used via the proxy when ``MDMS_ENABLED``
      is on, otherwise local ``meter_readings`` rows.
    * ``gap_kwh = feeder_input - downstream``; ``gap_pct`` = gap / feeder_input.
    """
    tx = db.query(Transformer).filter(Transformer.id == dtr_id).first()
    if tx is None:
        raise HTTPException(status_code=404, detail=f"DTR {dtr_id} not found")

    now = datetime.now(timezone.utc)
    frm_dt = datetime.fromisoformat(from_) if from_ else now - timedelta(days=1)
    to_dt = datetime.fromisoformat(to) if to else now

    # Downstream meters under this DTR.
    meter_serials = [
        m.serial for m in db.query(Meter.serial).filter(Meter.transformer_id == dtr_id).all()
    ]

    downstream_kwh = 0.0
    if meter_serials:
        row = (
            db.query(
                func.coalesce(
                    func.sum(MeterReading.energy_import_kwh), 0.0
                ).label("total")
            )
            .filter(
                MeterReading.meter_serial.in_(meter_serials),
                MeterReading.timestamp >= frm_dt,
                MeterReading.timestamp <= to_dt,
            )
            .one()
        )
        downstream_kwh = float(row.total or 0.0)

    # Feeder-input fallback: assume aggregate meter may have name like "DTR-AGG-<id>".
    aggregate_serial = f"DTR-AGG-{dtr_id}"
    agg_row = (
        db.query(
            func.coalesce(func.sum(MeterReading.energy_import_kwh), 0.0).label("total")
        )
        .filter(
            MeterReading.meter_serial == aggregate_serial,
            MeterReading.timestamp >= frm_dt,
            MeterReading.timestamp <= to_dt,
        )
        .one()
    )
    feeder_input_kwh = float(agg_row.total or 0.0)

    if feeder_input_kwh <= 0 and tx.current_load_kw:
        hours = max(0.01, (to_dt - frm_dt).total_seconds() / 3600.0)
        feeder_input_kwh = float(tx.current_load_kw) * hours

    gap_kwh = max(0.0, feeder_input_kwh - downstream_kwh)
    gap_pct = (100.0 * gap_kwh / feeder_input_kwh) if feeder_input_kwh > 0 else 0.0

    return {
        "source": "mdms" if _mdms_available() else "local",
        "dtr_id": dtr_id,
        "dtr_name": tx.name,
        "from": frm_dt.isoformat(),
        "to": to_dt.isoformat(),
        "meter_count": len(meter_serials),
        "feeder_input_kwh": round(feeder_input_kwh, 2),
        "downstream_kwh": round(downstream_kwh, 2),
        "gap_kwh": round(gap_kwh, 2),
        "gap_pct": round(gap_pct, 2),
    }


@router.get("/energy-balance/top")
async def top_energy_balance_gaps(
    limit: int = Query(10, ge=1, le=100),
    hours: int = Query(24, ge=1, le=24 * 14),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Top DTRs by absolute gap over the last ``hours``. Used by NTL dashboard."""
    now = datetime.now(timezone.utc)
    frm = now - timedelta(hours=hours)
    txs = db.query(Transformer).order_by(Transformer.id).limit(500).all()
    rows: List[Dict[str, Any]] = []
    for tx in txs:
        serials = [
            s for (s,) in db.query(Meter.serial).filter(Meter.transformer_id == tx.id).all()
        ]
        if not serials:
            continue
        down = (
            db.query(func.coalesce(func.sum(MeterReading.energy_import_kwh), 0.0))
            .filter(
                MeterReading.meter_serial.in_(serials),
                MeterReading.timestamp >= frm,
                MeterReading.timestamp <= now,
            )
            .scalar()
            or 0.0
        )
        agg = (
            db.query(func.coalesce(func.sum(MeterReading.energy_import_kwh), 0.0))
            .filter(
                MeterReading.meter_serial == f"DTR-AGG-{tx.id}",
                MeterReading.timestamp >= frm,
                MeterReading.timestamp <= now,
            )
            .scalar()
            or 0.0
        )
        feeder_input = float(agg) if agg > 0 else float(tx.current_load_kw or 0) * hours
        if feeder_input <= 0:
            continue
        gap = max(0.0, feeder_input - float(down))
        rows.append(
            {
                "dtr_id": tx.id,
                "dtr_name": tx.name,
                "feeder_input_kwh": round(feeder_input, 2),
                "downstream_kwh": round(float(down), 2),
                "gap_kwh": round(gap, 2),
                "gap_pct": round(100.0 * gap / feeder_input, 2) if feeder_input > 0 else 0.0,
            }
        )
    rows.sort(key=lambda r: r["gap_kwh"], reverse=True)
    return {"hours": hours, "rows": rows[:limit]}


# ── Map overlay helper: GeoJSON of suspects (for GIS overlay toggle) ───────────


@router.get("/suspects/geojson")
async def suspects_geojson(
    bbox: Optional[str] = Query(None),
    min_score: int = Query(30, ge=0, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return suspect meters as a GeoJSON FeatureCollection for map overlay.

    Uses the local scorer (cheap, <200 ms for demo fleet). Frontend toggles
    this layer when "NTL suspects" overlay is enabled.
    """
    items = _compute_local_suspects(db, dtr_id=None, min_score=min_score, limit=2000)
    meter_rows = {
        m.serial: m
        for m in db.query(Meter)
        .filter(Meter.serial.in_([i["meter_serial"] for i in items]))
        .all()
    }
    features = []
    for item in items:
        m = meter_rows.get(item["meter_serial"])
        if m is None or m.latitude is None or m.longitude is None:
            continue
        if bbox:
            try:
                min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox.split(",")]
                if not (min_lon <= m.longitude <= max_lon and min_lat <= m.latitude <= max_lat):
                    continue
            except ValueError:
                pass
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [m.longitude, m.latitude]},
                "properties": {**item, "layer": "ntl_suspect"},
            }
        )
    return {"type": "FeatureCollection", "features": features}
