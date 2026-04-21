"""Seed 30 days of historical DER telemetry + 90-day metrology rollups.

Creates realistic consumers, assets (PV / BESS / EV), inverters, and time-series
data so the DER fleet and drill-down pages render fully populated charts.

Run once after DB migrations and the base seed_data.py:

    cd backend
    python scripts/seed_der_historical.py

Idempotent: consumers / assets / inverters are inserted with ON CONFLICT DO NOTHING.
Telemetry rows are batch-upserted; re-running overwrites the same time window.
"""
from __future__ import annotations

import math
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.base import SessionLocal

random.seed(42)

# ── Constants ─────────────────────────────────────────────────────────────────

HISTORY_DAYS = 30        # telemetry window (matches max API window)
METROLOGY_DAYS = 90      # daily rollup window
TELEMETRY_INTERVAL_MIN = 5
SAST_OFFSET_H = 2        # UTC+2

SUNRISE_H = 6.0          # fractional hour in SAST
SUNSET_H = 18.0

# ── Asset definitions ─────────────────────────────────────────────────────────

CONSUMERS = [
    {
        "id": "con-sow-001",
        "name": "Soweto Solar Solutions",
        "account_no": "ACC-SOW-0001",
        "email": "ops@sowetosolar.co.za",
        "phone": "+27113450001",
        "premise_address": "12 Vilakazi St, Soweto, Johannesburg",
        "lat": Decimal("-26.2485"), "lon": Decimal("27.8546"),
        "tariff_code": "TOU-C3",
    },
    {
        "id": "con-san-001",
        "name": "Sandton Energy Storage Ltd",
        "account_no": "ACC-SAN-0001",
        "email": "grid@sandtonbess.co.za",
        "phone": "+27112340002",
        "premise_address": "5 Sandton Drive, Sandton, Johannesburg",
        "lat": Decimal("-26.1076"), "lon": Decimal("28.0567"),
        "tariff_code": "RURAFLEX",
    },
    {
        "id": "con-cpt-001",
        "name": "Cape Town EV Hub",
        "account_no": "ACC-CPT-0001",
        "email": "charge@ctevhub.co.za",
        "phone": "+27214560003",
        "premise_address": "V&A Waterfront, Cape Town",
        "lat": Decimal("-33.9015"), "lon": Decimal("18.4185"),
        "tariff_code": "TOU-C3",
    },
    {
        "id": "con-pta-001",
        "name": "Pretoria Green Power",
        "account_no": "ACC-PTA-0001",
        "email": "green@ptapower.co.za",
        "phone": "+27123450004",
        "premise_address": "33 Church St, Pretoria CBD",
        "lat": Decimal("-25.7463"), "lon": Decimal("28.1878"),
        "tariff_code": "TOU-C2",
    },
    {
        "id": "con-dbn-001",
        "name": "Durban Harbour Power",
        "account_no": "ACC-DBN-0001",
        "email": "power@dbnharbour.co.za",
        "phone": "+27313450005",
        "premise_address": "Maydon Wharf, Durban Harbour",
        "lat": Decimal("-29.8587"), "lon": Decimal("31.0218"),
        "tariff_code": "RURAFLEX",
    },
    {
        "id": "con-jhb-001",
        "name": "Johannesburg Fast Charge",
        "account_no": "ACC-JHB-0001",
        "email": "charge@jhbfast.co.za",
        "phone": "+27116780006",
        "premise_address": "Nelson Mandela Square, Sandton",
        "lat": Decimal("-26.1071"), "lon": Decimal("28.0544"),
        "tariff_code": "TOU-C3",
    },
    {
        "id": "con-blo-001",
        "name": "Bloemfontein Energy Storage",
        "account_no": "ACC-BLO-0001",
        "email": "ops@bloemenergy.co.za",
        "phone": "+27514560007",
        "premise_address": "30 Naval Hill Dr, Bloemfontein",
        "lat": Decimal("-29.1123"), "lon": Decimal("26.2140"),
        "tariff_code": "TOU-C2",
    },
]

