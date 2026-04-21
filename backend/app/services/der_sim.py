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
METROLOGY_DAYS = 90         # rolling billing-grade daily rollup window
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

_INSERT_INV_TELEMETRY_SQL = text("""
    INSERT INTO der_inverter_telemetry
        (inverter_id, ts, ac_voltage_v, ac_current_a, ac_power_kw,
         ac_frequency_hz, power_factor, dc_voltage_v, dc_current_a,
         temperature_c, efficiency_pct)
    VALUES
        (:inverter_id, :ts, :ac_voltage_v, :ac_current_a, :ac_power_kw,
         :ac_frequency_hz, :power_factor, :dc_voltage_v, :dc_current_a,
         :temperature_c, :efficiency_pct)
    ON CONFLICT (inverter_id, ts) DO NOTHING
""")


def _flush(db: Session, rows: list[dict]) -> None:
    if rows:
        db.execute(_INSERT_SQL, rows)
        db.commit()


def _flush_inv(db: Session, rows: list[dict]) -> None:
    if rows:
        db.execute(_INSERT_INV_TELEMETRY_SQL, rows)
        db.commit()


def _inverter_telemetry_fields(asset_power_kw: float, rated_ac_kw: float,
                                state: str) -> dict:
    """Derive per-inverter telemetry fields from the parent asset's tick.

    Assumes a single-inverter PV: the inverter's AC power equals the asset's
    active power (clamped to rated AC). DC power ≈ AC / efficiency. Voltage,
    current, temperature and efficiency are computed around typical values.
    """
    p_ac = max(0.0, min(float(rated_ac_kw) * 1.05, float(asset_power_kw)))
    load = p_ac / rated_ac_kw if rated_ac_kw > 0 else 0.0
    # Efficiency curves: low at partial load, peak ~97% near rated output.
    eff = 85.0 + 12.0 * load - 4.0 * (load ** 2) if load > 0 else 0.0
    eff = max(0.0, min(98.5, eff))
    p_dc = p_ac / (eff / 100.0) if eff > 5 else 0.0
    ac_v = round(random.gauss(230.0, 3.0), 2)
    ac_f = round(random.gauss(50.0, 0.04), 3)
    pf = round(random.uniform(0.96, 0.999), 3) if p_ac > 0.1 else None
    ac_i = round((p_ac * 1000) / (ac_v * 1.732) if p_ac > 0 else 0.0, 3)
    dc_v = round(random.uniform(540.0, 780.0) if p_dc > 0.1 else 0.0, 2)
    dc_i = round((p_dc * 1000) / dc_v if dc_v > 5 else 0.0, 3)
    # Ambient drift: 22°C base + load-driven rise + small noise.
    temp = round(22.0 + 28.0 * load + random.gauss(0, 1.0), 2) if p_ac > 0.1 \
        else round(random.gauss(22.0, 1.5), 2)
    return {
        "ac_voltage_v": ac_v,
        "ac_current_a": ac_i,
        "ac_power_kw": round(p_ac, 3),
        "ac_frequency_hz": ac_f,
        "power_factor": pf,
        "dc_voltage_v": dc_v,
        "dc_current_a": dc_i,
        "temperature_c": temp,
        "efficiency_pct": round(eff, 2),
    }


def _load_pv_inverter_map(db: Session) -> dict[str, list[tuple[str, float]]]:
    """Return {asset_id: [(inverter_id, rated_ac_kw), ...]} for PV assets."""
    rows = db.execute(text("""
        SELECT i.asset_id, i.id,
               COALESCE(i.rated_ac_kw, a.capacity_kw, 10)::float
        FROM der_inverter i
        JOIN der_asset a ON a.id = i.asset_id
        WHERE a.type = 'pv'
    """)).fetchall()
    m: dict[str, list[tuple[str, float]]] = {}
    for asset_id, inv_id, rated in rows:
        m.setdefault(asset_id, []).append((inv_id, rated))
    return m


# ── Back-fill ──────────────────────────────────────────────────────────────────

