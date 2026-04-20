"""metrology reading tables: interval / daily / monthly

Revision ID: 20260418_0002
Revises: 20260418_0001
Create Date: 2026-04-18

Creates the three new metrology tables that feed /energy/* and /reports/*.
Follow-up (TODO 013-mvp-phase2): convert meter_reading_interval into a native
monthly-partitioned table; MVP uses a single table with composite PK + index.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260418_0002"
down_revision: Union[str, None] = "20260418_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meter_reading_interval",
        sa.Column("meter_serial", sa.String(50), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.Integer, nullable=False, server_default="0"),
        sa.Column("value", sa.Float, nullable=False, server_default="0"),
        sa.Column("quality", sa.String(16), nullable=False, server_default="raw"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("energy_kwh", sa.Float, nullable=True),
        sa.Column("energy_export_kwh", sa.Float, nullable=True),
        sa.Column("demand_kw", sa.Float, nullable=True),
        sa.Column("voltage", sa.Float, nullable=True),
        sa.Column("current", sa.Float, nullable=True),
        sa.Column("power_factor", sa.Float, nullable=True),
        sa.Column("frequency", sa.Float, nullable=True),
        sa.Column("thd", sa.Float, nullable=True),
        sa.Column("is_estimated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_edited", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_validated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_priority", sa.SmallInteger, nullable=False, server_default="10"),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("kafka_partition", sa.SmallInteger, nullable=True),
        sa.Column("kafka_offset", sa.BigInteger, nullable=True),
        sa.PrimaryKeyConstraint("meter_serial", "ts", "channel", name="pk_mri_serial_ts_ch"),
        sa.CheckConstraint(
            "source IN ('HES_KAFKA','MDMS_VEE','MDMS_VEE_BACKFILL','HES_REST')",
            name="ck_mri_source",
        ),
        sa.CheckConstraint(
            "quality IN ('valid','estimated','failed','raw')",
            name="ck_mri_quality",
        ),
    )
    op.create_index("ix_mri_serial_ts", "meter_reading_interval", ["meter_serial", "ts"])
    op.create_index("ix_mri_ingested_at", "meter_reading_interval", ["ingested_at"])
    op.create_index("ix_mri_source", "meter_reading_interval", ["source"])

    op.create_table(
        "meter_reading_daily",
        sa.Column("meter_serial", sa.String(50), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("kwh_import", sa.Float, nullable=False, server_default="0"),
        sa.Column("kwh_export", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_demand_kw", sa.Float, nullable=True),
        sa.Column("min_voltage", sa.Float, nullable=True),
        sa.Column("max_voltage", sa.Float, nullable=True),
        sa.Column("avg_pf", sa.Float, nullable=True),
        sa.Column("reading_count", sa.Integer, nullable=True),
        sa.Column("estimated_count", sa.Integer, nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="MDMS_VEE"),
        sa.Column("source_mix", JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("meter_serial", "date", name="pk_mrd_serial_date"),
    )
    op.create_index("ix_mrd_serial_date", "meter_reading_daily", ["meter_serial", "date"])
    op.create_index("ix_mrd_date", "meter_reading_daily", ["date"])

    op.create_table(
        "meter_reading_monthly",
        sa.Column("meter_serial", sa.String(50), nullable=False),
        sa.Column("year_month", sa.CHAR(7), nullable=False),
        sa.Column("kwh_import", sa.Float, nullable=False, server_default="0"),
        sa.Column("kwh_export", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_demand_kw", sa.Float, nullable=True),
        sa.Column("avg_pf", sa.Float, nullable=True),
        sa.Column("reading_days", sa.Integer, nullable=True),
        sa.Column("vee_billing_kwh", sa.Float, nullable=True),
        sa.Column("reconciliation_delta_pct", sa.Float, nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="MDMS_VEE"),
        sa.Column("source_mix", JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("meter_serial", "year_month", name="pk_mrm_serial_month"),
    )
    op.create_index(
        "ix_mrm_serial_month", "meter_reading_monthly", ["meter_serial", "year_month"]
    )


def downgrade() -> None:
    op.drop_index("ix_mrm_serial_month", table_name="meter_reading_monthly")
    op.drop_table("meter_reading_monthly")
    op.drop_index("ix_mrd_date", table_name="meter_reading_daily")
    op.drop_index("ix_mrd_serial_date", table_name="meter_reading_daily")
    op.drop_table("meter_reading_daily")
    op.drop_index("ix_mri_source", table_name="meter_reading_interval")
    op.drop_index("ix_mri_ingested_at", table_name="meter_reading_interval")
    op.drop_index("ix_mri_serial_ts", table_name="meter_reading_interval")
    op.drop_table("meter_reading_interval")
