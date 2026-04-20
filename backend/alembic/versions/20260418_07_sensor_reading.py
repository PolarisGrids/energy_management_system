"""Spec 018 W2.T5 — transformer_sensor_reading (monthly partition).

Revision ID: d4_sensor_reading
Revises: d3_meter_last_command
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4_sensor_reading"
down_revision: Union[str, Sequence[str], None] = "d3_meter_last_command"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partitioned parent table — PostgreSQL 12+ native range partitioning.
    # `IF NOT EXISTS` makes this idempotent against dev DBs that may have
    # the flat (non-partitioned) table from a prior `Base.metadata.create_all()`.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS transformer_sensor_reading (
            id            BIGSERIAL       NOT NULL,
            sensor_id     VARCHAR(100)    NOT NULL,
            dtr_id        VARCHAR(100),
            type          VARCHAR(50)     NOT NULL,
            value         NUMERIC(12,4)   NOT NULL,
            unit          VARCHAR(20),
            breach_flag   BOOLEAN         NOT NULL DEFAULT FALSE,
            threshold_max NUMERIC(12,4),
            ts            TIMESTAMPTZ     NOT NULL,
            PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts);
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transformer_sensor_reading_sensor_ts "
        "ON transformer_sensor_reading (sensor_id, ts)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transformer_sensor_reading_dtr "
        "ON transformer_sensor_reading (dtr_id)"
    )

    # Seed 3 months of rolling partitions (last month, this month, next month).
    # Subsequent partitions are created by the ops runbook's monthly job.
    op.execute(
        """
        DO $$
        DECLARE m_start DATE; m_end DATE; p_name TEXT;
        BEGIN
            FOR i IN -1..1 LOOP
                m_start := date_trunc('month', now()) + (i || ' month')::interval;
                m_end   := m_start + INTERVAL '1 month';
                p_name  := 'transformer_sensor_reading_' || to_char(m_start, 'YYYY_MM');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF transformer_sensor_reading
                       FOR VALUES FROM (%L) TO (%L);',
                    p_name, m_start, m_end
                );
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS transformer_sensor_reading CASCADE;")
