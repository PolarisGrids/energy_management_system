"""DER realtime simulator (demo / dev mode).

Runs as an asyncio background task started from ``app.main.lifespan`` when
``DER_SIM_ENABLED=1`` (default on). Every 5 minutes it:

1. Ensures the current-week ``der_telemetry`` partition exists.
2. Queries every row in ``der_asset``.
3. Inserts one telemetry row per asset at the current 5-min-aligned UTC timestamp.

On startup it also **back-fills** any asset whose latest telemetry is older than
2 hours, filling from 30 days ago up to the current tick. This ensures all
windows (1h / 24h / 7d / 30d) are populated immediately after a fresh deploy.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.base import SessionLocal

log = logging.getLogger(__name__)

TICK_SECONDS = 300          # 5-minute interval
HISTORY_DAYS = 30
SAST_OFFSET_H = 2
SUNRISE_H = 6.0
SUNSET_H = 18.0
BATCH = 400


# ── Physics ────────────────────────────────────────────────────────────────────

def _solar_fraction(ts_utc: datetime, cloud: float) -> float:
    h = (ts_utc.hour + ts_utc.minute / 60.0) + SAST_OFFSET_H
    if h < SUNRISE_H or h >= SUNSET_H:
        return 0.0
    frac = math.sin(math.pi * (h - SUNRISE_H) / (SUNSET_H - SUNRISE_H)) ** 1.2
    return max(0.0, min(1.0, frac * cloud * (1 + random.gauss(0, 0.025))))


def _cloud_for_day(asset_id: str, day: date) -> float:
    seed = hash(asset_id) ^ (day.toordinal() * 7919) & 0xFFFFFFFF
    rng = random.Random(seed)
    r = rng.random()
    if r > 0.55:
        return rng.uniform(0.88, 1.0)
    elif r > 0.20:
        return rng.uniform(0.58, 0.88)
    return rng.uniform(0.25, 0.55)


def _pv_tick(ts: datetime, cap_kw: float, asset_id: str) -> dict:
    cloud = _cloud_for_day(asset_id, ts.date())
    frac = _solar_fraction(ts, cloud)
    power = round(cap_kw * 0.97 * frac, 3)
    h = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
    if h < SUNRISE_H or h >= SUNSET_H:
        state = "idle"
        achiev = None
    else:
        state = "online"
        exp = cap_kw * 0.97 * max(1e-6,
            math.sin(math.pi * (h - SUNRISE_H) / (SUNSET_H - SUNRISE_H)) ** 1.2)
        achiev = round(min(110.0, power / exp * 100), 2)
    return dict(state=state, active_power_kw=power,
                reactive_power_kvar=round(power * 0.05, 3) if power > 0 else None,
                soc_pct=None, session_energy_kwh=None,
                achievement_rate_pct=achiev, curtailment_pct=None)


def _bess_tick(ts: datetime, cap_kw: float, cap_kwh: float, soc: float) -> tuple[dict, float]:
    h = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
    dt_h = TICK_SECONDS / 3600.0
    if (h >= 23 or h < 6) and soc < 80:
        rate = cap_kw * random.uniform(0.25, 0.40)
        soc = min(95.0, soc + rate * dt_h / cap_kwh * 100)
        state, power = "charging", -rate
    elif 9.5 <= h < 13.5 and soc < 92:
        rate = cap_kw * random.uniform(0.55, 0.90)
        soc = min(95.0, soc + rate * dt_h / cap_kwh * 100)
        state, power = "charging", -rate
    elif 17.0 <= h < 21.0 and soc > 18:
        rate = cap_kw * random.uniform(0.50, 0.85)
        soc = max(10.0, soc - rate * dt_h / cap_kwh * 100)
        state, power = "discharging", rate
    elif soc < 30:
        rate = cap_kw * random.uniform(0.15, 0.30)
        soc = min(40.0, soc + rate * dt_h / cap_kwh * 100)
        state, power = "charging", -rate
    else:
        state, power = "idle", 0.0
    return (dict(state=state, active_power_kw=round(power, 3),
                 reactive_power_kvar=round(abs(power) * 0.03, 3),
                 soc_pct=round(soc, 2),
                 session_energy_kwh=None, achievement_rate_pct=None,
                 curtailment_pct=None), soc)


def _ev_tick(ts: datetime, cap_kw: float,
             session_active: bool, session_energy: float) -> tuple[dict, bool, float]:
    h = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
    dt_h = TICK_SECONDS / 3600.0
    in_peak = (7.0 <= h < 9.5) or (17.0 <= h < 20.5)
    in_mid = 11.0 <= h < 14.0

    if session_active:
        if random.random() < 0.022 or not (in_peak or in_mid):
            return dict(state="idle", active_power_kw=0.0,
                        reactive_power_kvar=None, soc_pct=None,
                        session_energy_kwh=None, achievement_rate_pct=None,
                        curtailment_pct=None), False, 0.0
        power = cap_kw * random.uniform(0.55, 0.95)
        session_energy += power * dt_h
        return dict(state="charging", active_power_kw=round(power, 3),
                    reactive_power_kvar=round(power * 0.05, 3),
                    soc_pct=None, session_energy_kwh=round(session_energy, 3),
                    achievement_rate_pct=None, curtailment_pct=None), True, session_energy
    else:
        prob = 0.55 if in_peak else (0.30 if in_mid else 0.0)
        if prob > 0 and random.random() < prob:
            power = cap_kw * random.uniform(0.60, 0.95)
            se = power * dt_h
            return dict(state="charging", active_power_kw=round(power, 3),
                        reactive_power_kvar=round(power * 0.05, 3),
                        soc_pct=None, session_energy_kwh=round(se, 3),
                        achievement_rate_pct=None, curtailment_pct=None), True, se
        return dict(state="idle", active_power_kw=0.0,
                    reactive_power_kvar=None, soc_pct=None,
                    session_energy_kwh=None, achievement_rate_pct=None,
                    curtailment_pct=None), False, 0.0


# ── Partition management ───────────────────────────────────────────────────────

def _ensure_partition(db: Session, ts: datetime) -> None:
    d = ts.date()
    week_start = d - timedelta(days=d.weekday())
    week_end = week_start + timedelta(days=7)
    name = f"der_telemetry_{week_start.strftime('%G_%V')}"
    try:
        db.execute(text(
            f"CREATE TABLE IF NOT EXISTS {name} "
            f"PARTITION OF der_telemetry "
            f"FOR VALUES FROM ('{week_start}') TO ('{week_end}');"
        ))
        db.commit()
    except Exception:
        db.rollback()


def _ensure_partitions_range(db: Session, start: datetime, end: datetime) -> None:
    cur = start.date() - timedelta(days=start.date().weekday())
    while cur <= end.date():
        nxt = cur + timedelta(days=7)
        name = f"der_telemetry_{cur.strftime('%G_%V')}"
        try:
            db.execute(text(
                f"CREATE TABLE IF NOT EXISTS {name} "
                f"PARTITION OF der_telemetry "
                f"FOR VALUES FROM ('{cur}') TO ('{nxt}');"
            ))
            db.commit()
        except Exception:
            db.rollback()
        cur = nxt


# ── Bulk insert helpers ────────────────────────────────────────────────────────

_INSERT_SQL = text("""
    INSERT INTO der_telemetry
        (asset_id, ts, state, active_power_kw, reactive_power_kvar,
         soc_pct, session_energy_kwh, achievement_rate_pct, curtailment_pct)
    VALUES
        (:asset_id, :ts, :state, :active_power_kw, :reactive_power_kvar,
         :soc_pct, :session_energy_kwh, :achievement_rate_pct, :curtailment_pct)
