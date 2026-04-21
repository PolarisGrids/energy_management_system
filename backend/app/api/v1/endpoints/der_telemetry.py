"""DER telemetry read endpoints (spec 018 W3.T11/T12).

Feeds the per-type native pages (`/der/pv`, `/der/bess`, `/der/ev`) and the
feeder-level DER aggregation view used by `DERManagement`.

Data source: `der_telemetry` (weekly partitioned, populated by the
`hesv2.der.telemetry` Kafka consumer — W2.T7). The `der_asset` table is the
join target for type filtering + feeder scoping.

Never synthesises values. When the Kafka stream hasn't populated the table,
the endpoint returns empty arrays and a `banner` string for the UI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.der_consumer import DERConsumer
from app.models.der_ems import DERAssetEMS
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response models ──


class DERTelemetryPoint(BaseModel):
    ts: str
    active_power_kw: Optional[float] = None
    reactive_power_kvar: Optional[float] = None
    soc_pct: Optional[float] = None
    session_energy_kwh: Optional[float] = None
    achievement_rate_pct: Optional[float] = None
    curtailment_pct: Optional[float] = None
    state: Optional[str] = None


class DERConsumerInline(BaseModel):
    """Lightweight consumer summary embedded in asset rows (W5)."""

    id: str
    name: str
    account_no: Optional[str] = None
    tariff_code: Optional[str] = None


class DERAssetLatest(BaseModel):
    id: str
    type: str
    type_code: Optional[str] = None  # W5 sub-type
    name: Optional[str] = None
    dtr_id: Optional[str] = None
    feeder_id: Optional[str] = None
    capacity_kw: Optional[float] = None
    capacity_kwh: Optional[float] = None
    consumer: Optional[DERConsumerInline] = None  # W5
    # Last-known telemetry fields (may be None when stream is silent)
    last_ts: Optional[str] = None
    current_output_kw: Optional[float] = None
    soc_pct: Optional[float] = None
    achievement_rate_pct: Optional[float] = None
    curtailment_pct: Optional[float] = None
    state: Optional[str] = None
    inverter_online: Optional[bool] = None
    session_energy_kwh: Optional[float] = None


class DERAggregatePoint(BaseModel):
    ts: str
    total_kw: float


class DERTelemetryResponse(BaseModel):
    type: Optional[str] = None
    window: str
    asset_id: Optional[str] = None
    assets: List[DERAssetLatest]
    aggregate: List[DERAggregatePoint]
    total_assets: Optional[int] = None  # W5 — pre-pagination count for UI paging
    banner: Optional[str] = None


class DERFeederAggregateBucket(BaseModel):
    ts: str
    pv_kw: float = 0.0
    bess_kw: float = 0.0
    ev_kw: float = 0.0
    microgrid_kw: float = 0.0
    total_kw: float = 0.0


class DERFeederAggregateResponse(BaseModel):
    feeder_id: str
    window: str
    buckets: List[DERFeederAggregateBucket]
    assets_by_type: dict
    banner: Optional[str] = None


# ── Helpers ──


_WINDOWS = {
    "1h": (timedelta(hours=1), 60),
    "24h": (timedelta(hours=24), 60),
    "7d": (timedelta(days=7), 15 * 60),
    # W5 — 30-day window for the long-trend chart on fleet + detail pages.
    # 1-hour buckets keep the response payload bounded (~720 points max).
    "30d": (timedelta(days=30), 60 * 60),
}


def _der_table_exists(db: Session) -> bool:
    try:
        bind = db.get_bind()
        return sa_inspect(bind).has_table("der_telemetry")
    except Exception:
        return False


def _bucket_expr(bucket_seconds: int) -> str:
    """SQL expression that rounds `ts` down to the start of a bucket.

    Works on PostgreSQL (to_timestamp(floor(epoch/n)*n)) and SQLite (strftime).
    The der_telemetry partitioned table is Postgres-only in prod, but the
    SQLite branch keeps unit tests green.
    """
    return (
        "to_timestamp(floor(extract(epoch FROM ts) / :bucket_s) * :bucket_s) "
        "AT TIME ZONE 'UTC'"
    )


def _sqlite_bucket_expr() -> str:
    return (
        "datetime((strftime('%s', ts) / :bucket_s) * :bucket_s, 'unixepoch')"
    )


def _is_sqlite(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "sqlite"
    except Exception:
        return False


# ── Endpoints ──


@router.get("/telemetry", response_model=DERTelemetryResponse)
def get_der_telemetry(
    type: Optional[Literal["pv", "bess", "ev", "ev_charger", "microgrid"]] = Query(
        None, description="Filter by top-level asset type"
    ),
    window: Literal["1h", "24h", "7d", "30d"] = Query("24h"),
    asset_id: Optional[str] = Query(None, description="Single asset drill-down"),
    # ── W5 list filters ──
    type_code: Optional[str] = Query(
        None, description="Filter by der_type_catalog sub-type code"
    ),
    feeder_id: Optional[str] = Query(None, description="Filter by feeder"),
    consumer_id: Optional[str] = Query(None, description="Filter by consumer/owner"),
    state: Optional[str] = Query(
        None, description="Filter by last-known state (online/offline/etc)"
    ),
    search: Optional[str] = Query(
        None,
        description="Case-insensitive substring match against asset id/name/dtr_id and consumer name/account_no",
        min_length=1,
        max_length=80,
    ),
    limit: int = Query(50, ge=1, le=500, description="Max assets per response"),
    offset: int = Query(0, ge=0, description="Pagination offset for the asset list"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return per-asset latest telemetry + bucketed aggregate power curve.

    * `assets`   — one row per matching DER asset with last-known telemetry.
    * `aggregate`— total active-power kW summed across all matching assets per
                   time bucket (1-min for `1h`/`24h`, 15-min for `7d`).

    Empty-stream handling: returns empty lists + a `banner` string; never
    synthesises values (spec 018 no-mock-data rule).
    """
    td, bucket_s = _WINDOWS[window]
    now = datetime.now(timezone.utc)
    cutoff = now - td

    # Normalise simulator type to EMS asset type (`ev` vs `ev_charger`).
    db_type = type
    if type == "ev":
        db_type = "ev"  # der_asset column uses 'ev' per contract
    elif type == "ev_charger":
        db_type = "ev"

    # ── Assets ──
    # Outer-join consumer so search/listing can pull both sides in one query.
    from sqlalchemy import func as _fn, or_

    asset_q = db.query(DERAssetEMS, DERConsumer).outerjoin(
        DERConsumer, DERConsumer.id == DERAssetEMS.consumer_id
    )
    if db_type:
        asset_q = asset_q.filter(DERAssetEMS.type == db_type)
    if asset_id:
        asset_q = asset_q.filter(DERAssetEMS.id == asset_id)
    if type_code:
        asset_q = asset_q.filter(DERAssetEMS.type_code == type_code)
    if feeder_id:
        asset_q = asset_q.filter(DERAssetEMS.feeder_id == feeder_id)
    if consumer_id:
        asset_q = asset_q.filter(DERAssetEMS.consumer_id == consumer_id)
    if search:
        like = f"%{search.lower()}%"
        asset_q = asset_q.filter(
            or_(
                _fn.lower(DERAssetEMS.id).like(like),
                _fn.lower(DERAssetEMS.name).like(like),
                _fn.lower(DERAssetEMS.dtr_id).like(like),
                _fn.lower(DERConsumer.name).like(like),
                _fn.lower(DERConsumer.account_no).like(like),
            )
        )

    # Pre-pagination total for UI paging controls. `state` is a telemetry
    # field (not on der_asset), so we do *not* count-filter on it here —
    # state filtering happens after telemetry join below.
    total_assets = asset_q.with_entities(_fn.count(DERAssetEMS.id)).scalar() or 0

    rows = (
        asset_q.order_by(DERAssetEMS.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    asset_rows = [r[0] for r in rows]
    consumer_by_asset = {r[0].id: r[1] for r in rows if r[1] is not None}

    if not asset_rows:
        return DERTelemetryResponse(
            type=type, window=window, asset_id=asset_id, assets=[], aggregate=[],
            total_assets=int(total_assets),
            banner=(
                "No matching DER assets for the supplied filters."
                if (search or type_code or feeder_id or consumer_id or state)
                else "No matching DER assets — simulator bulk-import may not have run yet."
            ),
        )

    # ── Latest-per-asset telemetry ──
    assets_out: List[DERAssetLatest] = []
    banner: Optional[str] = None
    aggregate_rows: list = []

    def _consumer_inline(asset_id_: str) -> Optional[DERConsumerInline]:
        c = consumer_by_asset.get(asset_id_)
        if c is None:
            return None
        return DERConsumerInline(
            id=c.id, name=c.name,
            account_no=c.account_no, tariff_code=c.tariff_code,
        )

    if not _der_table_exists(db):
        banner = "der_telemetry table not provisioned — Kafka stream pending"
        for a in asset_rows:
            assets_out.append(
                DERAssetLatest(
                    id=a.id, type=a.type, type_code=a.type_code, name=a.name,
                    dtr_id=a.dtr_id, feeder_id=a.feeder_id,
                    capacity_kw=float(a.capacity_kw) if a.capacity_kw is not None else None,
                    capacity_kwh=float(a.capacity_kwh) if a.capacity_kwh is not None else None,
                    consumer=_consumer_inline(a.id),
                )
            )
        return DERTelemetryResponse(
            type=type, window=window, asset_id=asset_id,
            assets=assets_out, aggregate=[],
            total_assets=int(total_assets), banner=banner,
        )

    asset_ids = [a.id for a in asset_rows]

    # Latest row per asset: rank by ts desc, pick first. Works on both PG + SQLite
    # (ROW_NUMBER() is SQL-standard; SQLite supports it ≥3.25.0).
    latest_sql = text(
        """
        WITH ranked AS (
          SELECT
            asset_id, ts, state,
            active_power_kw, reactive_power_kvar, soc_pct,
            session_energy_kwh, achievement_rate_pct, curtailment_pct,
            ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY ts DESC) AS rn
          FROM der_telemetry
          WHERE asset_id IN :aids AND ts >= :cutoff
        )
        SELECT asset_id, ts, state, active_power_kw, reactive_power_kvar,
               soc_pct, session_energy_kwh, achievement_rate_pct, curtailment_pct
        FROM ranked WHERE rn = 1
        """
    ).bindparams()

    # SQLAlchemy needs an explicit expanding bindparam for IN tuples.
    from sqlalchemy import bindparam

    latest_sql = latest_sql.bindparams(bindparam("aids", expanding=True))
    try:
        latest = db.execute(latest_sql, {"aids": asset_ids, "cutoff": cutoff}).fetchall()
    except Exception as exc:  # pragma: no cover - DB portability safety-net
        logger.warning("der telemetry latest query failed: %s", exc)
        latest = []

    latest_by_asset = {row[0]: row for row in latest}

    for a in asset_rows:
        row = latest_by_asset.get(a.id)
        if row is None:
            # `state` filter excludes silent assets — they have no last-known state.
            if state:
                continue
            assets_out.append(
                DERAssetLatest(
                    id=a.id, type=a.type, type_code=a.type_code, name=a.name,
                    dtr_id=a.dtr_id, feeder_id=a.feeder_id,
                    capacity_kw=float(a.capacity_kw) if a.capacity_kw is not None else None,
                    capacity_kwh=float(a.capacity_kwh) if a.capacity_kwh is not None else None,
                    consumer=_consumer_inline(a.id),
                )
            )
            continue
        (_, ts, st, ap, rp, soc, se, ar, cp) = row
        if state and (st or "").lower() != state.lower():
            continue
        assets_out.append(
            DERAssetLatest(
                id=a.id, type=a.type, type_code=a.type_code, name=a.name,
                dtr_id=a.dtr_id, feeder_id=a.feeder_id,
                capacity_kw=float(a.capacity_kw) if a.capacity_kw is not None else None,
                capacity_kwh=float(a.capacity_kwh) if a.capacity_kwh is not None else None,
                consumer=_consumer_inline(a.id),
                last_ts=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                current_output_kw=float(ap) if ap is not None else None,
                soc_pct=float(soc) if soc is not None else None,
                achievement_rate_pct=float(ar) if ar is not None else None,
                curtailment_pct=float(cp) if cp is not None else None,
                state=st,
                inverter_online=(st or "").lower() in ("online", "running", "charging", "discharging") if st else None,
                session_energy_kwh=float(se) if se is not None else None,
            )
        )

    # ── Aggregate bucket curve ──
    bucket_expr = _sqlite_bucket_expr() if _is_sqlite(db) else _bucket_expr(bucket_s)
    agg_sql = text(
        f"""
        SELECT {bucket_expr} AS bucket,
               COALESCE(SUM(active_power_kw), 0) AS total_kw
        FROM der_telemetry
        WHERE asset_id IN :aids AND ts >= :cutoff
        GROUP BY bucket
        ORDER BY bucket
        """
    ).bindparams(bindparam("aids", expanding=True))
    try:
        aggregate_rows = db.execute(
            agg_sql, {"aids": asset_ids, "cutoff": cutoff, "bucket_s": bucket_s}
        ).fetchall()
    except Exception as exc:  # pragma: no cover
        logger.warning("der telemetry aggregate query failed: %s", exc)
        aggregate_rows = []

    aggregate = [
        DERAggregatePoint(
            ts=(r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])),
            total_kw=float(r[1] or 0.0),
        )
        for r in aggregate_rows
    ]

    if not aggregate and not any(a.last_ts for a in assets_out):
        banner = (
            "No DER telemetry in window — waiting for Kafka stream on "
            "hesv2.der.telemetry"
        )

    return DERTelemetryResponse(
        type=type, window=window, asset_id=asset_id,
        assets=assets_out, aggregate=aggregate,
        total_assets=int(total_assets), banner=banner,
    )


