"""Read-only connector for MDMS db_cis.consumer_master_data.

The CIS database is authoritative for consumer identity (account, name,
contact, meter serial, feeder/DTR). EMS treats it as read-only; a local
``consumer_tag`` table adds the "critical customer" classification that
drives the default virtual-object-groups.

Connection is configured via :attr:`Settings.MDMS_CIS_DB_URL`. When the
URL is unset or the remote is unreachable the functions return ``[]`` so
the UI degrades to showing only locally-tagged consumers rather than 500.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings

log = logging.getLogger(__name__)

# Lazy-initialised singleton engine so we don't pay the connect cost per call.
_engine: Optional[Engine] = None


@dataclass
class CisConsumer:
    account_id: str
    consumer_name: str
    meter_serial: str
    mobile_number: Optional[str]
    email: Optional[str]
    supply_type: Optional[str]
    meter_category: Optional[str]
    feeder_code: Optional[str]
    feeder_name: Optional[str]
    dtr_code: Optional[str]
    dtr_name: Optional[str]
    substation_code: Optional[str]
    substation_name: Optional[str]
    is_vip: bool
    consumer_type: Optional[str]


def _get_engine() -> Optional[Engine]:
    global _engine
    if _engine is not None:
        return _engine
    url = getattr(settings, "MDMS_CIS_DB_URL", None)
    if not url:
        log.info("MDMS_CIS_DB_URL is not set — CIS consumer lookups disabled")
        return None
    try:
        _engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
    except Exception as exc:  # pragma: no cover
        log.warning("Failed to build MDMS CIS engine: %s", exc)
        _engine = None
    return _engine


_SELECT_COLS = """
    "accountId"        AS account_id,
    "consumerName"     AS consumer_name,
    "meterSrno"        AS meter_serial,
    "mobileNumber"     AS mobile_number,
    "email"            AS email,
    "supplyTypecode"   AS supply_type,
    "meterCategory"    AS meter_category,
    "feederCode"       AS feeder_code,
    "feederName"       AS feeder_name,
    "dtrCode"          AS dtr_code,
    "dtrName"          AS dtr_name,
    "substaionCode"    AS substation_code,
    "substationName"   AS substation_name,
    COALESCE(is_vip, false) AS is_vip,
    "consumerType"     AS consumer_type
"""


def _row_to_consumer(row) -> CisConsumer:
    m = row._mapping
    mobile = m.get("mobile_number")
    return CisConsumer(
        account_id=str(m.get("account_id") or ""),
        consumer_name=str(m.get("consumer_name") or ""),
        meter_serial=str(m.get("meter_serial") or ""),
        mobile_number=str(mobile) if mobile is not None else None,
        email=m.get("email"),
        supply_type=m.get("supply_type"),
        meter_category=m.get("meter_category"),
        feeder_code=m.get("feeder_code"),
        feeder_name=m.get("feeder_name"),
        dtr_code=m.get("dtr_code"),
        dtr_name=m.get("dtr_name"),
        substation_code=m.get("substation_code"),
        substation_name=m.get("substation_name"),
        is_vip=bool(m.get("is_vip") or False),
        consumer_type=m.get("consumer_type"),
    )


def list_consumers(
    *,
    limit: int = 500,
    offset: int = 0,
    feeder_code: Optional[str] = None,
    dtr_code: Optional[str] = None,
    search: Optional[str] = None,
    meter_serials: Optional[List[str]] = None,
) -> List[CisConsumer]:
    """Return consumers from MDMS CIS with optional filters.

    Returns ``[]`` when the CIS DB is not configured or unreachable.
    """
    engine = _get_engine()
    if engine is None:
        return []

    where: List[str] = []
    params: dict = {"limit": int(limit), "offset": int(offset)}
    if feeder_code:
        where.append('"feederCode" = :feeder_code OR "feederName" = :feeder_code')
        params["feeder_code"] = feeder_code
    if dtr_code:
        where.append('"dtrCode" = :dtr_code OR "dtrName" = :dtr_code')
        params["dtr_code"] = dtr_code
    if search:
        where.append(
            '("consumerName" ILIKE :q OR "accountId" ILIKE :q OR "meterSrno" ILIKE :q)'
        )
        params["q"] = f"%{search}%"
    if meter_serials:
        where.append('"meterSrno" = ANY(:serials)')
        params["serials"] = list(meter_serials)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = text(
        f'SELECT {_SELECT_COLS} '
        'FROM consumer_master_data '
        f'{where_sql} '
        'ORDER BY "accountId" '
        'LIMIT :limit OFFSET :offset'
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_consumer(r) for r in rows]
    except Exception as exc:
        log.warning("MDMS CIS list_consumers failed: %s", exc)
        return []


def count_consumers(
    *,
    feeder_code: Optional[str] = None,
    dtr_code: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    engine = _get_engine()
    if engine is None:
        return 0
    where: List[str] = []
    params: dict = {}
    if feeder_code:
        where.append('"feederCode" = :feeder_code OR "feederName" = :feeder_code')
        params["feeder_code"] = feeder_code
    if dtr_code:
        where.append('"dtrCode" = :dtr_code OR "dtrName" = :dtr_code')
        params["dtr_code"] = dtr_code
    if search:
        where.append(
            '("consumerName" ILIKE :q OR "accountId" ILIKE :q OR "meterSrno" ILIKE :q)'
        )
        params["q"] = f"%{search}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = text(f'SELECT COUNT(*) FROM consumer_master_data {where_sql}')
    try:
        with engine.connect() as conn:
            return int(conn.execute(sql, params).scalar_one())
    except Exception as exc:
        log.warning("MDMS CIS count_consumers failed: %s", exc)
        return 0


def list_feeders() -> List[dict]:
    engine = _get_engine()
    if engine is None:
        return []
    sql = text(
        'SELECT DISTINCT "feederCode" AS code, "feederName" AS name '
        'FROM consumer_master_data '
        'WHERE "feederCode" IS NOT NULL '
        'ORDER BY 1'
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [{"code": r._mapping["code"], "name": r._mapping["name"]} for r in rows]
    except Exception as exc:
        log.warning("MDMS CIS list_feeders failed: %s", exc)
        return []


__all__ = [
    "CisConsumer",
    "list_consumers",
    "count_consumers",
    "list_feeders",
]
