"""Spec 018 W2.T4 — add `meters.last_command_id` for command round-trip tracking.

Revision ID: d3_meter_last_command
Revises: d2_alarm_trace_correlation
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "d3_meter_last_command"
down_revision: Union[str, Sequence[str], None] = "d2_alarm_trace_correlation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("meters", "last_command_id"):
        op.add_column("meters", sa.Column("last_command_id", sa.String(length=64), nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meters_last_command_id "
        "ON meters (last_command_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_meters_last_command_id", table_name="meters")
    with op.batch_alter_table("meters") as batch:
        batch.drop_column("last_command_id")
