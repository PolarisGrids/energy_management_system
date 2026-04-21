"""Theft Analysis — theft_score + theft_run_log tables.

Revision ID: theft_analysis_20260421
Revises:     merge_heads_20260421
Create Date: 2026-04-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "theft_analysis_20260421"
down_revision: Union[str, Sequence[str], None] = "merge_heads_20260421"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _jsonb():
    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    if not _has_table("theft_score"):
        op.create_table(
            "theft_score",
            sa.Column("device_identifier", sa.String(64), primary_key=True),
            sa.Column("meter_type", sa.String(32), nullable=True),
            sa.Column("account_id", sa.String(32), nullable=True),
            sa.Column("manufacturer", sa.String(128), nullable=True),
            sa.Column("sanctioned_load_kw", sa.Float(), nullable=True),
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("risk_tier", sa.String(16), nullable=False, server_default="low"),
            sa.Column("fired_detectors", _jsonb(), nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column("top_evidence", _jsonb(), nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column("detector_results", _jsonb(), nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index(
            "ix_theft_score_score_desc", "theft_score",
            [sa.text("score DESC")],
        )
        op.create_index(
            "ix_theft_score_tier_score", "theft_score",
            ["risk_tier", sa.text("score DESC")],
        )
        op.create_index(
            "ix_theft_score_meter_type", "theft_score", ["meter_type"]
        )
        op.create_index(
            "ix_theft_score_account_id", "theft_score", ["account_id"]
        )

    if not _has_table("theft_run_log"):
        op.create_table(
            "theft_run_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("meters_scored", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meters_critical", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meters_high", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meters_medium", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meters_low", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trigger", sa.String(32), nullable=False, server_default="scheduled"),
            sa.Column("error", sa.Text(), nullable=True),
        )
        op.create_index(
            "ix_theft_run_log_started_at_desc", "theft_run_log",
            [sa.text("started_at DESC")],
        )


def downgrade() -> None:
    if _has_table("theft_run_log"):
        op.drop_index("ix_theft_run_log_started_at_desc", table_name="theft_run_log")
        op.drop_table("theft_run_log")
    if _has_table("theft_score"):
        op.drop_index("ix_theft_score_account_id", table_name="theft_score")
        op.drop_index("ix_theft_score_meter_type", table_name="theft_score")
        op.drop_index("ix_theft_score_tier_score", table_name="theft_score")
        op.drop_index("ix_theft_score_score_desc", table_name="theft_score")
        op.drop_table("theft_score")