def _ensure_inverters_for_pv(db: Session) -> int:
    """Create one inverter per PV asset that has none (demo data).

    Returns the number of inverters created.
    """
    import uuid as _uuid

    rows = db.execute(text("""
        SELECT a.id, COALESCE(a.capacity_kw, 5)::float AS cap_kw, a.name
        FROM der_asset a
        WHERE a.type = 'pv'
          AND NOT EXISTS (SELECT 1 FROM der_inverter i WHERE i.asset_id = a.id)
    """)).fetchall()

    if not rows:
        return 0

    makers = [
        ("SMA", "STP 25000-TL", "three", "Modbus/TCP", "3.21.12.R"),
        ("Huawei", "SUN2000-33KTL", "three", "Modbus/TCP", "V100R001C10"),
        ("ABB", "TRIO-TM-50.0", "three", "SunSpec", "2.4.1"),
        ("Fronius", "Symo 20.0-3-M", "three", "Modbus/TCP", "3.14.1-2"),
        ("SolarEdge", "SE27.6K", "three", "Modbus/TCP", "4.13.33"),
    ]

    today = date.today()
    for asset_id, cap_kw, _name in rows:
        seed = abs(hash(asset_id)) % 10_000
        rng = random.Random(seed)
        mfr, model, phase, comms, fw = rng.choice(makers)
        inv_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"inv-{asset_id}"))
        sn = f"{mfr[:3].upper()}-{asset_id}-{seed % 1000:03d}"
        rated_ac = round(float(cap_kw) * rng.uniform(0.95, 1.00), 2)
        rated_dc = round(rated_ac * rng.uniform(1.03, 1.10), 2)
        installed = today - timedelta(days=rng.randint(180, 1095))
        warranty = installed + timedelta(days=365 * 5)

        try:
            db.execute(text("""
                INSERT INTO der_inverter
                    (id, asset_id, manufacturer, model, serial_number,
                     firmware_version, rated_ac_kw, rated_dc_kw,
                     num_mppt_trackers, num_strings, phase_config,
                     ac_voltage_nominal_v, comms_protocol,
                     installation_date, warranty_expires, status)
                VALUES
                    (:id, :asset_id, :mfr, :model, :sn, :fw,
                     :rated_ac, :rated_dc, :mppt, :strings, :phase,
                     400.0, :comms, :installed, :warranty, 'online')
                ON CONFLICT (serial_number) DO NOTHING
            """), {
                "id": inv_id, "asset_id": asset_id, "mfr": mfr, "model": model,
                "sn": sn, "fw": fw, "rated_ac": rated_ac, "rated_dc": rated_dc,
                "mppt": rng.randint(2, 4), "strings": rng.randint(6, 16),
                "phase": phase, "comms": comms,
                "installed": installed, "warranty": warranty,
            })
        except Exception:
            db.rollback()
    db.commit()
    log.info("der_sim: ensured %d inverters for PV assets without any", len(rows))
    return len(rows)


