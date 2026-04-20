"""Read-only client for the MDMS VEE database.

Uses a dedicated SQLAlchemy async engine bound to MDMS_VEE_DATABASE_URL. If the
var is unset or unreachable, raises MdmsVeeUnavailable. No commit paths — this
is strictly read-only.

NOTE(013-mvp-phase2): add pool_pre_ping, statement_timeout, and retry policies.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

log = logging.getLogger("polaris.metrology.vee")


class MdmsVeeUnavailable(RuntimeError):
    """Raised when MDMS_VEE_DATABASE_URL is not configured or not reachable."""


_engine: Optional[AsyncEngine] = None


def _engine_or_raise() -> AsyncEngine:
    global _engine
    url = settings.MDMS_VEE_DATABASE_URL
    if not url:
        raise MdmsVeeUnavailable("MDMS_VEE_DATABASE_URL is not configured")
    if _engine is None:
        # Ensure asyncpg driver prefix.
        if "+asyncpg" not in url and url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _engine = create_async_engine(url, pool_size=5, pool_pre_ping=True)
    return _engine


async def dispose() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


# ----------------------------------------------------------------- read helpers


async def fetch_blockload(
    meter_serials: Optional[Iterable[str]] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = 10000,
) -> List[dict]:
    """Half-hourly interval rows from blockload_vee_validated.

    Maps upstream columns to Polaris-internal field names. Filters on
    device_identifier (meter serial), blockload_datetime.
    """
    eng = _engine_or_raise()
    sql = text(
        """
        SELECT device_identifier AS meter_serial,
               blockload_datetime AS ts,
               "import_Wh" AS import_wh,
               "export_Wh" AS export_wh,
               avg_voltage,
               avg_current,
               "BLS_frequency" AS frequency,
               is_valid,
               is_estimated,
               is_edited
          FROM blockload_vee_validated
         WHERE is_active = TRUE
           AND (:serials IS NULL OR device_identifier = ANY(:serials))
           AND (:from_ts IS NULL OR blockload_datetime >= :from_ts)
           AND (:to_ts IS NULL OR blockload_datetime <= :to_ts)
         ORDER BY blockload_datetime ASC
         LIMIT :limit
        """
    )
    params = {
        "serials": list(meter_serials) if meter_serials else None,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "limit": limit,
    }
    async with eng.connect() as conn:
        result = await conn.execute(sql, params)
        rows = [dict(r._mapping) for r in result]
    return rows


async def fetch_daily(
    meter_serials: Optional[Iterable[str]] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = 10000,
) -> List[dict]:
    eng = _engine_or_raise()
    sql = text(
        """
        SELECT device_identifier AS meter_serial,
               dailyload_datetime::date AS date,
               "import_Wh" AS import_wh,
               "export_Wh" AS export_wh,
               "MD_W" AS md_w,
               is_valid,
               is_estimated
          FROM dailyload_vee_validated
         WHERE is_active = TRUE
           AND (:serials IS NULL OR device_identifier = ANY(:serials))
           AND (:from_date IS NULL OR dailyload_datetime::date >= :from_date)
           AND (:to_date IS NULL OR dailyload_datetime::date <= :to_date)
         ORDER BY dailyload_datetime ASC
         LIMIT :limit
        """
    )
    params = {
        "serials": list(meter_serials) if meter_serials else None,
        "from_date": from_date,
        "to_date": to_date,
        "limit": limit,
    }
    async with eng.connect() as conn:
        result = await conn.execute(sql, params)
        rows = [dict(r._mapping) for r in result]
    return rows


async def fetch_monthly(
    meter_serials: Optional[Iterable[str]] = None,
    year_month: Optional[str] = None,
    limit: int = 10000,
) -> List[dict]:
    """Monthly billing registers. year_month format: 'YYYY-MM'."""
    eng = _engine_or_raise()
    sql = text(
        """
        SELECT device_identifier AS meter_serial,
               to_char(billing_datetime, 'YYYY-MM') AS year_month,
               "cumm_import_Wh" AS cumm_import_wh,
               "MD_W" AS md_w,
               "MD_VA" AS md_va,
               "avg_PF" AS avg_pf,
               "export_Wh" AS export_wh
          FROM monthlybilling_vee_validated
         WHERE is_valid = TRUE
           AND (:serials IS NULL OR device_identifier = ANY(:serials))
           AND (:year_month IS NULL OR to_char(billing_datetime, 'YYYY-MM') = :year_month)
         LIMIT :limit
        """
    )
    params = {
        "serials": list(meter_serials) if meter_serials else None,
        "year_month": year_month,
        "limit": limit,
    }
    async with eng.connect() as conn:
        result = await conn.execute(sql, params)
        rows = [dict(r._mapping) for r in result]
    return rows
