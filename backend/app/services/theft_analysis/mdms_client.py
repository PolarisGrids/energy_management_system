"""Read-only data fetchers for theft analysis against MDMS validation_rules.

All functions return plain dataclasses / dicts — no ORM — because this DB is
owned by the MDMS team and we only ever read from it. We reuse the engine
built in :mod:`app.services.mdms_validation_client` so both SLA and theft
lookups share a single pool.

When the MDMS DSN is unset or the remote is unreachable every function
returns an empty result rather than raising — callers stay green while the
UI degrades gracefully.

Column case: several MDMS columns are *mixed-case quoted* identifiers
(``"import_Wh"``, ``"Rphase_BLS_current"`` …). Every query double-quotes
them; do not lowercase.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text

from app.services.mdms_validation_client import _get_engine

log = logging.getLogger(__name__)


# --- meter prefixes we treat as "consumer" meters (theft subjects) ---
# DTR/feeder meters (DTM-*, FDR-*) are excluded — they participate in
# energy-balance rather than being theft candidates.
CONSUMER_PREFIXES = ("MTR", "PO", "PPD")

# Tamper-related DLMS event codes emitted by the simulator. Kept aligned
# with src/scenarios/theft.py in the simulator repo.
TAMPER_EVENT_CODES: Dict[int, str] = {
    201: "magnetic_tamper_occurred",
    202: "magnetic_tamper_restored",
    203: "neutral_disturbance_occurred",
    204: "neutral_disturbance_restored",
    205: "low_pf_occurred",
    206: "low_pf_restored",
    251: "cover_opened",
    2018: "time_tampering",
}


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────

@dataclass
class MeterRoster:
    device_identifier: str
    meter_type: Optional[str]           # 1-Phase / 3-Phase / LTCT / HTCT / None
    manufacturer: Optional[str]
    installation_date: Optional[datetime]
    sanctioned_load: Optional[float]    # kW (from CIS)
    multiplying_factor: Optional[float]
    connection_status: Optional[str]
    net_meter_flag: Optional[str]
    supply_type_code: Optional[str]
    account_id: Optional[str]


@dataclass
class HHReading:
    device_identifier: str
    ts: datetime
    import_wh: Optional[float]
    export_wh: Optional[float]
    import_vah: Optional[float]
    export_vah: Optional[float]
    avg_current: Optional[float]
    avg_voltage: Optional[float]
    i_r: Optional[float]
    i_y: Optional[float]
    i_b: Optional[float]
    v_rn: Optional[float]
    v_yn: Optional[float]
    v_bn: Optional[float]


@dataclass
class DailyReading:
    device_identifier: str
    ts: datetime
    import_wh: Optional[float]
    export_wh: Optional[float]
    md_w: Optional[float]
    md_va: Optional[float]
    md_w_at: Optional[datetime]


@dataclass
class TamperEvent:
    device_identifier: str
    event_code: int
    event_label: str
    event_source: str                   # 'pull' | 'push'
    event_ts: datetime
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceAnomaly:
    device_identifier: str
    detected_at: datetime
    error_message: Optional[str]


# ──────────────────────────────────────────────────────────────────────
# Fetchers
# ──────────────────────────────────────────────────────────────────────

def fetch_meter_roster(
    *,
    consumer_only: bool = True,
) -> List[MeterRoster]:
    """All meters with joined CIS metadata.

    When ``consumer_only`` (default), DTR/feeder meters are filtered out so
    the detectors only score meters that could actually commit NTL.
    """
    engine = _get_engine()
    if engine is None:
        return []

    where = ""
    if consumer_only:
        prefixes = " OR ".join(
            f"di.device_identifier LIKE '{p}%'" for p in CONSUMER_PREFIXES
        )
        where = f"WHERE {prefixes}"

    sql = text(
        f"""
        SELECT
            di.device_identifier,
            di.meter_type,
            mf.manufacturer_name                    AS manufacturer_name_di,
            cm.manufacturer_name                    AS manufacturer_name_cm,
            di.installation_date,
            cm.sanctioned_load,
            cm.multiplying_factor,
            cm.connection_status,
            cm.net_meter_flag,
            cm.supply_type_code,
            cm.account_id
          FROM device_info di
          LEFT JOIN cis_meter_data cm
                 ON cm.device_identifier = di.device_identifier
          LEFT JOIN manufacturers mf
                 ON mf.id = di.manufacturer_id
         {where}
         ORDER BY di.device_identifier
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
    except Exception as exc:
        log.warning("fetch_meter_roster failed: %s", exc)
        return []

    out: List[MeterRoster] = []
    for r in rows:
        m = r._mapping
        out.append(
            MeterRoster(
                device_identifier=str(m["device_identifier"]),
                meter_type=m["meter_type"],
                manufacturer=m["manufacturer_name_di"] or m["manufacturer_name_cm"],
                installation_date=m["installation_date"],
                sanctioned_load=_as_float(m["sanctioned_load"]),
                multiplying_factor=_as_float(m["multiplying_factor"]),
                connection_status=m["connection_status"],
                net_meter_flag=m["net_meter_flag"],
                supply_type_code=m["supply_type_code"],
                account_id=m["account_id"],
            )
        )
    return out