def _rollup_metrology_daily(db: Session, days: int = 90) -> int:
    """Compute billing-grade daily metrology rollups from der_telemetry.

    One row per (asset_id, date) covering the last `days` days. The fields
    derived per asset type are:

    * PV:  kwh_generated from Σ(positive active_power_kw × Δt),
           kwh_exported ≈ 65% of generated, self_consumed = remainder,
           peak_output_kw = MAX(active_power_kw),
           achievement_pct = kwh_generated / (capacity_kw × 6.5h_effective) × 100.
    * BESS: kwh_exported from Σ(positive active_power_kw × Δt) (discharge),
            kwh_imported from Σ(-active_power_kw × Δt) for negative (charge).
    * EV:  kwh_imported from Σ(active_power_kw × Δt).

    Δt is derived from the actual sampling interval (TICK_SECONDS / 3600 h).
    Uses INSERT ... ON CONFLICT ... DO UPDATE so repeated calls refresh
    rollups for in-progress days without duplicating rows.
    """
    now = _aligned_now()
    start = (now - timedelta(days=days)).date()
    dt_h = TICK_SECONDS / 3600.0

    # One SQL statement per asset type so we can materialise the right
    # columns from the same aggregate cube without branching per row.
    # PV ─────────────────────────────────────────────────────────────────
    pv_sql = text("""
        INSERT INTO der_metrology_daily AS d
            (asset_id, date, kwh_generated, kwh_exported, kwh_imported,
             kwh_self_consumed, peak_output_kw, equivalent_hours,
             achievement_pct, reading_count, estimated_count, source)
        SELECT t.asset_id,
               (t.ts AT TIME ZONE 'UTC')::date AS d,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h, 4) AS gen,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h * 0.65, 4) AS exp,
               0 AS imp,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h * 0.35, 4) AS self_c,
               ROUND(MAX(t.active_power_kw), 3) AS peak,
               ROUND((SUM(GREATEST(t.active_power_kw, 0)) * :dt_h)
                     / NULLIF(a.capacity_kw, 0), 3) AS eq_h,
               LEAST(105,
                 ROUND(((SUM(GREATEST(t.active_power_kw, 0)) * :dt_h)
                        / NULLIF(a.capacity_kw * 6.5, 0)) * 100, 2)) AS ach,
               COUNT(*) AS n_reads,
               0 AS n_est,
               'DER_TELEMETRY' AS source
        FROM der_telemetry t
        JOIN der_asset a ON a.id = t.asset_id
        WHERE a.type = 'pv'
          AND t.ts >= :start
        GROUP BY t.asset_id, d, a.capacity_kw
        ON CONFLICT (asset_id, date) DO UPDATE SET
          kwh_generated     = EXCLUDED.kwh_generated,
          kwh_exported      = EXCLUDED.kwh_exported,
          kwh_imported      = EXCLUDED.kwh_imported,
          kwh_self_consumed = EXCLUDED.kwh_self_consumed,
          peak_output_kw    = EXCLUDED.peak_output_kw,
          equivalent_hours  = EXCLUDED.equivalent_hours,
          achievement_pct   = EXCLUDED.achievement_pct,
          reading_count     = EXCLUDED.reading_count,
          updated_at        = now()
    """)

    # BESS ───────────────────────────────────────────────────────────────
    bess_sql = text("""
        INSERT INTO der_metrology_daily
            (asset_id, date, kwh_generated, kwh_exported, kwh_imported,
             kwh_self_consumed, peak_output_kw, equivalent_hours,
             achievement_pct, reading_count, estimated_count, source)
        SELECT t.asset_id,
               (t.ts AT TIME ZONE 'UTC')::date AS d,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h, 4) AS gen,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h, 4) AS exp,
               ROUND(SUM(GREATEST(-t.active_power_kw, 0)) * :dt_h, 4) AS imp,
               0 AS self_c,
               ROUND(MAX(ABS(t.active_power_kw)), 3) AS peak,
               ROUND((SUM(GREATEST(t.active_power_kw, 0)) * :dt_h)
                     / NULLIF(a.capacity_kw, 0), 3) AS eq_h,
               NULL AS ach,
               COUNT(*) AS n_reads,
               0 AS n_est,
               'DER_TELEMETRY' AS source
        FROM der_telemetry t
        JOIN der_asset a ON a.id = t.asset_id
        WHERE a.type = 'bess'
          AND t.ts >= :start
        GROUP BY t.asset_id, d, a.capacity_kw
        ON CONFLICT (asset_id, date) DO UPDATE SET
          kwh_generated     = EXCLUDED.kwh_generated,
          kwh_exported      = EXCLUDED.kwh_exported,
          kwh_imported      = EXCLUDED.kwh_imported,
          kwh_self_consumed = EXCLUDED.kwh_self_consumed,
          peak_output_kw    = EXCLUDED.peak_output_kw,
          equivalent_hours  = EXCLUDED.equivalent_hours,
          reading_count     = EXCLUDED.reading_count,
          updated_at        = now()
    """)

    # EV ─────────────────────────────────────────────────────────────────
    ev_sql = text("""
        INSERT INTO der_metrology_daily
            (asset_id, date, kwh_generated, kwh_exported, kwh_imported,
             kwh_self_consumed, peak_output_kw, equivalent_hours,
             achievement_pct, reading_count, estimated_count, source)
        SELECT t.asset_id,
               (t.ts AT TIME ZONE 'UTC')::date AS d,
               0 AS gen, 0 AS exp,
               ROUND(SUM(GREATEST(t.active_power_kw, 0)) * :dt_h, 4) AS imp,
               0 AS self_c,
               ROUND(MAX(t.active_power_kw), 3) AS peak,
               ROUND((SUM(GREATEST(t.active_power_kw, 0)) * :dt_h)
                     / NULLIF(a.capacity_kw, 0), 3) AS eq_h,
               NULL AS ach,
               COUNT(*) AS n_reads,
               0 AS n_est,
               'DER_TELEMETRY' AS source
        FROM der_telemetry t
        JOIN der_asset a ON a.id = t.asset_id
        WHERE a.type = 'ev'
          AND t.ts >= :start
        GROUP BY t.asset_id, d, a.capacity_kw
        ON CONFLICT (asset_id, date) DO UPDATE SET
          kwh_imported      = EXCLUDED.kwh_imported,
          peak_output_kw    = EXCLUDED.peak_output_kw,
          equivalent_hours  = EXCLUDED.equivalent_hours,
          reading_count     = EXCLUDED.reading_count,
          updated_at        = now()
    """)

    total = 0
    for sql in (pv_sql, bess_sql, ev_sql):
        try:
            res = db.execute(sql, {"dt_h": dt_h, "start": start})
            total += res.rowcount or 0
            db.commit()
        except Exception as exc:
            log.error("der_sim: metrology rollup error: %s", exc)
            db.rollback()
    log.info("der_sim: metrology rollup upserted ~%d rows", total)
    return total


