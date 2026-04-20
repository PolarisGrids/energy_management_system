"""Enable PostGIS, add geom columns to existing asset tables, create GIS tables.

Covers spec 014-gis-postgis MVP scope (Setup + Foundational + US1).

Revision ID: a1_postgis_gis
Revises: 20260418_0002
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1_postgis_gis"
down_revision: Union[str, Sequence[str], None] = "20260418_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GEOM_POINT_TABLES = [
    ("meters", "geom", "Point"),
    ("transformers", "geom", "Point"),
    ("der_assets", "geom", "Point"),
    ("alarms", "geom", "Point"),
    ("network_events", "geom", "Point"),
]


def upgrade() -> None:
    # 1. Enable PostGIS ------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # 2. geom columns on existing tables ------------------------------------
    for table, col, geom_type in GEOM_POINT_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} geometry(Point, 4326)"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_geom ON {table} USING GIST ({col})"
        )

    op.execute(
        "ALTER TABLE feeders ADD COLUMN IF NOT EXISTS geom geometry(LineString, 4326)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feeders_geom ON feeders USING GIST (geom)"
    )

    # 3. Populate geom from lat/lon where possible --------------------------
    op.execute(
        """
        UPDATE meters SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE transformers SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE der_assets SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE alarms SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE network_events SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    )

    # 4. Synthesize feeder LineString from child transformer centroids -----
    #    Groups transformers by feeder and connects them in id-order.
    op.execute(
        """
        UPDATE feeders f
        SET geom = sub.line_geom
        FROM (
            SELECT feeder_id,
                   ST_SetSRID(ST_MakeLine(pt ORDER BY id), 4326) AS line_geom
            FROM (
                SELECT t.feeder_id,
                       t.id,
                       ST_MakePoint(t.longitude, t.latitude) AS pt
                FROM transformers t
                WHERE t.latitude IS NOT NULL AND t.longitude IS NOT NULL
            ) AS tx
            GROUP BY feeder_id
            HAVING COUNT(*) >= 2
        ) AS sub
        WHERE f.id = sub.feeder_id AND f.geom IS NULL
        """
    )

    # 5. New tables ---------------------------------------------------------
    op.create_table(
        "service_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meter_serial", sa.String(50), nullable=True, index=True),
        sa.Column("transformer_id", sa.Integer(), sa.ForeignKey("transformers.id"), nullable=True),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("cable_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "ALTER TABLE service_lines ADD COLUMN geom geometry(LineString, 4326)"
    )
    op.execute(
        "CREATE INDEX idx_service_lines_geom ON service_lines USING GIST (geom)"
    )

    op.create_table(
        "outage_areas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("network_event_id", sa.Integer(), nullable=True),
        sa.Column("affected_customers", sa.Integer(), default=0),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etr", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "ALTER TABLE outage_areas ADD COLUMN polygon_geom geometry(Polygon, 4326)"
    )
    op.execute(
        "CREATE INDEX idx_outage_areas_geom ON outage_areas USING GIST (polygon_geom)"
    )

    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("zone_type", sa.String(50), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("rules", postgresql.JSONB, nullable=True),
        sa.Column("orphan", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "ALTER TABLE zones ADD COLUMN geom geometry(Polygon, 4326)"
    )
    op.execute("CREATE INDEX idx_zones_geom ON zones USING GIST (geom)")

    op.create_table(
        "poles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feeder_id", sa.Integer(), sa.ForeignKey("feeders.id"), nullable=True),
        sa.Column("material", sa.String(50), nullable=True),
        sa.Column("height_m", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE poles ADD COLUMN geom geometry(Point, 4326)")
    op.execute("CREATE INDEX idx_poles_geom ON poles USING GIST (geom)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poles")
    op.execute("DROP TABLE IF EXISTS zones")
    op.execute("DROP TABLE IF EXISTS outage_areas")
    op.execute("DROP TABLE IF EXISTS service_lines")

    for table, col, _ in GEOM_POINT_TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_geom")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
    op.execute("DROP INDEX IF EXISTS idx_feeders_geom")
    op.execute("ALTER TABLE feeders DROP COLUMN IF EXISTS geom")

    # Keep PostGIS extension installed; do not drop on downgrade (destructive).
    # op.execute("DROP EXTENSION IF EXISTS postgis CASCADE")
