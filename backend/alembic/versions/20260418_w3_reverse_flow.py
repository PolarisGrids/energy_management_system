"""spec 018 W3.T13 — reverse_flow_event table

Stores feeder reverse-flow incidents detected by the background correlator.
An incident is opened when net flow (import_kw - export_kw) stays < 0 for
`reverse_flow_window_seconds` (default 300s), and closed when net flow
returns to >= 0.

Revision ID: w3_reverse_flow
Revises:     w3_outage_model
Create Date: 2026-04-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "w3_reverse_flow"
down_revision: Union[str, Sequence[str], None] = "w3_outage_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reverse_flow_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("feeder_id", sa.String(length=100), nullable=False, index=True),
        sa.Column("detected_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("net_flow_kw", sa.Numeric(14, 4), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'OPEN'")),
        sa.Column(
            "details",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_reverse_flow_feeder_status",
        "reverse_flow_event",
        ["feeder_id", "status"],
    )
    op.create_index(
        "ix_reverse_flow_detected_at",
        "reverse_flow_event",
        ["detected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reverse_flow_detected_at", table_name="reverse_flow_event")
    op.drop_index("ix_reverse_flow_feeder_status", table_name="reverse_flow_event")
    op.drop_table("reverse_flow_event")
