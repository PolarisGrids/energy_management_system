"""Spec 018 W2.T6 — dcu_health_cache (upsert per DCU; 5-minute TTL at read time).

Revision ID: d5_dcu_health_cache
Revises: d4_sensor_reading
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "d5_dcu_health_cache"
down_revision: Union[str, Sequence[str], None] = "d4_sensor_reading"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not sa_inspect(op.get_bind()).has_table("dcu_health_cache"):
        op.create_table(
            "dcu_health_cache",
            sa.Column("dcu_id", sa.String(length=100), primary_key=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("rssi_dbm", sa.Numeric(6, 2), nullable=True),
            sa.Column("success_rate_pct", sa.Numeric(5, 2), nullable=True),
            sa.Column("retry_count_last_hour", sa.Integer(), nullable=True),
            sa.Column("meters_connected", sa.Integer(), nullable=True),
            sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dcu_health_cache_status "
        "ON dcu_health_cache (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dcu_health_cache_last_reported_at "
        "ON dcu_health_cache (last_reported_at)"
    )


def downgrade() -> None:
    op.drop_index("ix_dcu_health_cache_last_reported_at", table_name="dcu_health_cache")
    op.drop_index("ix_dcu_health_cache_status", table_name="dcu_health_cache")
    op.drop_table("dcu_health_cache")
