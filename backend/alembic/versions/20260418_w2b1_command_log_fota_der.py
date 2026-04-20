"""spec 018 W2B — command_log, fota_job, fota_job_meter_status, der_asset, der_command

Revision ID: w2b1_cmdlog_fota_der
Revises: c1_align_phase_a_015
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "w2b1_cmdlog_fota_der"
# Descends from the current W2A head `d6_der_telemetry`. W2A already creates
# `transformer_sensor_reading` (d4), so our migration only guards-if-exists.
down_revision: Union[str, Sequence[str], None] = "d6_der_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    # ── command_log ──
    if not _has_table("command_log"):
        op.create_table(
            "command_log",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("meter_serial", sa.String(100), nullable=False),
            sa.Column("command_type", sa.String(60), nullable=False),
            sa.Column("payload", JSONB, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
            sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("response_payload", JSONB, nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
            sa.Column("issuer_user_id", sa.String(200), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
        )
        op.create_index("ix_command_log_meter_serial", "command_log", ["meter_serial"])
        op.create_index(
            "ix_command_log_meter_serial_issued_at",
            "command_log",
            ["meter_serial", "issued_at"],
        )
        op.create_index("ix_command_log_trace_id", "command_log", ["trace_id"])

    # ── fota_job ──
    if not _has_table("fota_job"):
        op.create_table(
            "fota_job",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("hes_job_id", sa.String(100), nullable=True),
            sa.Column("firmware_name", sa.Text(), nullable=False),
            sa.Column("firmware_version", sa.String(50), nullable=True),
            sa.Column("image_uri", sa.Text(), nullable=False),
            sa.Column("total_meters", sa.Integer(), server_default="0"),
            sa.Column("succeeded", sa.Integer(), server_default="0"),
            sa.Column("failed", sa.Integer(), server_default="0"),
            sa.Column("in_progress", sa.Integer(), server_default="0"),
            sa.Column("status", sa.String(20), server_default="QUEUED"),
            sa.Column("issuer_user_id", sa.String(200), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("poll_cursor", JSONB, nullable=True),
        )
        op.create_index("ix_fota_job_hes_job_id", "fota_job", ["hes_job_id"])

    # ── fota_job_meter_status ──
    if not _has_table("fota_job_meter_status"):
        op.create_table(
            "fota_job_meter_status",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "job_id",
                UUID(as_uuid=False),
                sa.ForeignKey("fota_job.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("meter_serial", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), server_default="PENDING"),
            sa.Column("progress_pct", sa.Integer(), server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_fota_job_meter_status_job_id", "fota_job_meter_status", ["job_id"])
        op.create_index(
            "ix_fota_job_meter_status_serial", "fota_job_meter_status", ["meter_serial"]
        )

    # ── der_asset (spec 018, VARCHAR PK) ──
    if not _has_table("der_asset"):
        op.create_table(
            "der_asset",
            sa.Column("id", sa.String(100), primary_key=True),
            sa.Column("type", sa.String(20), nullable=False),
            sa.Column("name", sa.Text(), nullable=True),
            sa.Column("dtr_id", sa.String(100), nullable=True),
            sa.Column("feeder_id", sa.String(100), nullable=True),
            sa.Column("lat", sa.Numeric(10, 6), nullable=True),
            sa.Column("lon", sa.Numeric(10, 6), nullable=True),
            sa.Column("capacity_kw", sa.Numeric(10, 2), nullable=True),
            sa.Column("capacity_kwh", sa.Numeric(10, 2), nullable=True),
            sa.Column("metadata", JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_der_asset_dtr_id", "der_asset", ["dtr_id"])

    # ── transformer_sensor_reading (W2B.T11 DB source for sensor history) ──
    if not _has_table("transformer_sensor_reading"):
        op.create_table(
            "transformer_sensor_reading",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("sensor_id", sa.String(100), nullable=False),
            sa.Column("dtr_id", sa.String(100), nullable=True),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("value", sa.Numeric(12, 4), nullable=True),
            sa.Column("unit", sa.String(20), nullable=True),
            sa.Column("breach_flag", sa.Boolean(), server_default=sa.false()),
            sa.Column("threshold_max", sa.Numeric(12, 4), nullable=True),
            sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "ix_transformer_sensor_reading_sensor_id", "transformer_sensor_reading", ["sensor_id"]
        )
        op.create_index(
            "ix_transformer_sensor_reading_dtr_id", "transformer_sensor_reading", ["dtr_id"]
        )
        op.create_index(
            "ix_sensor_reading_sensor_ts", "transformer_sensor_reading", ["sensor_id", "ts"]
        )

    # ── der_command ──
    if not _has_table("der_command"):
        op.create_table(
            "der_command",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "asset_id",
                sa.String(100),
                sa.ForeignKey("der_asset.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("command_type", sa.String(40), nullable=False),
            sa.Column("setpoint", sa.Numeric(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
            sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("issuer_user_id", sa.String(200), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("response_payload", JSONB, nullable=True),
        )
        op.create_index("ix_der_command_asset_id", "der_command", ["asset_id"])


def downgrade() -> None:
    for t in (
        "der_command",
        "transformer_sensor_reading",
        "der_asset",
        "fota_job_meter_status",
        "fota_job",
        "command_log",
    ):
        if _has_table(t):
            op.drop_table(t)
