"""Seed demo-grade metrology + outage data against the live DB.

Run once (idempotent — skips if data already present) against the `smoc_ems`
database inside the `smoc_backend` container to populate:

  * meter_reading_interval  — last 3 days, 30-min intervals
  * meter_reading_daily     — last 35 days
  * meter_reading_monthly   — last 3 months
  * outage_incidents        — 6 demo incidents across the lifecycle

Invocation (inside container):
    python -m scripts.seed_demo_data
"""
from __future__ import annotations

import math
import random
import sys
import os
from datetime import datetime, timedelta, timezone, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
import app.models  # ensure all models registered

from app.models.meter import Meter, Feeder
from app.models.metrology import (
    MeterReadingInterval,
    MeterReadingDaily,
    MeterReadingMonthly,
)
from app.models.outage import OutageIncident, OutageStatus


random.seed(42)


def _tariff_profile(tariff_class: str, hour: int) -> float:
    """Return a diurnal demand (kW) factor for a class + hour."""
    if tariff_class == "Commercial":
        if hour < 7:
            return 0.3
        if hour < 9:
            return 1.2
        if hour < 18:
            return 2.4 + math.sin((hour - 13) / 3) * 0.4
        if hour < 21:
            return 1.6
        return 0.4
    if tariff_class == "Residential":
        if hour < 6:
            return 0.4
        if hour < 9:
            return 1.4 + (hour - 6) * 0.3
        if hour < 17:
            return 0.9
        if hour < 20:
            return 2.2 + (hour - 17) * 0.3
        return 1.0
    # prepaid/default
    if hour < 6:
        return 0.3
    if hour < 9:
        return 1.0
    if hour < 17:
        return 0.7
    if hour < 21:
        return 1.6
    return 0.8


def seed_intervals(db, meters, days: int = 3) -> int:
    """30-min interval rows — subset of meters to keep volume manageable."""
    existing = db.query(MeterReadingInterval).count()
    if existing > 0:
        print(f"  intervals: already {existing} rows, skipping")
        return 0

    # Cap to first 200 meters — plenty for demo visuals, avoids 200K+ rows.
    sample = meters[:200]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    slots = days * 48  # 48 half-hours/day

    rows = []
    for meter in sample:
        base = {
            "Commercial": random.uniform(3.0, 8.0),
            "Residential": random.uniform(0.8, 2.2),
        }.get(meter.tariff_class, random.uniform(0.6, 1.8))

        for slot in range(slots):
            ts = now - timedelta(minutes=30 * slot)
            factor = _tariff_profile(meter.tariff_class, ts.hour)
            noise = random.uniform(0.9, 1.12)
            demand = round(base * factor * noise, 3)
            energy = round(demand * 0.5, 4)  # 30-min slot
            rows.append(
                dict(
                    meter_serial=meter.serial,
                    ts=ts,
                    channel=0,
                    value=demand,
                    quality="valid",
                    source="MDMS_VEE",
                    energy_kwh=energy,
                    energy_export_kwh=round(random.uniform(0, 0.05), 4),
                    demand_kw=demand,
                    voltage=round(random.uniform(225, 238), 1),
                    current=round(demand * 1000 / 230, 2),
                    power_factor=round(random.uniform(0.88, 0.98), 3),
                    frequency=50.0,
                    thd=round(random.uniform(1.5, 4.5), 1),
                    is_estimated=False,
                    is_edited=False,
                    is_validated=True,
                    source_priority=10,
                )
            )

    # Bulk insert in chunks
    from sqlalchemy import insert
    chunk = 5000
    inserted = 0
    for i in range(0, len(rows), chunk):
        db.execute(insert(MeterReadingInterval), rows[i : i + chunk])
        db.commit()
        inserted += len(rows[i : i + chunk])
    print(f"  intervals: {inserted} rows inserted")
    return inserted


def seed_daily(db, meters, days: int = 35) -> int:
    existing = db.query(MeterReadingDaily).count()
    if existing > 0:
        print(f"  daily: already {existing} rows, skipping")
        return 0

    today = datetime.now(timezone.utc).date()
    from sqlalchemy import insert

    rows = []
    for meter in meters:
        daily_base = {
            "Commercial": random.uniform(60, 180),
            "Residential": random.uniform(10, 30),
        }.get(meter.tariff_class, random.uniform(4, 14))

        for d_off in range(days):
            day = today - timedelta(days=d_off)
            weekday_mult = 0.85 if day.weekday() >= 5 else 1.0
            kwh = round(daily_base * random.uniform(0.85, 1.15) * weekday_mult, 2)
            peak = round(kwh * random.uniform(0.08, 0.12), 2)
            rows.append(
                dict(
                    meter_serial=meter.serial,
                    date=day,
                    kwh_import=kwh,
                    kwh_export=round(random.uniform(0, kwh * 0.03), 3),
                    max_demand_kw=peak,
                    min_voltage=round(random.uniform(224, 228), 1),
                    max_voltage=round(random.uniform(236, 242), 1),
                    avg_pf=round(random.uniform(0.90, 0.97), 3),
                    reading_count=48,
                    estimated_count=random.randint(0, 2),
                    source="MDMS_VEE",
                    source_mix={"MDMS_VEE": 48},
                )
            )

    chunk = 5000
    inserted = 0
    for i in range(0, len(rows), chunk):
        db.execute(insert(MeterReadingDaily), rows[i : i + chunk])
        db.commit()
        inserted += len(rows[i : i + chunk])
    print(f"  daily: {inserted} rows inserted")
    return inserted


