"""spec 018 W4.T11 + W4.T14 — dashboard_layout + source_status tables.

Chains after w4_appbuilder_reports (Agent M's head). Adds the two owned
tables this wave still needs:

  • dashboard_layout — per-user saved widget layouts with optional role-share.
  • source_status    — Data Accuracy cache refreshed every 5 min by a
                       scheduler joining HES/MDMS/CIS signals per meter.

Both creates use ``_has_table`` idempotence guards so the migration is safe
to re-run or apply on top of partially-populated DBs.

Revision ID: w4_dashboards
Revises:     w4_appbuilder_reports
Create Date: 2026-04-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "w4_dashboards"
down_revision: Union[str, Sequence[str], None] = "w4_appbuilder_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _jsonb_or_json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def _text_array() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(ARRAY(sa.Text()), "postgresql")


def upgrade() -> None:
    # ── dashboard_layout ────────────────────────────────────────────────────
    if not _has_table("dashboard_layout"):
        op.create_table(
            "dashboard_layout",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("owner_user_id", sa.String(length=200), nullable=False, index=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("widgets", _jsonb_or_json(), nullable=False, server_default="[]"),
            sa.Column(
                "shared_with_roles",
                _text_array(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_dashboard_layout_owner",
            "dashboard_layout",
            ["owner_user_id"],
        )

    # ── source_status (Data Accuracy cache) ─────────────────────────────────
    if not _has_table("source_status"):
        op.create_table(
            "source_status",
            sa.Column("meter_serial", sa.String(length=100), primary_key=True),
            sa.Column("hes_last_seen", sa.DateTime(timezone=True), nullable=True),
            sa.Column("mdms_last_validated", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cis_last_billing", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_source_status_updated_at",
            "source_status",
            ["updated_at"],
        )


def downgrade() -> None:
    if _has_table("source_status"):
        op.drop_index("ix_source_status_updated_at", table_name="source_status")
        op.drop_table("source_status")
    if _has_table("dashboard_layout"):
        op.drop_index("ix_dashboard_layout_owner", table_name="dashboard_layout")
        op.drop_table("dashboard_layout")
