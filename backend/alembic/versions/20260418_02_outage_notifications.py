"""Outage incidents + notifications + reliability tables.

Spec 016-notifications-outage (MVP Setup + Foundational + US1 + US2).

Revision ID: b1_outage_notifications
Revises: a1_postgis_gis
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1_outage_notifications"
down_revision: Union[str, Sequence[str], None] = "a1_postgis_gis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OUTAGE_STATUS_VALUES = (
    "DETECTED",
    "CONFIRMED",
    "DISPATCHED",
    "RESTORING",
    "RESTORED",
    "CLOSED",
    "CANCELLED",
)
CHANNEL_VALUES = ("email", "sms", "teams", "push")
NOTIFY_STATUS_VALUES = ("pending", "sent", "failed", "dlq")
SEVERITY_VALUES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def upgrade() -> None:
    # Sanity: PostGIS must already be enabled (014 migrates it).
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='postgis') "
        "THEN RAISE EXCEPTION '016 migration requires spec 014 PostGIS extension'; "
        "END IF; END $$"
    )

    # ── outage_incidents ───────────────────────────────────────────────────
    op.create_table(
        "outage_incidents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="DETECTED",
        ),
        sa.Column(
            "feeder_id",
            sa.Integer(),
            sa.ForeignKey("feeders.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "outage_area_id",
            sa.Integer(),
            sa.ForeignKey("outage_areas.id"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etr_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("affected_customers", sa.Integer(), server_default="0"),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_outage_incidents_status", "outage_incidents", ["status"])
    op.execute(
        "ALTER TABLE outage_incidents ADD CONSTRAINT outage_incidents_status_chk "
        "CHECK (status IN ('" + "','".join(OUTAGE_STATUS_VALUES) + "'))"
    )

    # ── notification_templates ─────────────────────────────────────────────
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("subject_tpl", sa.Text(), nullable=True),
        sa.Column("body_tpl", sa.Text(), nullable=False),
        sa.Column(
            "locale",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "ALTER TABLE notification_templates ADD CONSTRAINT notification_templates_channel_chk "
        "CHECK (channel IN ('" + "','".join(CHANNEL_VALUES) + "'))"
    )

    # ── notification_rules ─────────────────────────────────────────────────
    op.create_table(
        "notification_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trigger_type", sa.String(length=100), nullable=False, index=True),
        sa.Column("severity_min", sa.String(length=16), nullable=True),
        sa.Column("match_filter", postgresql.JSONB, nullable=True),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "recipients",
            postgresql.ARRAY(sa.String(length=200)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── notification_deliveries ────────────────────────────────────────────
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel", sa.String(length=16), nullable=False, index=True),
        sa.Column("recipient", sa.String(length=300), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("notification_templates.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "ALTER TABLE notification_deliveries ADD CONSTRAINT notification_deliveries_channel_chk "
        "CHECK (channel IN ('" + "','".join(CHANNEL_VALUES) + "'))"
    )
    op.execute(
        "ALTER TABLE notification_deliveries ADD CONSTRAINT notification_deliveries_status_chk "
        "CHECK (status IN ('" + "','".join(NOTIFY_STATUS_VALUES) + "'))"
    )

    # ── user_notification_preferences ──────────────────────────────────────
    op.create_table(
        "user_notification_preferences",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column(
            "tz",
            sa.String(length=64),
            nullable=False,
            server_default="Asia/Kolkata",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── reliability_monthly ────────────────────────────────────────────────
    op.create_table(
        "reliability_monthly",
        sa.Column(
            "feeder_id",
            sa.Integer(),
            sa.ForeignKey("feeders.id"),
            primary_key=True,
        ),
        sa.Column("year_month", sa.CHAR(length=7), primary_key=True),
        sa.Column("saidi", sa.Float(), nullable=True),
        sa.Column("saifi", sa.Float(), nullable=True),
        sa.Column("caidi", sa.Float(), nullable=True),
        sa.Column("maifi", sa.Float(), nullable=True),
        sa.Column("total_customers", sa.Integer(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(year_month) = 7", name="reliability_monthly_yyyymm"
        ),
    )

    # ── Seed default templates + rules ─────────────────────────────────────
    op.execute(
        """
        INSERT INTO notification_templates (name, channel, subject_tpl, body_tpl, locale)
        VALUES
          ('outage-detected', 'email',
           'Outage detected on feeder {{ feeder_name }}',
           'An outage has been detected on feeder {{ feeder_name }} at {{ started_at }}. Affected customers: {{ affected_customers }}. ETR: {{ etr_at }}.',
           'en'),
          ('outage-restored', 'email',
           'Outage restored on feeder {{ feeder_name }}',
           'The outage on feeder {{ feeder_name }} has been restored at {{ restored_at }}.',
           'en'),
          ('alarm-critical', 'email',
           'CRITICAL alarm — {{ alarm_type }}',
           'CRITICAL alarm: {{ title }} on meter {{ meter_serial }} at {{ triggered_at }}. Trace: {{ trace_id }}.',
           'en')
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO notification_rules (trigger_type, severity_min, channels, recipients, enabled)
        VALUES
          ('outage.created',       'MEDIUM',   '{email,teams}', '{ops@polaris-ems.local}',      true),
          ('outage.restored',      'LOW',      '{email}',       '{ops@polaris-ems.local}',      true),
          ('alarm.critical',       'CRITICAL', '{email,sms,teams}', '{oncall@polaris-ems.local}', true)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reliability_monthly")
    op.execute("DROP TABLE IF EXISTS user_notification_preferences")
    op.execute("DROP TABLE IF EXISTS notification_deliveries")
    op.execute("DROP TABLE IF EXISTS notification_rules")
    op.execute("DROP TABLE IF EXISTS notification_templates")
    op.execute("DROP TABLE IF EXISTS outage_incidents")
