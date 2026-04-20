"""spec 018 W4 — virtual_object_group + alarm_rule + alarm_rule_firing + notification_delivery

Chains from `w3_reverse_flow` (J). Introduces the Wave 4 Notifications /
Alert-rules track data model per data-model.md §virtual_object_group,
§alarm_rule, §notification_delivery.

Revision ID: w4_notifications
Revises:     w3_reverse_flow
Create Date: 2026-04-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "w4_notifications"
down_revision: Union[str, Sequence[str], None] = "w3_reverse_flow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _jsonb_or_json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def _text_array() -> sa.types.TypeEngine:
    # Postgres native ARRAY(TEXT); JSON list on SQLite.
    return sa.JSON().with_variant(ARRAY(sa.Text()), "postgresql")


def upgrade() -> None:
    # ── virtual_object_group ────────────────────────────────────────────────
    if not _has_table("virtual_object_group"):
        op.create_table(
            "virtual_object_group",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("selector", _jsonb_or_json(), nullable=False,
                      server_default=sa.text("'{}'")),
            sa.Column("owner_user_id", sa.String(length=200), nullable=False),
            sa.Column("shared_with_roles", _text_array(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "ix_virtual_object_group_name", "virtual_object_group", ["name"]
        )
        op.create_index(
            "ix_virtual_object_group_owner", "virtual_object_group",
            ["owner_user_id"],
        )

    # ── alarm_rule ───────────────────────────────────────────────────────────
    if not _has_table("alarm_rule"):
        op.create_table(
            "alarm_rule",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "group_id",
                sa.String(length=36),
                sa.ForeignKey("virtual_object_group.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.String(length=1000), nullable=True),
            sa.Column("condition", _jsonb_or_json(), nullable=False,
                      server_default=sa.text("'{}'")),
            sa.Column("action", _jsonb_or_json(), nullable=False,
                      server_default=sa.text("'{}'")),
            sa.Column("priority", sa.Integer(), nullable=False,
                      server_default=sa.text("3")),
            sa.Column("active", sa.Boolean(), nullable=False,
                      server_default=sa.text("true")),
            sa.Column("schedule", _jsonb_or_json(), nullable=True),
            sa.Column("dedup_window_seconds", sa.Integer(), nullable=False,
                      server_default=sa.text("300")),
            sa.Column("owner_user_id", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
        )
        op.create_index("ix_alarm_rule_group", "alarm_rule", ["group_id"])
        op.create_index("ix_alarm_rule_active", "alarm_rule", ["active"])

    # ── alarm_rule_firing ────────────────────────────────────────────────────
    if not _has_table("alarm_rule_firing"):
        op.create_table(
            "alarm_rule_firing",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "rule_id",
                sa.String(length=36),
                sa.ForeignKey("alarm_rule.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("fired_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("dedup_key", sa.String(length=200), nullable=False),
            sa.Column("match_count", sa.Integer(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("sample_meter_serial", sa.String(length=100), nullable=True),
            sa.Column("sample_dtr_id", sa.String(length=100), nullable=True),
            sa.Column("context", _jsonb_or_json(), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_by", sa.String(length=200), nullable=True),
            sa.Column("escalation_tier", sa.Integer(), nullable=False,
                      server_default=sa.text("0")),
        )
        op.create_index("ix_alarm_rule_firing_rule", "alarm_rule_firing", ["rule_id"])
        op.create_index(
            "ix_alarm_rule_firing_dedup",
            "alarm_rule_firing",
            ["rule_id", "dedup_key"],
        )
        op.create_index(
            "ix_alarm_rule_firing_fired_at",
            "alarm_rule_firing",
            [sa.text("fired_at DESC")],
        )

    # ── notification_delivery ────────────────────────────────────────────────
    if not _has_table("notification_delivery"):
        op.create_table(
            "notification_delivery",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "rule_id",
                sa.String(length=36),
                sa.ForeignKey("alarm_rule.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "firing_id",
                sa.String(length=36),
                sa.ForeignKey("alarm_rule_firing.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("channel", sa.String(length=20), nullable=False),
            sa.Column("recipient", sa.Text(), nullable=False),
            sa.Column("subject", sa.String(length=500), nullable=True),
            sa.Column("payload", _jsonb_or_json(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("provider_reference", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("escalation_tier", sa.Integer(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("send_after", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_notif_delivery_rule", "notification_delivery", ["rule_id"])
        op.create_index("ix_notif_delivery_firing", "notification_delivery", ["firing_id"])
        op.create_index("ix_notif_delivery_channel", "notification_delivery", ["channel"])
        op.create_index("ix_notif_delivery_status", "notification_delivery", ["status"])
        op.create_index("ix_notif_delivery_send_after", "notification_delivery", ["send_after"])


def downgrade() -> None:
    for t in (
        "notification_delivery",
        "alarm_rule_firing",
        "alarm_rule",
        "virtual_object_group",
    ):
        if _has_table(t):
            op.drop_table(t)