def _backfill_inverter_telemetry(db: Session) -> int:
    """Back-fill per-inverter telemetry for PV inverters that have none in
    the last 2h. Derives inverter readings from the asset's existing
    der_telemetry rows so the two stay aligned.
    """
    now = _aligned_now()
    cutoff_stale = now - timedelta(hours=2)
    start = now - timedelta(days=HISTORY_DAYS)

    stale_invs = db.execute(text("""
        SELECT i.id, i.asset_id,
               COALESCE(i.rated_ac_kw, a.capacity_kw, 10)::float AS rated_ac,
               COALESCE(a.capacity_kw, i.rated_ac_kw, 10)::float AS cap_kw
        FROM der_inverter i
        JOIN der_asset a ON a.id = i.asset_id
        WHERE a.type = 'pv'
          AND NOT EXISTS (
              SELECT 1 FROM der_inverter_telemetry t
              WHERE t.inverter_id = i.id AND t.ts >= :cutoff
          )
    """), {"cutoff": cutoff_stale}).fetchall()

    if not stale_invs:
        return 0

    log.info("der_sim: back-filling telemetry for %d stale inverters", len(stale_invs))

    for inv_id, asset_id, rated_ac, cap_kw in stale_invs:
        # Pull parent-asset telemetry in the window; derive inverter fields.
        asset_rows = db.execute(text("""
            SELECT ts, state, active_power_kw FROM der_telemetry
            WHERE asset_id = :aid AND ts >= :start
            ORDER BY ts
        """), {"aid": asset_id, "start": start}).fetchall()

        inv_rows: list[dict] = []
        for ts, state, p_kw in asset_rows:
            p_asset = float(p_kw or 0.0)
            share = p_asset * (rated_ac / cap_kw) if cap_kw else p_asset
            inv_fields = _inverter_telemetry_fields(share, rated_ac, state or "online")
            inv_rows.append({"inverter_id": inv_id, "ts": ts, **inv_fields})
            if len(inv_rows) >= BATCH:
                _flush_inv(db, inv_rows)
                inv_rows = []
        _flush_inv(db, inv_rows)
    log.info("der_sim: inverter telemetry backfill complete")
    return len(stale_invs)