ASSETS = [
    # ── PV ────────────────────────────────────────────────────────────────────
    {
        "id": "SOW-PV-001", "type": "pv", "type_code": "rooftop_pv",
        "name": "Soweto Rooftop Cluster #1",
        "consumer_id": "con-sow-001",
        "capacity_kw": Decimal("250.00"), "capacity_kwh": None,
        "lat": Decimal("-26.2492"), "lon": Decimal("27.8551"),
    },
    {
        "id": "SAN-PV-001", "type": "pv", "type_code": "rooftop_pv",
        "name": "Sandton Office Park PV",
        "consumer_id": "con-san-001",
        "capacity_kw": Decimal("150.00"), "capacity_kwh": None,
        "lat": Decimal("-26.1073"), "lon": Decimal("28.0572"),
    },
    {
        "id": "CPT-PV-001", "type": "pv", "type_code": "ground_mount_pv",
        "name": "Cape Town Ground-Mount Array",
        "consumer_id": "con-cpt-001",
        "capacity_kw": Decimal("500.00"), "capacity_kwh": None,
        "lat": Decimal("-33.9021"), "lon": Decimal("18.4190"),
    },
    {
        "id": "PTA-PV-001", "type": "pv", "type_code": "carport_pv",
        "name": "Pretoria Carport Solar",
        "consumer_id": "con-pta-001",
        "capacity_kw": Decimal("100.00"), "capacity_kwh": None,
        "lat": Decimal("-25.7468"), "lon": Decimal("28.1882"),
    },
    {
        "id": "DBN-PV-001", "type": "pv", "type_code": "ground_mount_pv",
        "name": "Durban Harbour PV Farm",
        "consumer_id": "con-dbn-001",
        "capacity_kw": Decimal("800.00"), "capacity_kwh": None,
        "lat": Decimal("-29.8591"), "lon": Decimal("31.0225"),
    },
    # ── BESS ──────────────────────────────────────────────────────────────────
    {
        "id": "SAN-BESS-001", "type": "bess", "type_code": "lithium_bess",
        "name": "Sandton Lithium BESS Unit #1",
        "consumer_id": "con-san-001",
        "capacity_kw": Decimal("200.00"), "capacity_kwh": Decimal("800.00"),
        "lat": Decimal("-26.1078"), "lon": Decimal("28.0563"),
    },
    {
        "id": "CPT-BESS-001", "type": "bess", "type_code": "flow_bess",
        "name": "Cape Town Flow Battery",
        "consumer_id": "con-cpt-001",
        "capacity_kw": Decimal("150.00"), "capacity_kwh": Decimal("600.00"),
        "lat": Decimal("-33.9018"), "lon": Decimal("18.4188"),
    },
    {
        "id": "BLO-BESS-001", "type": "bess", "type_code": "hybrid_bess",
        "name": "Bloemfontein Hybrid Battery",
        "consumer_id": "con-blo-001",
        "capacity_kw": Decimal("100.00"), "capacity_kwh": Decimal("400.00"),
        "lat": Decimal("-29.1126"), "lon": Decimal("26.2145"),
    },
    # ── EV ────────────────────────────────────────────────────────────────────
    {
        "id": "CPT-EV-001", "type": "ev", "type_code": "dc_fast",
        "name": "Cape Town Waterfront Fast Charge",
        "consumer_id": "con-cpt-001",
        "capacity_kw": Decimal("360.00"), "capacity_kwh": None,
        "lat": Decimal("-33.9017"), "lon": Decimal("18.4180"),
    },
    {
        "id": "JHB-EV-001", "type": "ev", "type_code": "dc_fast",
        "name": "Joburg CBD Fast Charge Hub",
        "consumer_id": "con-jhb-001",
        "capacity_kw": Decimal("240.00"), "capacity_kwh": None,
        "lat": Decimal("-26.1074"), "lon": Decimal("28.0548"),
    },
    {
        "id": "PTA-EV-001", "type": "ev", "type_code": "ac_l2",
        "name": "Pretoria Mall AC Charger",
        "consumer_id": "con-pta-001",
        "capacity_kw": Decimal("50.00"), "capacity_kwh": None,
        "lat": Decimal("-25.7470"), "lon": Decimal("28.1885"),
    },
    {
        "id": "DBN-EV-001", "type": "ev", "type_code": "v2g",
        "name": "Durban V2G Hub",
        "consumer_id": "con-dbn-001",
        "capacity_kw": Decimal("100.00"), "capacity_kwh": None,
        "lat": Decimal("-29.8589"), "lon": Decimal("31.0220"),
    },
]