@router.get("/feeder/{feeder_id}/aggregate", response_model=DERFeederAggregateResponse)
def get_feeder_der_aggregate(
    feeder_id: str,
    window: Literal["1h", "24h", "7d"] = Query("24h"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Stacked per-type DER contribution for a feeder over `window`.

    Returns one bucket per time slice, with a column per DER type so the
    frontend can render a stacked-area chart directly.
    """
    td, bucket_s = _WINDOWS[window]
    now = datetime.now(timezone.utc)
    cutoff = now - td

    assets = db.query(DERAssetEMS).filter(DERAssetEMS.feeder_id == feeder_id).all()
    assets_by_type: dict = {"pv": [], "bess": [], "ev": [], "microgrid": []}
    for a in assets:
        assets_by_type.setdefault(a.type, []).append(
            {
                "id": a.id,
                "name": a.name,
                "dtr_id": a.dtr_id,
                "capacity_kw": float(a.capacity_kw) if a.capacity_kw is not None else None,
            }
        )

    if not assets:
        return DERFeederAggregateResponse(
            feeder_id=feeder_id, window=window, buckets=[], assets_by_type=assets_by_type,
            banner="No DER assets registered on this feeder.",
        )

    if not _der_table_exists(db):
        return DERFeederAggregateResponse(
            feeder_id=feeder_id, window=window, buckets=[], assets_by_type=assets_by_type,
            banner="der_telemetry table not provisioned — Kafka stream pending",
        )

    from sqlalchemy import bindparam

    bucket_expr = _sqlite_bucket_expr() if _is_sqlite(db) else _bucket_expr(bucket_s)
    sql = text(
        f"""
        SELECT {bucket_expr} AS bucket, a.type AS a_type,
               COALESCE(SUM(t.active_power_kw), 0) AS kw
        FROM der_telemetry t
        JOIN der_asset a ON a.id = t.asset_id
        WHERE a.feeder_id = :fid AND t.ts >= :cutoff
        GROUP BY bucket, a.type
        ORDER BY bucket
        """
    )
    try:
        rows = db.execute(sql, {"fid": feeder_id, "cutoff": cutoff, "bucket_s": bucket_s}).fetchall()
    except Exception as exc:  # pragma: no cover
        logger.warning("feeder aggregate query failed: %s", exc)
        rows = []

    by_bucket: dict = {}
    for bucket, a_type, kw in rows:
        key = bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket)
        slot = by_bucket.setdefault(key, DERFeederAggregateBucket(ts=key))
        v = float(kw or 0.0)
        if a_type == "pv":
            slot.pv_kw += v
        elif a_type == "bess":
            slot.bess_kw += v
        elif a_type in ("ev", "ev_charger"):
            slot.ev_kw += v
        elif a_type == "microgrid":
            slot.microgrid_kw += v
        slot.total_kw += v

    buckets = [by_bucket[k] for k in sorted(by_bucket)]
    banner = None if buckets else "No DER telemetry for this feeder in window."

    return DERFeederAggregateResponse(
        feeder_id=feeder_id, window=window, buckets=buckets,
        assets_by_type=assets_by_type, banner=banner,
    )
