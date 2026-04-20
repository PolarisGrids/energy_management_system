"""Spec 018 W2.T7 — der_telemetry (weekly partition).

Revision ID: d6_der_telemetry
Revises: d5_dcu_health_cache
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa  # noqa: F401
from alembic import op

revision: str = "d6_der_telemetry"
down_revision: Union[str, Sequence[str], None] = "d5_dcu_health_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: dev DBs may have the non-partitioned flat table from a
    # prior `Base.metadata.create_all()` run. IF NOT EXISTS keeps the
    # migration a no-op in that case.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS der_telemetry (
            id                   BIGSERIAL      NOT NULL,
            asset_id             VARCHAR(100)   NOT NULL,
            ts                   TIMESTAMPTZ    NOT NULL,
            state                VARCHAR(20),
            active_power_kw      NUMERIC(14,4),
            reactive_power_kvar  NUMERIC(14,4),
            soc_pct              NUMERIC(5,2),
            session_energy_kwh   NUMERIC(14,4),
            achievement_rate_pct NUMERIC(5,2),
            curtailment_pct      NUMERIC(5,2),
            PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts);
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_der_telemetry_asset_ts "
        "ON der_telemetry (asset_id, ts)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_der_telemetry_ts ON der_telemetry (ts)")

    # Seed 3 rolling weekly partitions (previous, current, next).
    op.execute(
        """
        DO $$
        DECLARE w_start DATE; w_end DATE; p_name TEXT;
        BEGIN
            FOR i IN -1..1 LOOP
                w_start := date_trunc('week', now()) + (i * 7 || ' day')::interval;
                w_end   := w_start + INTERVAL '7 day';
                p_name  := 'der_telemetry_' || to_char(w_start, 'IYYY_IW');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF der_telemetry
                       FOR VALUES FROM (%L) TO (%L);',
                    p_name, w_start, w_end
                );
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS der_telemetry CASCADE;")