def fetch_hh_window(
    *,
    period_start: datetime,
    period_end: datetime,
    device_identifiers: Optional[Sequence[str]] = None,
) -> List[HHReading]:
    """Half-hourly blockload readings for all / listed consumer meters."""
    engine = _get_engine()
    if engine is None:
        return []

    params: Dict[str, Any] = {"start": period_start, "end": period_end}
    where_ids = ""
    if device_identifiers:
        params["ids"] = tuple(device_identifiers)
        where_ids = "AND bl.device_identifier IN :ids"

    sql = text(
        f"""
        SELECT
            bl.device_identifier,
            bl.blockload_datetime                     AS ts,
            bl."import_Wh"                            AS import_wh,
            bl."export_Wh"                            AS export_wh,
            bl."import_VAh"                           AS import_vah,
            bl."export_VAh"                           AS export_vah,
            bl.avg_current,
            bl.avg_voltage,
            bl."Rphase_BLS_current"                   AS i_r,
            bl."Yphase_BLS_current"                   AS i_y,
            bl."Bphase_BLS_current"                   AS i_b,
            bl."RN_BLS_voltage"                       AS v_rn,
            bl."YN_BLS_voltage"                       AS v_yn,
            bl."BN_BLS_voltage"                       AS v_bn
          FROM blockload_vee_validated bl
         WHERE bl.blockload_datetime >= :start
           AND bl.blockload_datetime <  :end
           {where_ids}
         ORDER BY bl.device_identifier, bl.blockload_datetime
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        log.warning("fetch_hh_window failed: %s", exc)
        return []

    out: List[HHReading] = []
    for r in rows:
        m = r._mapping
        out.append(
            HHReading(
                device_identifier=str(m["device_identifier"]),
                ts=m["ts"],
                import_wh=_as_float(m["import_wh"]),
                export_wh=_as_float(m["export_wh"]),
                import_vah=_as_float(m["import_vah"]),
                export_vah=_as_float(m["export_vah"]),
                avg_current=_as_float(m["avg_current"]),
                avg_voltage=_as_float(m["avg_voltage"]),
                i_r=_as_float(m["i_r"]),
                i_y=_as_float(m["i_y"]),
                i_b=_as_float(m["i_b"]),
                v_rn=_as_float(m["v_rn"]),
                v_yn=_as_float(m["v_yn"]),
                v_bn=_as_float(m["v_bn"]),
            )
        )
    return out


def fetch_daily_window(
    *,
    period_start: datetime,
    period_end: datetime,
    device_identifiers: Optional[Sequence[str]] = None,
) -> List[DailyReading]:
    """Daily load readings incl. max-demand."""
    engine = _get_engine()
    if engine is None:
        return []

    params: Dict[str, Any] = {"start": period_start, "end": period_end}
    where_ids = ""
    if device_identifiers:
        params["ids"] = tuple(device_identifiers)
        where_ids = "AND dl.device_identifier IN :ids"

    sql = text(
        f"""
        SELECT
            dl.device_identifier,
            dl.dailyload_datetime          AS ts,
            dl."import_Wh"                 AS import_wh,
            dl."export_Wh"                 AS export_wh,
            dl."MD_W"                      AS md_w,
            dl."MD_VA"                     AS md_va,
            dl."MD_W_datetime"             AS md_w_at
          FROM dailyload_vee_validated dl
         WHERE dl.dailyload_datetime >= :start
           AND dl.dailyload_datetime <  :end
           {where_ids}
         ORDER BY dl.device_identifier, dl.dailyload_datetime
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        log.warning("fetch_daily_window failed: %s", exc)
        return []

    out: List[DailyReading] = []
    for r in rows:
        m = r._mapping
        out.append(
            DailyReading(
                device_identifier=str(m["device_identifier"]),
                ts=m["ts"],
                import_wh=_as_float(m["import_wh"]),
                export_wh=_as_float(m["export_wh"]),
                md_w=_as_float(m["md_w"]),
                md_va=_as_float(m["md_va"]),
                md_w_at=m["md_w_at"],
            )
        )
    return out


def fetch_tamper_events(
    *,
    period_start: datetime,
    period_end: datetime,
    device_identifiers: Optional[Sequence[str]] = None,
    codes: Optional[Iterable[int]] = None,
) -> List[TamperEvent]:
    """Pull + push tamper-relevant events within the window.

    ``push_events_vee`` doesn't expose a numeric event_code column — the
    signal lives in ``event_bits`` (the bitstring decoded upstream). For
    push rows we pattern-match the bitstring against the DLMS codes we
    care about.
    """
    engine = _get_engine()
    if engine is None:
        return []

    wanted_codes = list(codes or TAMPER_EVENT_CODES.keys())
    params: Dict[str, Any] = {
        "start": period_start,
        "end": period_end,
        "codes": tuple(wanted_codes),
    }
    pull_where_ids = ""
    push_where_ids = ""
    if device_identifiers:
        params["ids"] = tuple(device_identifiers)
        pull_where_ids = "AND pe.device_identifier IN :ids"
        push_where_ids = "AND ps.device_identifier IN :ids"

    pull_sql = text(
        f"""
        SELECT
            pe.device_identifier,
            pe.event_code,
            pe."Date_and_time_of_event" AS event_ts,
            pe.event_type,
            pe.event_message
          FROM pull_events_vee pe
         WHERE pe.event_code IN :codes
           AND COALESCE(pe."Date_and_time_of_event", pe.created_at) >= :start
           AND COALESCE(pe."Date_and_time_of_event", pe.created_at) <  :end
           {pull_where_ids}
        """
    )
    push_sql = text(
        f"""
        SELECT
            ps.device_identifier,
            ps.event_bits,
            ps.data_timestamp           AS event_ts,
            ps.meter_time,
            ps.event_message
          FROM push_events_vee ps
         WHERE ps.data_timestamp >= :start
           AND ps.data_timestamp <  :end
           AND ps.event_bits ~ :bits_regex
           {push_where_ids}
        """
    )
    # event_bits is usually a numeric-ish string. Match any of the wanted codes.
    params["bits_regex"] = "^(" + "|".join(str(c) for c in wanted_codes) + ")$"

    out: List[TamperEvent] = []
    try:
        with engine.connect() as conn:
            for r in conn.execute(pull_sql, params).fetchall():
                m = r._mapping
                code = int(m["event_code"])
                out.append(
                    TamperEvent(
                        device_identifier=str(m["device_identifier"]),
                        event_code=code,
                        event_label=TAMPER_EVENT_CODES.get(code, f"code_{code}"),
                        event_source="pull",
                        event_ts=m["event_ts"],
                        raw={
                            "event_type": m["event_type"],
                            "event_message": m["event_message"],
                        },
                    )
                )
            for r in conn.execute(push_sql, params).fetchall():
                m = r._mapping
                try:
                    code = int(str(m["event_bits"]).strip())
                except (ValueError, TypeError):
                    continue
                out.append(
                    TamperEvent(
                        device_identifier=str(m["device_identifier"]),
                        event_code=code,
                        event_label=TAMPER_EVENT_CODES.get(code, f"code_{code}"),
                        event_source="push",
                        event_ts=m["event_ts"] or m["meter_time"],
                        raw={"event_message": m["event_message"]},
                    )
                )
    except Exception as exc:
        log.warning("fetch_tamper_events failed: %s", exc)
        return []

    out.sort(key=lambda e: (e.device_identifier, e.event_ts or datetime.min))
    return out


def fetch_device_anomalies(
    *,
    period_start: datetime,
    period_end: datetime,
    device_identifiers: Optional[Sequence[str]] = None,
) -> List[DeviceAnomaly]:
    engine = _get_engine()
    if engine is None:
        return []

    params: Dict[str, Any] = {"start": period_start, "end": period_end}
    where_ids = ""
    if device_identifiers:
        params["ids"] = tuple(device_identifiers)
        where_ids = "AND da.device_identifier IN :ids"

    sql = text(
        f"""
        SELECT da.device_identifier, da.anomaly_detected_at AS detected_at, da.error_message
          FROM device_anomalies da
         WHERE da.anomaly_detected_at >= :start
           AND da.anomaly_detected_at <  :end
           {where_ids}
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        log.warning("fetch_device_anomalies failed: %s", exc)
        return []

    return [
        DeviceAnomaly(
            device_identifier=str(r._mapping["device_identifier"]),
            detected_at=r._mapping["detected_at"],
            error_message=r._mapping["error_message"],
        )
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────

def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__ = [
    "CONSUMER_PREFIXES",
    "TAMPER_EVENT_CODES",
    "MeterRoster",
    "HHReading",
    "DailyReading",
    "TamperEvent",
    "DeviceAnomaly",
    "fetch_meter_roster",
    "fetch_hh_window",
    "fetch_daily_window",
    "fetch_tamper_events",
    "fetch_device_anomalies",
]