# Inverter specs keyed by PV asset_id
INVERTERS = {
    "SOW-PV-001": [
        {"manufacturer": "SMA", "model": "STP 125-US-41", "serial_number": "SMA-SOW-001-A",
         "rated_ac_kw": 125.0, "rated_dc_kw": 130.0, "num_mppt_trackers": 2, "num_strings": 8,
         "phase_config": "three", "firmware_version": "3.21.12.R"},
        {"manufacturer": "SMA", "model": "STP 125-US-41", "serial_number": "SMA-SOW-001-B",
         "rated_ac_kw": 125.0, "rated_dc_kw": 130.0, "num_mppt_trackers": 2, "num_strings": 8,
         "phase_config": "three", "firmware_version": "3.21.12.R"},
    ],
    "SAN-PV-001": [
        {"manufacturer": "Huawei", "model": "SUN2000-150KTL", "serial_number": "HW-SAN-001",
         "rated_ac_kw": 150.0, "rated_dc_kw": 157.5, "num_mppt_trackers": 10, "num_strings": 20,
         "phase_config": "three", "firmware_version": "V100R001C10"},
    ],
    "CPT-PV-001": [
        {"manufacturer": "ABB", "model": "TRIO-TM-50.0", "serial_number": "ABB-CPT-001-A",
         "rated_ac_kw": 167.0, "rated_dc_kw": 175.0, "num_mppt_trackers": 3, "num_strings": 12,
         "phase_config": "three", "firmware_version": "2.4.1"},
        {"manufacturer": "ABB", "model": "TRIO-TM-50.0", "serial_number": "ABB-CPT-001-B",
         "rated_ac_kw": 167.0, "rated_dc_kw": 175.0, "num_mppt_trackers": 3, "num_strings": 12,
         "phase_config": "three", "firmware_version": "2.4.1"},
        {"manufacturer": "ABB", "model": "TRIO-TM-50.0", "serial_number": "ABB-CPT-001-C",
         "rated_ac_kw": 166.0, "rated_dc_kw": 174.0, "num_mppt_trackers": 3, "num_strings": 12,
         "phase_config": "three", "firmware_version": "2.4.1"},
    ],
    "PTA-PV-001": [
        {"manufacturer": "Fronius", "model": "Symo 50.0-3-M", "serial_number": "FRO-PTA-001",
         "rated_ac_kw": 50.0, "rated_dc_kw": 52.5, "num_mppt_trackers": 2, "num_strings": 6,
         "phase_config": "three", "firmware_version": "3.14.1-2"},
        {"manufacturer": "Fronius", "model": "Symo 50.0-3-M", "serial_number": "FRO-PTA-002",
         "rated_ac_kw": 50.0, "rated_dc_kw": 52.5, "num_mppt_trackers": 2, "num_strings": 6,
         "phase_config": "three", "firmware_version": "3.14.1-2"},
    ],
    "DBN-PV-001": [
        {"manufacturer": "SMA", "model": "STP 250-US-41", "serial_number": "SMA-DBN-001-A",
         "rated_ac_kw": 267.0, "rated_dc_kw": 280.0, "num_mppt_trackers": 4, "num_strings": 16,
         "phase_config": "three", "firmware_version": "3.21.12.R"},
        {"manufacturer": "SMA", "model": "STP 250-US-41", "serial_number": "SMA-DBN-001-B",
         "rated_ac_kw": 267.0, "rated_dc_kw": 280.0, "num_mppt_trackers": 4, "num_strings": 16,
         "phase_config": "three", "firmware_version": "3.21.12.R"},
        {"manufacturer": "SMA", "model": "STP 250-US-41", "serial_number": "SMA-DBN-001-C",
         "rated_ac_kw": 266.0, "rated_dc_kw": 279.0, "num_mppt_trackers": 4, "num_strings": 16,
         "phase_config": "three", "firmware_version": "3.21.12.R"},
    ],
}


# ── Physics helpers ────────────────────────────────────────────────────────────

def _solar_fraction(ts_utc: datetime, cloud: float) -> float:
    """Fraction of rated capacity from solar irradiance at a given UTC timestamp."""
    h_sast = (ts_utc.hour + ts_utc.minute / 60.0) + SAST_OFFSET_H
    if h_sast < SUNRISE_H or h_sast >= SUNSET_H:
        return 0.0
    # Bell curve: sin(pi * (h - sunrise) / daylight_hours)^1.2
    frac = math.sin(math.pi * (h_sast - SUNRISE_H) / (SUNSET_H - SUNRISE_H))
    frac = max(0.0, frac ** 1.2)
    # Minute-level jitter for cloud scud
    jitter = 1.0 + random.gauss(0, 0.025)
    return min(1.0, max(0.0, frac * cloud * jitter))


def _daily_cloud_curve(day_index: int, n_steps: int) -> list[float]:
    """Returns per-step cloud transmission factors for one day.

    Mixture of clear days (cloud ~ 0.92-1.0), partly cloudy (0.6-0.85), and
    overcast (0.25-0.55). Cloud transitions slowly within a day.
    """
    rng = random.Random(day_index * 7919)
    day_type = rng.random()
    if day_type > 0.55:      # clear ~45% of days
        base = rng.uniform(0.90, 1.0)
        sigma = 0.04
    elif day_type > 0.20:    # partly cloudy ~35% of days
        base = rng.uniform(0.60, 0.88)
        sigma = 0.10
    else:                    # overcast ~20% of days
        base = rng.uniform(0.25, 0.55)
        sigma = 0.08

    cloud = base
    result = []
    for _ in range(n_steps):
        cloud += rng.gauss(0, sigma * 0.05)
        cloud = max(0.05, min(1.0, cloud))
        result.append(cloud)
    return result


