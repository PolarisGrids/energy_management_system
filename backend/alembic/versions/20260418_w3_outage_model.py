"""spec 018 W3 — outage_incident + timeline + flisr_action + reliability MV

Per spec 018 data-model.md §outage_incident. This is distinct from the spec-016
`outage_incidents` (plural) table, which is feeder-scoped with sequential integer
PKs. The spec-018 table uses a UUID PK, PostGIS fault-point geometry, an array
of affected DTR ids, and an append-only JSONB timeline.

Revision ID: w3_outage_model
Revises:     w2b1_cmdlog_fota_der
Create Date: 2026-04-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "w3_outage_model"
down_revision: Union[str, Sequence[str], None] = "w2b1_cmdlog_fota_der"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _postgis_available() -> bool:
    bind = op.get_bind()
    try:
        row = bind.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname='postgis'")
        ).first()
        return row is not None
    except Exception:
        return False


def upgrade() -> None:
    # ── outage_incident (spec-018) ─────────────────────────────────────────
    if not _has_table("outage_incident"):
        cols = [
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="DETECTED"),
            sa.Column("affected_dtr_ids", ARRAY(sa.Text()), nullable=True),
            sa.Column("affected_meter_count", sa.Integer(), server_default="0"),
            sa.Column("restored_meter_count", sa.Integer(), server_default="0"),
            sa.Column("confidence_pct", sa.Numeric(5, 2), nullable=True),
            sa.Column("timeline", JSONB, nullable=False, server_default="[]"),
            sa.Column("saidi_contribution_s", sa.Integer(), nullable=True),
            sa.Column("trigger_trace_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        ]
        # Add PostGIS geometry column if extension available; otherwise fall back to JSONB.
        if _postgis_available():
            op.create_table("outage_incident", *cols)
            op.execute(
                "ALTER TABLE outage_incident "
                "ADD COLUMN suspected_fault_point geometry(Point, 4326)"
            )
            op.execute(
                "CREATE INDEX ix_outage_incident_fault_point_gist "
                "ON outage_incident USING GIST (suspected_fault_point)"
            )
        else:
            cols.append(sa.Column("suspected_fault_point", JSONB, nullable=True))
            op.create_table("outage_incident", *cols)
        op.create_index("ix_outage_incident_status", "outage_incident", ["status"])
        op.create_index(
            "ix_outage_incident_opened_at",
            "outage_incident",
            [sa.text("opened_at DESC")],
        )

    # ── outage_timeline (append-only event log) ────────────────────────────
    if not _has_table("outage_timeline"):
        op.create_table(
            "outage_timeline",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "incident_id",
                UUID(as_uuid=False),
                sa.ForeignKey("outage_incident.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("actor_user_id", sa.String(200), nullable=True),
            sa.Column("details", JSONB, nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "ix_outage_timeline_incident_at",
            "outage_timeline",
            ["incident_id", sa.text("at ASC")],
        )

    # ── outage_flisr_action (network switching events) ─────────────────────
    if not _has_table("outage_flisr_action"):
        op.create_table(
            "outage_flisr_action",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "incident_id",
                UUID(as_uuid=False),
                sa.ForeignKey("outage_incident.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("action", sa.String(20), nullable=False),  # isolate | restore
            sa.Column("target_switch_id", sa.String(100), nullable=True),
            sa.Column("hes_command_id", sa.String(64), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
            sa.Column("issuer_user_id", sa.String(200), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("response_payload", JSONB, nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── reliability_indices_mv (materialised view) ─────────────────────────
    # SAIDI / SAIFI / CAIDI / MAIFI per day. Source = outage_incident.
    # system_id is a literal string for now (single system per deployment).
    # Momentary interruptions (< 5 min) contribute to MAIFI, not SAIDI.
    mv_sql = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS reliability_indices_mv AS
    WITH system_meters AS (
        SELECT COALESCE(NULLIF(current_setting('ems.total_customers', true), ''), '10000')::int AS total_customers
    ),
    daily AS (
        SELECT
            date_trunc('day', opened_at)::date AS date,
            'polaris-ems' AS system_id,
            SUM(
                CASE
                    WHEN closed_at IS NOT NULL AND EXTRACT(EPOCH FROM (closed_at - opened_at)) >= 300
                    THEN COALESCE(affected_meter_count, 0)
                          * (EXTRACT(EPOCH FROM (closed_at - opened_at)) / 60.0)
                    ELSE 0
                END
            )::numeric AS customer_minutes_interrupted,
            SUM(
                CASE
                    WHEN closed_at IS NOT NULL AND EXTRACT(EPOCH FROM (closed_at - opened_at)) >= 300
                    THEN COALESCE(affected_meter_count, 0)
                    ELSE 0
                END
            )::int AS customers_interrupted,
            SUM(
                CASE
                    WHEN closed_at IS NOT NULL AND EXTRACT(EPOCH FROM (closed_at - opened_at)) < 300
                    THEN COALESCE(affected_meter_count, 0)
                    ELSE 0
                END
            )::int AS momentary_customers_affected
        FROM outage_incident
        WHERE status IN ('RESTORED', 'CLOSED')
        GROUP BY 1, 2
    )
    SELECT
        d.date,
        d.system_id,
        (CASE WHEN sm.total_customers > 0
              THEN d.customer_minutes_interrupted / sm.total_customers ELSE 0 END)::numeric(10,4) AS saidi,
        (CASE WHEN sm.total_customers > 0
              THEN d.customers_interrupted::numeric / sm.total_customers ELSE 0 END)::numeric(10,4) AS saifi,
        (CASE WHEN d.customers_interrupted > 0
              THEN d.customer_minutes_interrupted / d.customers_interrupted ELSE 0 END)::numeric(10,4) AS caidi,
        (CASE WHEN sm.total_customers > 0
              THEN d.momentary_customers_affected::numeric / sm.total_customers ELSE 0 END)::numeric(10,4) AS maifi,
        sm.total_customers
    FROM daily d CROSS JOIN system_meters sm;
    """
    # PostgreSQL required (MVs); skip gracefully on SQLite-backed tests.
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(mv_sql)
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_reliability_indices_mv_date "
            "ON reliability_indices_mv (date, system_id)"
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP MATERIALIZED VIEW IF EXISTS reliability_indices_mv")
    for t in ("outage_flisr_action", "outage_timeline", "outage_incident"):
        if _has_table(t):
            op.drop_table(t)
