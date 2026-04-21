"""Read-only connector for MDMS `validation_rules` postgres.

The validation_rules DB is authoritative for metrology SLA — the
`data_availability` table tracks how many records per (meter_type, profile,
timestamp) came in valid vs. invalid vs. estimated. Those rows drive the
SLA KPIs shown on the dashboard (Blockload / Daily Load / Billing Profile).

Connection is configured via :attr:`Settings.MDMS_VALIDATION_DB_URL`. When
the URL is unset or the remote is unreachable the functions return empty
results so the UI degrades gracefully rather than 500ing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings

log = logging.getLogger(__name__)

_engine: Optional[Engine] = None

# profile_types.profile_type → canonical dashboard label. Keys must match the
# strings stored in `validation_rules.profile_types`.
PROFILE_LABELS = {
    "BLOCKLOAD": "Blockload",
    "DAILYLOAD": "Daily Load",
    "MONTHLY_BILLING": "Billing Profile",
    "PROFILE_INSTANT": "Instant Profile",
    "PULL_EVENTS": "Pull Events",
}


@dataclass
class ProfileSla:
    profile_type: str          # raw enum from profile_types (e.g. "BLOCKLOAD")
    label: str                 # display label (e.g. "Blockload")
    valid: int
    invalid: int
    estimated: int
    expected: int              # valid + invalid + estimated
    received: int              # valid (strict) — what passed VEE
    sla_pct: Optional[float]   # 100 * received / expected, None if expected == 0


def _get_engine() -> Optional[Engine]:
    global _engine
    if _engine is not None:
        return _engine
    url = getattr(settings, "MDMS_VALIDATION_DB_URL", None)
    if not url:
        log.info("MDMS_VALIDATION_DB_URL not set — SLA KPI lookups disabled")
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
        log.warning("Failed to build MDMS validation engine: %s", exc)
        _engine = None
    return _engine


def profile_sla(
    *,
    period_start: datetime,
    period_end: Optional[datetime] = None,
) -> List[ProfileSla]:
    """Aggregated SLA per profile_type over the given window.

    Window is half-open: ``data_timestamp >= period_start``, and when
    ``period_end`` is given, ``data_timestamp < period_end``.
    """
    engine = _get_engine()
    if engine is None:
        return []

    params: dict = {"start": period_start}
    where = "WHERE da.data_timestamp >= :start"
    if period_end is not None:
        where += " AND da.data_timestamp < :end"
        params["end"] = period_end

    sql = text(
        f"""
        SELECT pt.profile_type,
               COALESCE(SUM(da.valid_records), 0)     AS valid,
               COALESCE(SUM(da.invalid_records), 0)   AS invalid,
               COALESCE(SUM(da.estimated_records), 0) AS estimated
          FROM data_availability da
          JOIN profile_types pt ON pt.id = da.profile_id
         {where}
         GROUP BY pt.profile_type
         ORDER BY pt.profile_type
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        log.warning("MDMS validation profile_sla failed: %s", exc)
        return []

    out: List[ProfileSla] = []
    for r in rows:
        m = r._mapping
        valid = int(m["valid"] or 0)
        invalid = int(m["invalid"] or 0)
        estimated = int(m["estimated"] or 0)
        expected = valid + invalid + estimated
        pct = round(100.0 * valid / expected, 2) if expected else None
        ptype = str(m["profile_type"])
        out.append(
            ProfileSla(
                profile_type=ptype,
                label=PROFILE_LABELS.get(ptype, ptype.replace("_", " ").title()),
                valid=valid,
                invalid=invalid,
                estimated=estimated,
                expected=expected,
                received=valid,
                sla_pct=pct,
            )
        )
    return out


def month_to_date_sla(now: Optional[datetime] = None) -> List[ProfileSla]:
    """SLA aggregated from the first of the current month (UTC) to now."""
    now = now or datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return profile_sla(period_start=start, period_end=now)


__all__ = ["ProfileSla", "PROFILE_LABELS", "profile_sla", "month_to_date_sla"]