def backfill(db: Session) -> int:
    """Fill 30 days of history for every asset that has no data in the last 2h.

    Returns number of assets back-filled. Also ensures every PV asset has at
    least one inverter registered and that inverter telemetry is populated.
    """
    # Make sure PV assets have inverters registered (demo data).
    try:
        _ensure_inverters_for_pv(db)
    except Exception as exc:
        log.error("der_sim: inverter ensure error: %s", exc)
        db.rollback()

    # Back-fill inverter telemetry (independent of asset-telemetry gate).
    try:
        _backfill_inverter_telemetry(db)
    except Exception as exc:
        log.error("der_sim: inverter telemetry backfill error: %s", exc)
        db.rollback()

    # Roll up 90 days of daily metrology from existing telemetry rows.
    try:
        _rollup_metrology_daily(db, days=METROLOGY_DAYS)
    except Exception as exc:
        log.error("der_sim: metrology rollup error: %s", exc)
        db.rollback()

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
    pv_inverters = _load_pv_inverter_map(db)

    for asset_id, atype, cap_kw, cap_kwh in stale:
        rows: list[dict] = []
        inv_rows: list[dict] = []
        soc = random.uniform(45.0, 75.0)
        ev_active = False
        ev_se = 0.0
        inverters = pv_inverters.get(asset_id, []) if atype == "pv" else []

        for step in range(n_steps):
            ts = start + timedelta(seconds=step * TICK_SECONDS)
            if atype == "pv":
                fields = _pv_tick(ts, cap_kw, asset_id)
            elif atype == "bess":
                fields, soc = _bess_tick(ts, cap_kw, cap_kwh, soc)
            else:
                fields, ev_active, ev_se = _ev_tick(ts, cap_kw, ev_active, ev_se)

            rows.append({"asset_id": asset_id, "ts": ts, **fields})

            # Mirror PV output onto each attached inverter.
            if inverters and atype == "pv":
                p_asset = float(fields["active_power_kw"] or 0.0)
                for inv_id, rated_ac in inverters:
                    share = p_asset * (rated_ac / cap_kw) if cap_kw else p_asset
                    inv_fields = _inverter_telemetry_fields(share, rated_ac, fields["state"])
                    inv_rows.append({"inverter_id": inv_id, "ts": ts, **inv_fields})

            if len(rows) >= BATCH:
                _flush(db, rows)
                rows = []
            if len(inv_rows) >= BATCH:
                _flush_inv(db, inv_rows)
                inv_rows = []
        _flush(db, rows)
        _flush_inv(db, inv_rows)

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

    pv_inverters = _load_pv_inverter_map(db)
    rows: list[dict] = []
    inv_rows: list[dict] = []

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

        if atype == "pv":
            p_asset = float(fields["active_power_kw"] or 0.0)
            for inv_id, rated_ac in pv_inverters.get(asset_id, []):
                share = p_asset * (rated_ac / cap_kw) if cap_kw else p_asset
                inv_fields = _inverter_telemetry_fields(share, rated_ac, fields["state"])
                inv_rows.append({"inverter_id": inv_id, "ts": now, **inv_fields})

        if len(rows) >= BATCH:
            _flush(db, rows)
            rows = []
        if len(inv_rows) >= BATCH:
            _flush_inv(db, inv_rows)
            inv_rows = []

    _flush(db, rows)
    _flush_inv(db, inv_rows)
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

    tick_count = 0
    while not stop.is_set():
        db = SessionLocal()
        try:
            n = await loop.run_in_executor(None, tick, db)
            log.debug("der_sim: tick inserted %d rows at %s", n, _aligned_now())
            # Refresh daily metrology rollup every 12 ticks (~1 h) so the
            # in-progress day's billing kWh stays up to date without making
            # every 5-min tick expensive.
            tick_count += 1
            if tick_count % 12 == 0:
                try:
                    await loop.run_in_executor(None, _rollup_metrology_daily, db, 2)
                except Exception as exc:
                    log.error("der_sim: rollup refresh error: %s", exc)
        except Exception as exc:
            log.error("der_sim: tick error: %s", exc)
        finally:
            db.close()

        try:
            await asyncio.wait_for(stop.wait(), timeout=float(TICK_SECONDS))
        except asyncio.TimeoutError:
            pass