def _bess_profile(ts_utc: datetime, soc: float, capacity_kw: float) -> tuple[float, float, str]:
    """Returns (active_power_kw, new_soc_pct, state) for a BESS asset.

    Positive power = discharging (export), negative = charging (import).
    """
    h_sast = (ts_utc.hour + ts_utc.minute / 60.0) + SAST_OFFSET_H

    dt_h = TELEMETRY_INTERVAL_MIN / 60.0

    # Off-peak charge window: 23:00–06:00 and solar peak 09:30–13:30
    if (h_sast >= 23 or h_sast < 6):
        # Overnight slow charge from grid
        if soc < 80.0:
            charge_rate = capacity_kw * random.uniform(0.25, 0.40)
            delta = (charge_rate * dt_h / (capacity_kw * 4)) * 100  # approx
            new_soc = min(95.0, soc + delta)
            return -charge_rate, new_soc, "charging"
        else:
            return 0.0, soc, "idle"

    elif 9.5 <= h_sast < 13.5:
        # Solar peak charging
        if soc < 92.0:
            charge_rate = capacity_kw * random.uniform(0.55, 0.90)
            delta = (charge_rate * dt_h / (capacity_kw * 4)) * 100
            new_soc = min(95.0, soc + delta)
            return -charge_rate, new_soc, "charging"
        else:
            return 0.0, soc, "idle"

    elif 17.0 <= h_sast < 21.0:
        # Peak-demand discharge window
        if soc > 18.0:
            discharge_rate = capacity_kw * random.uniform(0.50, 0.85)
            delta = (discharge_rate * dt_h / (capacity_kw * 4)) * 100
            new_soc = max(10.0, soc - delta)
            return discharge_rate, new_soc, "discharging"
        else:
            return 0.0, soc, "idle"

    else:
        # Transition periods — gentle drift
        if soc < 30.0:
            charge_rate = capacity_kw * random.uniform(0.15, 0.30)
            delta = (charge_rate * dt_h / (capacity_kw * 4)) * 100
            new_soc = min(40.0, soc + delta)
            return -charge_rate, new_soc, "charging"
        return 0.0, soc + random.gauss(0, 0.05), "idle"


def _ev_load(ts_utc: datetime, capacity_kw: float, session_active: bool,
             session_energy: float) -> tuple[float, float, bool, str]:
    """Returns (power_kw, session_energy_kwh, session_active, state)."""
    h_sast = (ts_utc.hour + ts_utc.minute / 60.0) + SAST_OFFSET_H

    # Morning commute peak: 07:00–09:30
    # Evening peak: 17:00–20:30
    in_peak = (7.0 <= h_sast < 9.5) or (17.0 <= h_sast < 20.5)
    # Midday trickle: 11:00–14:00 (40% probability of session)
    in_midday = 11.0 <= h_sast < 14.0

    dt_h = TELEMETRY_INTERVAL_MIN / 60.0

    if session_active:
        # Session ends randomly (avg session ~45 min for DC fast)
        end_prob = 0.022  # ~1/45 chance per 5-min tick to end
        if random.random() < end_prob or not (in_peak or in_midday):
            return 0.0, session_energy, False, "idle"
        power = capacity_kw * random.uniform(0.55, 0.95)
        session_energy += power * dt_h
        return power, session_energy, True, "charging"
    else:
        # Start a new session
        if in_peak and random.random() < 0.55:
            power = capacity_kw * random.uniform(0.60, 0.95)
            se = power * dt_h
            return power, se, True, "charging"
        elif in_midday and random.random() < 0.30:
            power = capacity_kw * random.uniform(0.40, 0.75)
            se = power * dt_h
            return power, se, True, "charging"
        return 0.0, 0.0, False, "idle"


# ── Partition helper ───────────────────────────────────────────────────────────

def ensure_partitions(db, start_date: date, end_date: date) -> None:
    """Create weekly der_telemetry partitions covering [start_date, end_date]."""
    # Find Monday of the start week
    current = start_date - timedelta(days=start_date.weekday())
    while current <= end_date:
        week_end = current + timedelta(days=7)
        pname = f"der_telemetry_{current.strftime('%G_%V').replace('-', '_')}"
        db.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {pname} "
                f"PARTITION OF der_telemetry "
                f"FOR VALUES FROM ('{current}') TO ('{week_end}');"
            )
        )
        current = week_end
    db.commit()
    print("  Partitions ensured.")


# ── Seed functions ─────────────────────────────────────────────────────────────

_TYPE_CATALOG = [
    ("rooftop_pv",       "pv",        "Rooftop PV",           1,     50),
    ("ground_mount_pv",  "pv",        "Ground-Mount PV",      100,   50000),
    ("floating_pv",      "pv",        "Floating PV",          100,   5000),
    ("carport_pv",       "pv",        "Carport PV",           5,     500),
    ("lithium_bess",     "bess",      "Lithium-Ion BESS",     5,     10000),
    ("lead_acid_bess",   "bess",      "Lead-Acid BESS",       5,     500),
    ("flow_bess",        "bess",      "Flow Battery BESS",    100,   10000),
    ("hybrid_bess",      "bess",      "Hybrid BESS",          5,     1000),
    ("ac_l2",            "ev",        "AC Level-2 Charger",   7,     22),
    ("dc_fast",          "ev",        "DC Fast Charger",      50,    150),
    ("dc_ultra",         "ev",        "DC Ultra-Fast Charger",150,   350),
    ("v2g",              "ev",        "V2G Charger",          7,     50),
    ("microgrid_hybrid", "microgrid", "Hybrid Microgrid",     50,    5000),
    ("microgrid_diesel", "microgrid", "Diesel Microgrid",     50,    5000),
]


