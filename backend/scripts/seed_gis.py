"""Seed GIS-specific tables (spec 014-gis-postgis MVP).

Idempotent — skips seeding if rows already exist.

Populates:
  * service_lines: straight LineString meter.geom -> transformer.geom
  * outage_areas : 2-3 sample polygon outages around existing transformers

Runnable standalone:
    python scripts/seed_gis.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.base import SessionLocal


SERVICE_LINES_SQL = """
INSERT INTO service_lines (meter_serial, transformer_id, geom, length_m, created_at)
SELECT m.serial,
       m.transformer_id,
       ST_SetSRID(ST_MakeLine(m.geom, t.geom), 4326) AS geom,
       ST_Length(ST_MakeLine(m.geom, t.geom)::geography) AS length_m,
       NOW()
FROM meters m
JOIN transformers t ON t.id = m.transformer_id
WHERE m.geom IS NOT NULL AND t.geom IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM service_lines sl WHERE sl.meter_serial = m.serial
  )
"""


def seed_service_lines(db):
    result = db.execute(text(SERVICE_LINES_SQL))
    db.commit()
    print(f"  service_lines inserted: {result.rowcount}")


def seed_outage_areas(db):
    existing = db.execute(text("SELECT COUNT(*) FROM outage_areas")).scalar() or 0
    if existing:
        print(f"  outage_areas already seeded ({existing} rows); skipping")
        return
    # Sample ~1-2km radius circles around 3 transformers, approximated as octagons.
    db.execute(text(
        """
        INSERT INTO outage_areas (network_event_id, affected_customers, started_at, polygon_geom)
        SELECT NULL,
               (SELECT COUNT(*) FROM meters m WHERE m.transformer_id = t.id) AS affected_customers,
               NOW() - INTERVAL '2 hours',
               ST_SetSRID(ST_Buffer(t.geom::geography, 500)::geometry, 4326)  -- 500m buffer
        FROM transformers t
        WHERE t.geom IS NOT NULL
        ORDER BY t.id
        LIMIT 3
        """
    ))
    db.commit()
    count = db.execute(text("SELECT COUNT(*) FROM outage_areas")).scalar()
    print(f"  outage_areas inserted: {count}")


def main():
    print("Seeding GIS data (spec 014-gis-postgis MVP)...")
    db = SessionLocal()
    try:
        seed_service_lines(db)
        seed_outage_areas(db)
        print("GIS seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