def seed_monthly(db, meters, months: int = 3) -> int:
    existing = db.query(MeterReadingMonthly).count()
    if existing > 0:
        print(f"  monthly: already {existing} rows, skipping")
        return 0

    today = datetime.now(timezone.utc).date()
    from sqlalchemy import insert

    rows = []
    for meter in meters:
        base = {
            "Commercial": random.uniform(1800, 5200),
            "Residential": random.uniform(300, 900),
        }.get(meter.tariff_class, random.uniform(120, 420))

        for m_off in range(months):
            # Compute year-month by subtracting months
            y = today.year
            m = today.month - m_off
            while m <= 0:
                m += 12
                y -= 1
            ym = f"{y:04d}-{m:02d}"
            kwh = round(base * random.uniform(0.88, 1.12), 2)
            rows.append(
                dict(
                    meter_serial=meter.serial,
                    year_month=ym,
                    kwh_import=kwh,
                    kwh_export=round(random.uniform(0, kwh * 0.02), 2),
                    max_demand_kw=round(kwh / 400 * random.uniform(0.9, 1.15), 2),
                    avg_pf=round(random.uniform(0.90, 0.97), 3),
                    reading_days=30,
                    vee_billing_kwh=kwh,
                    reconciliation_delta_pct=round(random.uniform(-0.5, 0.5), 2),
                    source="MDMS_VEE",
                    source_mix={"MDMS_VEE": 30},
                )
            )

    chunk = 5000
    inserted = 0
    for i in range(0, len(rows), chunk):
        db.execute(insert(MeterReadingMonthly), rows[i : i + chunk])
        db.commit()
        inserted += len(rows[i : i + chunk])
    print(f"  monthly: {inserted} rows inserted")
    return inserted


def seed_outages(db) -> int:
    existing = db.query(OutageIncident).count()
    if existing > 0:
        print(f"  outages: already {existing} rows, skipping")
        return 0

    feeders = db.query(Feeder).order_by(Feeder.id).limit(12).all()
    if not feeders:
        print("  outages: no feeders in DB, aborting")
        return 0

    now = datetime.now(timezone.utc)
    specs = [
        # (status, started_offset_hours, cause, affected, etr_offset, closed)
        (OutageStatus.DETECTED, 0.5, "LV feeder trip — overcurrent", 342, 2, False),
        (OutageStatus.CONFIRMED, 1.8, "Cable fault — suspected tree contact", 187, 3, False),
        (OutageStatus.DISPATCHED, 3.2, "Transformer overload", 512, 4, False),
        (OutageStatus.RESTORING, 5.5, "Pole-mounted fuse replaced", 95, 1, False),
        (OutageStatus.RESTORED, 22, "Planned maintenance — ring main unit swap", 220, 0, True),
        (OutageStatus.CLOSED, 72, "Storm damage — lightning strike", 630, 0, True),
    ]
    rows = []
    for i, (status, start_h, cause, affected, etr_h, closed) in enumerate(specs):
        feeder = feeders[i % len(feeders)]
        started = now - timedelta(hours=start_h)
        etr = started + timedelta(hours=etr_h + 2)
        inc = OutageIncident(
            status=status.value,
            feeder_id=feeder.id,
            started_at=started,
            confirmed_at=started + timedelta(minutes=6)
                if status != OutageStatus.DETECTED else None,
            dispatched_at=started + timedelta(minutes=22)
                if status in (OutageStatus.DISPATCHED, OutageStatus.RESTORING,
                              OutageStatus.RESTORED, OutageStatus.CLOSED) else None,
            restored_at=started + timedelta(hours=start_h - 0.2)
                if status in (OutageStatus.RESTORED, OutageStatus.CLOSED) else None,
            closed_at=now - timedelta(hours=1) if closed else None,
            etr_at=etr,
            affected_customers=affected,
            cause=cause,
            notes=f"Incident #{i+1} — {cause}",
            created_by="supervisor",
        )
        db.add(inc)
        rows.append(inc)

    db.commit()
    print(f"  outages: {len(rows)} incidents inserted")
    return len(rows)


def main():
    print("Seeding demo metrology + outage data...")
    db = SessionLocal()
    try:
        meters = db.query(Meter).all()
        if not meters:
            print("No meters in DB; run seed_data.py first.")
            return
        print(f"  meters in DB: {len(meters)}")
        seed_daily(db, meters)
        seed_monthly(db, meters)
        seed_intervals(db, meters)
        seed_outages(db)
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
