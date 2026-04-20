"""Spec 018 W2.T3 — extend `alarms` with source_trace_id + correlation_group_id.

Enables the Wave-3 outage correlator to bundle alarms triggered by the same
upstream trace (HES command / Kafka event) into a single incident group.

Revision ID: d2_alarm_trace_correlation
Revises: d1_meter_event_log
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "d2_alarm_trace_correlation"
down_revision: Union[str, Sequence[str], None] = "d1_meter_event_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # Idempotence guard — dev DBs may already have these columns (added
    # manually during the 2026-04-19 alembic-drift reconcile).
    if not _has_column("alarms", "source_trace_id"):
        op.add_column("alarms", sa.Column("source_trace_id", sa.String(length=64), nullable=True))
    if not _has_column("alarms", "correlation_group_id"):
        op.add_column(
            "alarms",
            sa.Column("correlation_group_id", sa.String(length=64), nullable=True),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alarms_correlation_group_id "
        "ON alarms (correlation_group_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alarms_source_trace_id "
        "ON alarms (source_trace_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_alarms_source_trace_id", table_name="alarms")
    op.drop_index("ix_alarms_correlation_group_id", table_name="alarms")
    with op.batch_alter_table("alarms") as batch:
        batch.drop_column("correlation_group_id")
        batch.drop_column("source_trace_id")
