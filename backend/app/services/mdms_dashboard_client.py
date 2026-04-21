"""Read-only connectors that power the MDMS-backed dashboard widgets.

The dashboard (frontend ``Dashboard.jsx``) used to pull meter counts,
comm status, alarm totals and load profile from EMS-local tables / SSOT
proxies. Per product direction the source of truth moved to MDMS: the
CIS postgres for the asset population, the validation_rules postgres for
metrology / VEE-validated blockload, and the gp_hes postgres for push
events (alarms).

This module owns the three engines and exposes one focused helper per
widget. Each helper degrades to an empty / None result when its DSN is
unset or the remote is unreachable — the endpoint layer uses that to
flag upstream health without 500ing the dashboard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings

log = logging.getLogger(__name__)

_engines: Dict[str, Optional[Engine]] = {}

# Push-event `index` values that represent tamper / intrusion conditions.
# Sourced from the DLMS event catalogue used by the meters feeding gp_hes
# (magnet, cover open, load disconnect, earth loading, over-current). Kept
# local so we don't take a runtime dep on an MDMS lookup table.
TAMPER_EVENT_INDEXES = (11, 51, 81, 82, 83, 84)


def _get_engine(dsn_attr: str) -> Optional[Engine]:
    if dsn_attr in _engines:
        return _engines[dsn_attr]
    url = getattr(settings, dsn_attr, None)
    if not url:
        log.info("%s not set — MDMS dashboard feature disabled for this source", dsn_attr)
        _engines[dsn_attr] = None
        return None
    try:
        _engines[dsn_attr] = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
    except Exception as exc:  # pragma: no cover
        log.warning("Failed to build engine for %s: %s", dsn_attr, exc)
        _engines[dsn_attr] = None
    return _engines[dsn_attr]


# ── Fleet counts (db_cis) ────────────────────────────────────────────


@dataclass
class FleetCounts:
    meters: int          # consumer_master_data row count (non-null meterSrno)
    dtrs: int            # system_meters_master where meter_category='DTR'
    feeders: int         # system_meters_master where meter_category='Feeder'


def fleet_counts() -> FleetCounts:
    engine = _get_engine("MDMS_CIS_DB_URL")
    if engine is None:
        return FleetCounts(0, 0, 0)
    try:
        with engine.connect() as conn:
            meters = int(conn.execute(text(
                'SELECT COUNT(*) FROM consumer_master_data WHERE "meterSrno" IS NOT NULL'
            )).scalar_one())
            dtrs = int(conn.execute(text(
                "SELECT COUNT(*) FROM system_meters_master WHERE meter_category='DTR'"
            )).scalar_one())
            feeders = int(conn.execute(text(
                "SELECT COUNT(*) FROM system_meters_master WHERE meter_category='Feeder'"
            )).scalar_one())
        return FleetCounts(meters=meters, dtrs=dtrs, feeders=feeders)
    except Exception as exc:
        log.warning("MDMS fleet_counts failed: %s", exc)
        return FleetCounts(0, 0, 0)


# ── Comm status (validation_rules.blockload_vee_validated) ──────────


@dataclass
class CommStatus:
    online_meters: int           # distinct meters that reported blockload in window
    offline_meters: int          # total - online
    total_meters: int
    comm_success_rate: Optional[float]  # online / total * 100


def comm_status(hours: int = 24, total_meters: Optional[int] = None) -> CommStatus:
    engine = _get_engine("MDMS_VALIDATION_DB_URL")
    total = total_meters if total_meters is not None else fleet_counts().meters
    if engine is None:
        return CommStatus(0, total, total, None)
    try:
        with engine.connect() as conn:
            online = int(conn.execute(
                text(
                    "SELECT COUNT(DISTINCT meter_number) FROM blockload_vee_validated "
                    "WHERE data_timestamp >= :since"
                ),
                {"since": datetime.now(timezone.utc) - timedelta(hours=hours)},
            ).scalar_one())
    except Exception as exc:
        log.warning("MDMS comm_status failed: %s", exc)
        return CommStatus(0, total, total, None)
    online = min(online, total) if total else online
    offline = max(total - online, 0) if total else 0
    rate = round(100.0 * online / total, 2) if total else None
    return CommStatus(online_meters=online, offline_meters=offline,
                      total_meters=total, comm_success_rate=rate)


# ── Alarms (gp_hes.mdm_pushevent) ───────────────────────────────────


@dataclass
class AlarmRow:
    meter_id: str
    data_timestamp: datetime
    messages: List[str]
    indexes: List[int]
    is_tamper: bool


@dataclass
class AlarmSummary:
    active_count: int
    tamper_count: int        # distinct meters with a tamper-index event in window
    recent: List[AlarmRow]


def _parse_events(raw) -> Tuple[List[str], List[int]]:
    """Extract (messages, indexes) from a pushevent ``event_message`` JSONB."""
    msgs: List[str] = []
    idxs: List[int] = []
    if not raw:
        return msgs, idxs
    # asyncpg/psycopg2 return JSONB as Python dict/list already.
    items = raw if isinstance(raw, list) else [raw]
    for it in items:
        if not isinstance(it, dict):
            continue
        msg = it.get("message")
        idx = it.get("index")
        if msg is not None:
            msgs.append(str(msg))
        if idx is not None:
            try:
                idxs.append(int(idx))
            except (TypeError, ValueError):
                pass
    return msgs, idxs


def alarms(hours: int = 24, limit: int = 25) -> AlarmSummary:
    engine = _get_engine("MDMS_HES_DB_URL")
    if engine is None:
        return AlarmSummary(0, 0, [])
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT meter_id, data_timestamp, event_message "
                    "FROM mdm_pushevent "
                    "WHERE data_timestamp >= :since AND data_timestamp < now() "
                    "ORDER BY data_timestamp DESC LIMIT :limit"
                ),
                {"since": since, "limit": limit},
            ).fetchall()
            total = int(conn.execute(
                text(
                    "SELECT COUNT(*) FROM mdm_pushevent "
                    "WHERE data_timestamp >= :since AND data_timestamp < now()"
                ),
                {"since": since},
            ).scalar_one())
    except Exception as exc:
        log.warning("MDMS alarms query failed: %s", exc)
        return AlarmSummary(0, 0, [])

    recent: List[AlarmRow] = []
    tamper_meters: set = set()
    tamper_set = set(TAMPER_EVENT_INDEXES)
    for r in rows:
        m = r._mapping
        msgs, idxs = _parse_events(m["event_message"])
        is_tamper = any(i in tamper_set for i in idxs)
        if is_tamper:
            tamper_meters.add(str(m["meter_id"]))
        recent.append(
            AlarmRow(
                meter_id=str(m["meter_id"] or ""),
                data_timestamp=m["data_timestamp"],
                messages=msgs,
                indexes=idxs,
                is_tamper=is_tamper,
            )
        )

    # Fast tamper count across the full window (not just the top `limit`).
    try:
        with engine.connect() as conn:
            tamper_rows = conn.execute(
                text(
                    "SELECT DISTINCT meter_id, event_message FROM mdm_pushevent "
                    "WHERE data_timestamp >= :since AND data_timestamp < now()"
                ),
                {"since": since},
            ).fetchall()
        for r in tamper_rows:
            _, idxs = _parse_events(r._mapping["event_message"])
            if any(i in tamper_set for i in idxs):
                tamper_meters.add(str(r._mapping["meter_id"] or ""))
    except Exception as exc:
        log.warning("MDMS alarms tamper scan failed: %s", exc)

    return AlarmSummary(active_count=total, tamper_count=len(tamper_meters), recent=recent)


# ── Network load profile (validation_rules.blockload_vee_validated) ─


@dataclass
class LoadPoint:
    ts: datetime
    total_kw: float


def network_load_hourly(hours: int = 24) -> List[LoadPoint]:
    engine = _get_engine("MDMS_VALIDATION_DB_URL")
    if engine is None:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    'SELECT date_trunc(\'hour\', data_timestamp) AS h, '
                    'SUM("import_Wh") / 1000.0 AS kwh '
                    'FROM blockload_vee_validated '
                    'WHERE data_timestamp >= :since '
                    'GROUP BY 1 ORDER BY 1'
                ),
                {"since": since},
            ).fetchall()
    except Exception as exc:
        log.warning("MDMS network_load_hourly failed: %s", exc)
        return []
    # Each hour's total import_Wh / 1000 is the total energy (kWh) consumed
    # across the fleet; the average load (kW) for that hour equals kWh/1h.
    return [LoadPoint(ts=r._mapping["h"], total_kw=float(r._mapping["kwh"] or 0.0))
            for r in rows]


__all__ = [
    "FleetCounts",
    "CommStatus",
    "AlarmRow",
    "AlarmSummary",
    "LoadPoint",
    "fleet_counts",
    "comm_status",
    "alarms",
    "network_load_hourly",
    "TAMPER_EVENT_INDEXES",
]