""")


def _flush(db: Session, rows: list[dict]) -> None:
    if rows:
        db.execute(_INSERT_SQL, rows)
        db.commit()


# ── Back-fill ──────────────────────────────────────────────────────────────────

def backfill(db: Session) -> int:
    """Fill 30 days of history for every asset that has no data in the last 2h.

    Returns number of assets back-filled.
    """
    now = _aligned_now()
    cutoff_stale = now - timedelta(hours=2)
    start = now - timedelta(days=HISTORY_DAYS)

    # Find assets needing backfill
    stale = db.execute(text("""
        SELECT a.id, a.type,
               COALESCE(a.capacity_kw, 50)::float AS cap_kw,
               COALESCE(a.capacity_kwh, COALESCE(a.capacity_kw,50)*4)::float AS cap_kwh
        FROM der_asset a
        WHERE NOT EXISTS (
            SELECT 1 FROM der_telemetry t
            WHERE t.asset_id = a.id AND t.ts >= :cutoff
        )
    """), {"cutoff": cutoff_stale}).fetchall()

    if not stale:
        log.info("der_sim: no stale assets, skip backfill")
        return 0

    log.info("der_sim: back-filling %d assets from %s to %s", len(stale), start.date(), now.date())
    _ensure_partitions_range(db, start, now)

    n_steps = int((now - start).total_seconds() / TICK_SECONDS) + 1

    for asset_id, atype, cap_kw, cap_kwh in stale:
        rows: list[dict] = []
        soc = random.uniform(45.0, 75.0)
        ev_active = False
        ev_se = 0.0

        for step in range(n_steps):
            ts = start + timedelta(seconds=step * TICK_SECONDS)
            if atype == "pv":
                fields = _pv_tick(ts, cap_kw, asset_id)
            elif atype == "bess":
                fields, soc = _bess_tick(ts, cap_kw, cap_kwh, soc)
            else:
                fields, ev_active, ev_se = _ev_tick(ts, cap_kw, ev_active, ev_se)

            rows.append({"asset_id": asset_id, "ts": ts, **fields})
            if len(rows) >= BATCH:
                _flush(db, rows)
                rows = []
        _flush(db, rows)

    log.info("der_sim: backfill complete (%d assets, ~%d rows each)", len(stale), n_steps)
    return len(stale)


# ── Realtime tick ──────────────────────────────────────────────────────────────

def _aligned_now() -> datetime:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return now - timedelta(minutes=now.minute % (TICK_SECONDS // 60))


# In-memory carry-forward state per asset (soc for BESS, session for EV)
_bess_soc: dict[str, float] = {}
_ev_state: dict[str, tuple[bool, float]] = {}  # (active, session_kwh)


def tick(db: Session) -> int:
    """Generate one row per asset at the current aligned timestamp. Returns row count."""
    now = _aligned_now()
    _ensure_partition(db, now)

    assets = db.execute(text("""
        SELECT id, type,
               COALESCE(capacity_kw, 50)::float,
               COALESCE(capacity_kwh, COALESCE(capacity_kw,50)*4)::float
        FROM der_asset
    """)).fetchall()

    rows: list[dict] = []
    for asset_id, atype, cap_kw, cap_kwh in assets:
        if atype == "pv":
            fields = _pv_tick(now, cap_kw, asset_id)
        elif atype == "bess":
            soc = _bess_soc.get(asset_id, random.uniform(45.0, 75.0))
            fields, soc = _bess_tick(now, cap_kw, cap_kwh, soc)
            _bess_soc[asset_id] = soc
        else:
            active, se = _ev_state.get(asset_id, (False, 0.0))
            fields, active, se = _ev_tick(now, cap_kw, active, se)
            _ev_state[asset_id] = (active, se)

        rows.append({"asset_id": asset_id, "ts": now, **fields})
        if len(rows) >= BATCH:
            _flush(db, rows)
            rows = []
    _flush(db, rows)
    return len(assets)


# ── Async loop (wired into FastAPI lifespan) ───────────────────────────────────

async def run_sim_loop(stop: asyncio.Event) -> None:
    log.info("der_sim: starting (tick=%ds, history=%dd)", TICK_SECONDS, HISTORY_DAYS)

    # Back-fill on first start (blocking but fast enough in an executor)
    loop = asyncio.get_running_loop()
    db = SessionLocal()
    try:
        filled = await loop.run_in_executor(None, backfill, db)
        if filled:
            log.info("der_sim: back-filled %d assets", filled)
    except Exception as exc:
        log.error("der_sim: backfill error: %s", exc)
    finally:
        db.close()

    # Align first tick to the next 5-min boundary
    now = datetime.now(timezone.utc)
    next_tick = _aligned_now() + timedelta(seconds=TICK_SECONDS)
    wait = (next_tick - now).total_seconds()
    if wait > 0:
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass

    while not stop.is_set():
        db = SessionLocal()
        try:
            n = await loop.run_in_executor(None, tick, db)
            log.debug("der_sim: tick inserted %d rows at %s", n, _aligned_now())
        except Exception as exc:
            log.error("der_sim: tick error: %s", exc)
        finally:
            db.close()

        try:
            await asyncio.wait_for(stop.wait(), timeout=float(TICK_SECONDS))
        except asyncio.TimeoutError:
            pass