def seed_type_catalog(db) -> None:
    for code, cat, dn, kmin, kmax in _TYPE_CATALOG:
        db.execute(
            text(
                """
                INSERT INTO der_type_catalog
                    (code, category, display_name, typical_kw_min, typical_kw_max, default_unit)
                VALUES
                    (:code, :cat, :dn, :kmin, :kmax, 'kW')
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "cat": cat, "dn": dn, "kmin": kmin, "kmax": kmax},
        )
    db.commit()
    print(f"  Type catalog: {len(_TYPE_CATALOG)} types upserted.")


def seed_consumers(db) -> None:
    for c in CONSUMERS:
        db.execute(
            text(
                """
                INSERT INTO der_consumer
                    (id, name, account_no, email, phone, premise_address,
                     lat, lon, tariff_code, status)
                VALUES
                    (:id, :name, :account_no, :email, :phone, :premise_address,
                     :lat, :lon, :tariff_code, 'active')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            c,
        )
    db.commit()
    print(f"  Consumers: {len(CONSUMERS)} upserted.")


def seed_assets(db) -> list[str]:
    # Pull a feeder_id from the network to assign assets to (if any exist)
    feeder_ids: list[str] = []
    try:
        rows = db.execute(text("SELECT id FROM feeders ORDER BY id LIMIT 5")).fetchall()
        feeder_ids = [r[0] for r in rows]
    except Exception:
        db.rollback()

    inserted = 0
    for i, a in enumerate(ASSETS):
        fid = feeder_ids[i % len(feeder_ids)] if feeder_ids else None
        db.execute(
            text(
                """
                INSERT INTO der_asset
                    (id, type, type_code, name, consumer_id, capacity_kw, capacity_kwh,
                     lat, lon, feeder_id)
                VALUES
                    (:id, :type, :type_code, :name, :consumer_id, :capacity_kw, :capacity_kwh,
                     :lat, :lon, :feeder_id)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {**a, "feeder_id": fid},
        )
        inserted += 1

    db.commit()
    print(f"  DER assets: {inserted} upserted.")
    return [a["id"] for a in ASSETS]


def seed_inverters(db) -> None:
    today = date.today()
    installed = today - timedelta(days=random.randint(180, 730))
    warranty = installed + timedelta(days=365 * 5)

    count = 0
    for asset_id, inv_list in INVERTERS.items():
        for inv in inv_list:
            inv_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"inv-{inv['serial_number']}"))
            db.execute(
                text(
                    """
                    INSERT INTO der_inverter
                        (id, asset_id, manufacturer, model, serial_number,
                         firmware_version, rated_ac_kw, rated_dc_kw,
                         num_mppt_trackers, num_strings, phase_config,
                         ac_voltage_nominal_v, comms_protocol,
                         installation_date, warranty_expires, status)
                    VALUES
                        (:id, :asset_id, :manufacturer, :model, :serial_number,
                         :firmware_version, :rated_ac_kw, :rated_dc_kw,
                         :num_mppt_trackers, :num_strings, :phase_config,
                         400.0, 'Modbus/TCP',
                         :installation_date, :warranty_expires, 'online')
                    ON CONFLICT (serial_number) DO NOTHING
                    """
                ),
                {
                    **inv,
                    "id": inv_id,
                    "asset_id": asset_id,
                    "installation_date": installed,
                    "warranty_expires": warranty,
                },
            )
            count += 1
    db.commit()
    print(f"  Inverters: {count} upserted.")


def _batch_insert_telemetry(db, rows: list[dict]) -> None:
    if not rows:
        return
    # Use a unique index on (asset_id, ts) to make re-runs idempotent.
    # The partitioned table has no natural unique constraint on (asset_id, ts),
    # so we delete-then-insert in a way that's safe: caller deletes the window first.
    db.execute(
        text(
            """
            INSERT INTO der_telemetry
                (asset_id, ts, state, active_power_kw, reactive_power_kvar,
                 soc_pct, session_energy_kwh, achievement_rate_pct, curtailment_pct)
            VALUES
                (:asset_id, :ts, :state, :active_power_kw, :reactive_power_kvar,
                 :soc_pct, :session_energy_kwh, :achievement_rate_pct, :curtailment_pct)
            """
        ),
        rows,
    )


def seed_telemetry(db) -> None:
    # Wipe existing seed rows so re-runs don't stack (partitioned PK has BIGSERIAL,
    # no natural unique constraint on (asset_id, ts)).
    asset_ids = [a["id"] for a in ASSETS]
    db.execute(
        text("DELETE FROM der_telemetry WHERE asset_id IN :aids").bindparams(
            __import__("sqlalchemy").bindparam("aids", expanding=True)
        ),
        {"aids": asset_ids},
    )
    db.commit()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # Align to previous 5-min boundary
    now = now - timedelta(minutes=now.minute % TELEMETRY_INTERVAL_MIN)

    start = now - timedelta(days=HISTORY_DAYS)
    n_steps = int((now - start).total_seconds() / (TELEMETRY_INTERVAL_MIN * 60)) + 1

    BATCH = 500

    for asset in ASSETS:
        aid = asset["id"]
        atype = asset["type"]
        cap_kw = float(asset["capacity_kw"])
        cap_kwh = float(asset["capacity_kwh"]) if asset["capacity_kwh"] else cap_kw * 4

        rows: list[dict] = []

        # Per-day cloud curve lookup
        steps_per_day = int(24 * 60 / TELEMETRY_INTERVAL_MIN)
        day_clouds: dict[int, list[float]] = {}

        # BESS state
        soc = random.uniform(50.0, 75.0)

        # EV state
        ev_session_active = False
        ev_session_energy = 0.0

        for step in range(n_steps):
            ts = start + timedelta(minutes=step * TELEMETRY_INTERVAL_MIN)
            day_idx = (ts - start).days

            if atype == "pv":
                if day_idx not in day_clouds:
                    day_clouds[day_idx] = _daily_cloud_curve(day_idx, steps_per_day)
                step_in_day = int((ts.hour * 60 + ts.minute) / TELEMETRY_INTERVAL_MIN)
                cloud = day_clouds[day_idx][step_in_day % steps_per_day]

                frac = _solar_fraction(ts, cloud)
                power = round(cap_kw * 0.97 * frac, 3)
                rp = round(power * 0.05, 3)  # small reactive component

                h_sast = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
                if h_sast < SUNRISE_H or h_sast >= SUNSET_H:
                    state = "idle"
                    achiev = None
                else:
                    state = "online"
                    expected = cap_kw * 0.97 * max(0, math.sin(
                        math.pi * (h_sast - SUNRISE_H) / (SUNSET_H - SUNRISE_H)) ** 1.2)
                    achiev = round(min(110.0, (power / expected * 100) if expected > 1 else 100.0), 2)

                rows.append({
                    "asset_id": aid, "ts": ts,
                    "state": state,
                    "active_power_kw": power,
                    "reactive_power_kvar": rp if state == "online" else None,
                    "soc_pct": None,
                    "session_energy_kwh": None,
                    "achievement_rate_pct": achiev,
                    "curtailment_pct": None,
                })

            elif atype == "bess":
                power, soc, state = _bess_profile(ts, soc, cap_kw)
                rows.append({
                    "asset_id": aid, "ts": ts,
                    "state": state,
                    "active_power_kw": round(power, 3),
                    "reactive_power_kvar": round(power * 0.03, 3),
                    "soc_pct": round(soc, 2),
                    "session_energy_kwh": None,
                    "achievement_rate_pct": None,
                    "curtailment_pct": None,
                })

            elif atype == "ev":
                power, ev_session_energy, ev_session_active, state = _ev_load(
                    ts, cap_kw, ev_session_active, ev_session_energy
                )
                # Reset accumulated session energy when idle
                se = round(ev_session_energy, 3) if ev_session_active else None
                if not ev_session_active:
                    ev_session_energy = 0.0
                rows.append({
                    "asset_id": aid, "ts": ts,
                    "state": state,
                    "active_power_kw": round(power, 3),
                    "reactive_power_kvar": round(power * 0.05, 3) if power > 0 else None,
                    "soc_pct": None,
                    "session_energy_kwh": se,
                    "achievement_rate_pct": None,
                    "curtailment_pct": None,
                })

            if len(rows) >= BATCH:
                _batch_insert_telemetry(db, rows)
                db.commit()
                rows = []

        if rows:
            _batch_insert_telemetry(db, rows)
            db.commit()

        print(f"    {aid}: {n_steps} telemetry rows inserted.")

    print(f"  Telemetry complete ({n_steps * len(ASSETS):,} rows across {len(ASSETS)} assets).")


def seed_metrology(db) -> None:
    """Populate der_metrology (15-min interval) and der_metrology_daily (90-day rollup)."""
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    today = now_utc.date()

    # ── Daily rollup: 90 days ──────────────────────────────────────────────────
    daily_count = 0
    for asset in ASSETS:
        aid = asset["id"]
        atype = asset["type"]
        cap_kw = float(asset["capacity_kw"])
        cap_kwh = float(asset["capacity_kwh"]) if asset["capacity_kwh"] else cap_kw * 4

        for day_offset in range(METROLOGY_DAYS, 0, -1):
            d = today - timedelta(days=day_offset)
            rng = random.Random(hash(aid) ^ day_offset)

            if atype == "pv":
                cloud = rng.uniform(0.55, 1.0)
                # Approximate daily generation from numerical integration of bell curve
                # integral(sin(pi*x/12)^1.2, 0, 12) ≈ 7.0 (normalised hours)
                gen = round(cap_kw * 0.97 * cloud * rng.uniform(5.5, 8.5), 4)
                exported = round(gen * rng.uniform(0.55, 0.80), 4)
                self_consumed = round(gen - exported, 4)
                peak = round(cap_kw * 0.97 * cloud * rng.uniform(0.75, 1.0), 3)
                eq_hours = round(gen / cap_kw if cap_kw else 0, 3)
                achiev = round(min(105.0, gen / (cap_kw * 6.5) * 100), 2)
                row = {
                    "asset_id": aid, "date": d,
                    "kwh_generated": gen, "kwh_exported": exported,
                    "kwh_imported": 0.0, "kwh_self_consumed": self_consumed,
                    "peak_output_kw": peak, "equivalent_hours": eq_hours,
                    "achievement_pct": achiev,
                    "reading_count": 96, "estimated_count": rng.randint(0, 3),
                }
            elif atype == "bess":
                charged = round(cap_kwh * rng.uniform(0.35, 0.70), 4)
                discharged = round(charged * rng.uniform(0.88, 0.96), 4)
                row = {
                    "asset_id": aid, "date": d,
                    "kwh_generated": discharged,
                    "kwh_exported": discharged,
                    "kwh_imported": charged,
                    "kwh_self_consumed": 0.0,
                    "peak_output_kw": round(cap_kw * rng.uniform(0.55, 0.90), 3),
                    "equivalent_hours": round(discharged / cap_kw if cap_kw else 0, 3),
                    "achievement_pct": None,
                    "reading_count": 96, "estimated_count": 0,
                }
            else:  # ev
                sessions = rng.randint(4, 14)
                avg_session_kwh = cap_kw * rng.uniform(0.4, 0.8) * 0.75
                total_kwh = round(sessions * avg_session_kwh, 4)
                row = {
                    "asset_id": aid, "date": d,
                    "kwh_generated": 0.0,
                    "kwh_exported": 0.0,
                    "kwh_imported": total_kwh,
                    "kwh_self_consumed": 0.0,
                    "peak_output_kw": round(cap_kw * rng.uniform(0.55, 0.95), 3),
                    "equivalent_hours": round(total_kwh / cap_kw if cap_kw else 0, 3),
                    "achievement_pct": None,
                    "reading_count": 96, "estimated_count": 0,
                }

            db.execute(
                text(
                    """
                    INSERT INTO der_metrology_daily
                        (asset_id, date, kwh_generated, kwh_exported, kwh_imported,
                         kwh_self_consumed, peak_output_kw, equivalent_hours,
                         achievement_pct, reading_count, estimated_count, source)
                    VALUES
                        (:asset_id, :date, :kwh_generated, :kwh_exported, :kwh_imported,
                         :kwh_self_consumed, :peak_output_kw, :equivalent_hours,
                         :achievement_pct, :reading_count, :estimated_count, 'DER_TELEMETRY')
                    ON CONFLICT (asset_id, date) DO UPDATE SET
                        kwh_generated    = EXCLUDED.kwh_generated,
                        kwh_exported     = EXCLUDED.kwh_exported,
                        kwh_imported     = EXCLUDED.kwh_imported,
                        kwh_self_consumed = EXCLUDED.kwh_self_consumed,
                        peak_output_kw   = EXCLUDED.peak_output_kw,
                        equivalent_hours = EXCLUDED.equivalent_hours,
                        achievement_pct  = EXCLUDED.achievement_pct,
                        updated_at       = now()
                    """
                ),
                row,
            )
            daily_count += 1

        db.commit()

    print(f"  Daily metrology: {daily_count} rows upserted.")

    # ── Interval reads: last 30 days at 15-min ─────────────────────────────────
    interval_start = now_utc - timedelta(days=30)
    interval_start = interval_start.replace(minute=(interval_start.minute // 15) * 15,
                                            second=0, microsecond=0)
    interval_steps = int((now_utc - interval_start).total_seconds() / 900)  # 15-min

    interval_count = 0
    BATCH = 200

    for asset in ASSETS:
        aid = asset["id"]
        atype = asset["type"]
        cap_kw = float(asset["capacity_kw"])

        rows: list[dict] = []
        steps_per_day = int(24 * 60 / 15)
        day_clouds: dict[int, list[float]] = {}

        for step in range(interval_steps):
            ts = interval_start + timedelta(minutes=step * 15)
            day_idx = (ts - interval_start).days

            if atype == "pv":
                if day_idx not in day_clouds:
                    day_clouds[day_idx] = _daily_cloud_curve(day_idx + 500, steps_per_day)
                step_in_day = int((ts.hour * 60 + ts.minute) / 15)
                cloud = day_clouds[day_idx][step_in_day % steps_per_day]
                frac = _solar_fraction(ts, cloud)
                power_kw = cap_kw * 0.97 * frac
                energy_kwh = round(power_kw * (15 / 60), 4)
                exported = round(energy_kwh * 0.65, 4)
                rows.append({
                    "asset_id": aid, "ts": ts,
                    "energy_generated_kwh": energy_kwh,
                    "energy_exported_kwh": exported,
                    "energy_imported_kwh": 0.0,
                    "energy_self_consumed_kwh": round(energy_kwh - exported, 4),
                    "voltage_avg": round(random.uniform(228.0, 242.0), 2),
                    "current_avg": round(power_kw * 1000 / (230 * 3**0.5 * 3) if power_kw > 0 else 0.0, 3),
                    "power_factor": round(random.uniform(0.96, 0.999), 3),
                    "frequency_hz": round(random.uniform(49.95, 50.05), 3),
                    "quality": "valid",
                })
            elif atype == "bess":
                h_sast = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
                if 9.5 <= h_sast < 13.5:
                    imported = round(cap_kw * random.uniform(0.5, 0.8) * (15 / 60), 4)
                    exported = 0.0
                elif 17.0 <= h_sast < 21.0:
                    exported = round(cap_kw * random.uniform(0.5, 0.8) * (15 / 60), 4)
                    imported = 0.0
                else:
                    imported = exported = 0.0
                rows.append({
                    "asset_id": aid, "ts": ts,
                    "energy_generated_kwh": exported,
                    "energy_exported_kwh": exported,
                    "energy_imported_kwh": imported,
                    "energy_self_consumed_kwh": 0.0,
                    "voltage_avg": round(random.uniform(228.0, 242.0), 2),
                    "current_avg": round((exported + imported) * 1000 / (230 * 3**0.5 * 3), 3),
                    "power_factor": round(random.uniform(0.97, 0.999), 3),
                    "frequency_hz": round(random.uniform(49.95, 50.05), 3),
                    "quality": "valid",
                })
            else:  # ev
                h_sast = (ts.hour + ts.minute / 60.0) + SAST_OFFSET_H
                in_peak = (7.0 <= h_sast < 9.5) or (17.0 <= h_sast < 20.5)
                power = cap_kw * random.uniform(0.4, 0.85) if in_peak and random.random() < 0.6 else 0.0
                imported = round(power * (15 / 60), 4)
                rows.append({
                    "asset_id": aid, "ts": ts,
                    "energy_generated_kwh": 0.0,
                    "energy_exported_kwh": 0.0,
                    "energy_imported_kwh": imported,
                    "energy_self_consumed_kwh": 0.0,
                    "voltage_avg": round(random.uniform(228.0, 242.0), 2),
                    "current_avg": round(power * 1000 / (230 * 3**0.5 * 3) if power > 0 else 0.0, 3),
                    "power_factor": round(random.uniform(0.97, 0.999), 3),
                    "frequency_hz": round(random.uniform(49.95, 50.05), 3),
                    "quality": "valid",
                })

            if len(rows) >= BATCH:
                db.execute(
                    text(
                        """
                        INSERT INTO der_metrology
                            (asset_id, ts, energy_generated_kwh, energy_exported_kwh,
                             energy_imported_kwh, energy_self_consumed_kwh,
                             voltage_avg, current_avg, power_factor, frequency_hz,
                             quality, source, is_estimated)
                        VALUES
                            (:asset_id, :ts, :energy_generated_kwh, :energy_exported_kwh,
                             :energy_imported_kwh, :energy_self_consumed_kwh,
                             :voltage_avg, :current_avg, :power_factor, :frequency_hz,
                             :quality, 'DER_TELEMETRY', false)
                        ON CONFLICT (asset_id, ts) DO NOTHING
"""
                    ),
                    rows,
                )
                db.commit()
                interval_count += len(rows)
                rows = []

        if rows:
            db.execute(
                text(
                    """
                    INSERT INTO der_metrology
                        (asset_id, ts, energy_generated_kwh, energy_exported_kwh,
                         energy_imported_kwh, energy_self_consumed_kwh,
                         voltage_avg, current_avg, power_factor, frequency_hz,
                         quality, source, is_estimated)
                    VALUES
                        (:asset_id, :ts, :energy_generated_kwh, :energy_exported_kwh,
                         :energy_imported_kwh, :energy_self_consumed_kwh,
                         :voltage_avg, :current_avg, :power_factor, :frequency_hz,
                         :quality, 'DER_TELEMETRY', false)
                    ON CONFLICT (asset_id, ts) DO NOTHING
                    """
                ),
                rows,
            )
            db.commit()
            interval_count += len(rows)

    print(f"  Interval metrology: {interval_count:,} rows upserted.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=HISTORY_DAYS)).date()
        end_date = (now + timedelta(days=1)).date()

        print("DER historical seed starting...")

        print("  Ensuring weekly partitions...")
        ensure_partitions(db, start_date, end_date)

        print("  Seeding type catalog...")
        seed_type_catalog(db)

        print("  Seeding consumers...")
        seed_consumers(db)

        print("  Seeding DER assets...")
        seed_assets(db)

        print("  Seeding inverters...")
        seed_inverters(db)

        print(f"  Seeding {HISTORY_DAYS}-day telemetry (5-min intervals)...")
        seed_telemetry(db)

        print(f"  Seeding {METROLOGY_DAYS}-day metrology...")
        seed_metrology(db)

        print("\nDER historical seed complete.")
        print(f"  Consumers:  {len(CONSUMERS)}")
        print(f"  Assets:     {len(ASSETS)} ({sum(1 for a in ASSETS if a['type']=='pv')} PV, "
              f"{sum(1 for a in ASSETS if a['type']=='bess')} BESS, "
              f"{sum(1 for a in ASSETS if a['type']=='ev')} EV)")
        inv_count = sum(len(v) for v in INVERTERS.values())
        print(f"  Inverters:  {inv_count}")
        steps = int(HISTORY_DAYS * 24 * 60 / TELEMETRY_INTERVAL_MIN)
        print(f"  Telemetry:  ~{steps * len(ASSETS):,} rows ({HISTORY_DAYS}d × {TELEMETRY_INTERVAL_MIN}min)")
        print(f"  Metrology:  ~{int(30 * 96 * len(ASSETS)):,} interval rows + "
              f"{METROLOGY_DAYS * len(ASSETS):,} daily rows")

    finally:
        db.close()


if __name__ == "__main__":
    main()
