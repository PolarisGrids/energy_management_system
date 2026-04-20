"""Spec 018 W2.T2 — meter_event_log + outage_correlator_input.

Revision ID: d1_meter_event_log
Revises: c1_align_phase_a_015
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "d1_meter_event_log"
down_revision: Union[str, Sequence[str], None] = "c1_align_phase_a_015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    """Idempotence guard: dev DBs may already have these tables created by
    the legacy `Base.metadata.create_all()` path (now removed from
    seed_data.py). Skip the create so `alembic upgrade head` is re-runnable
    against any existing DB."""
    return sa_inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("meter_event_log"):
        op.create_table(
            "meter_event_log",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("meter_serial", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("dlms_event_code", sa.Integer(), nullable=True),
            sa.Column("dcu_id", sa.String(length=64), nullable=True),
            sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "received_ts",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("source_trace_id", sa.String(length=64), nullable=True),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.UniqueConstraint("event_id", name="uq_meter_event_log_event_id"),
        )
        op.create_index(
            "ix_meter_event_log_meter_ts", "meter_event_log", ["meter_serial", "event_ts"],
        )
        op.create_index(
            "ix_meter_event_log_type_ts", "meter_event_log", ["event_type", "event_ts"],
        )
        op.create_index("ix_meter_event_log_dcu", "meter_event_log", ["dcu_id"])

    if not _has_table("outage_correlator_input"):
        op.create_table(
            "outage_correlator_input",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("meter_serial", sa.String(length=64), nullable=False),
            sa.Column("dtr_id", sa.String(length=64), nullable=True),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "processed", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column("source_trace_id", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_outage_correlator_input_unprocessed",
            "outage_correlator_input",
            ["processed", "event_ts"],
        )
        op.create_index(
            "ix_outage_correlator_input_dtr", "outage_correlator_input", ["dtr_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_outage_correlator_input_dtr", table_name="outage_correlator_input")
    op.drop_index(
        "ix_outage_correlator_input_unprocessed", table_name="outage_correlator_input"
    )
    op.drop_table("outage_correlator_input")
    op.drop_index("ix_meter_event_log_dcu", table_name="meter_event_log")
    op.drop_index("ix_meter_event_log_type_ts", table_name="meter_event_log")
    op.drop_index("ix_meter_event_log_meter_ts", table_name="meter_event_log")
    op.drop_table("meter_event_log")
