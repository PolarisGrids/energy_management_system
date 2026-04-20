"""spec 018 W4.T6 + W4.T10 — AppBuilder (app_def / rule_def / algorithm_def)
and scheduled_report tables.

- All three definition tables are versioned (slug, version unique).
- Status lifecycle: DRAFT → PREVIEW → PUBLISHED → ARCHIVED.
- Only one PUBLISHED row per slug is enforced via a partial unique index on
  PostgreSQL (SQLite-compatible path omits the partial predicate in tests).
- `scheduled_report` holds recurring EGSM-report jobs dispatched by the
  APScheduler worker in `app.services.scheduled_report_worker`.

Revision ID: w4_appbuilder_reports
Revises:     w4_notifications
Create Date: 2026-04-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "w4_appbuilder_reports"
down_revision: Union[str, Sequence[str], None] = "w4_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _versioned_columns() -> list[sa.Column]:
    """Shared column set for app_def / rule_def / algorithm_def."""
    return [
        sa.Column(
            "id",
            sa.String(length=36).with_variant(UUID(as_uuid=False), "postgresql"),
            primary_key=True,
        ),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("author_user_id", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "definition",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _create_partial_unique_published(table: str) -> None:
    """Enforce 'one PUBLISHED per slug' on PostgreSQL only."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS "
        f"uq_{table}_one_published_per_slug "
        f"ON {table}(slug) WHERE status = 'PUBLISHED'"
    )


def upgrade() -> None:
    # ── app_def ─────────────────────────────────────────────────────────
    if not _has_table("app_def"):
        op.create_table(
            "app_def",
            *_versioned_columns(),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("required_role", sa.String(length=100), nullable=True),
            sa.UniqueConstraint("slug", "version", name="uq_app_def_slug_version"),
        )
        op.create_index("ix_app_def_slug", "app_def", ["slug"])
        op.create_index("ix_app_def_status", "app_def", ["status"])
        _create_partial_unique_published("app_def")

    # ── rule_def ────────────────────────────────────────────────────────
    if not _has_table("rule_def"):
        op.create_table(
            "rule_def",
            *_versioned_columns(),
            sa.Column("app_slug", sa.String(length=120), nullable=True),
            sa.UniqueConstraint("slug", "version", name="uq_rule_def_slug_version"),
        )
        op.create_index("ix_rule_def_slug", "rule_def", ["slug"])
        op.create_index("ix_rule_def_status", "rule_def", ["status"])
        op.create_index("ix_rule_def_app_slug", "rule_def", ["app_slug"])
        _create_partial_unique_published("rule_def")

    # ── algorithm_def ──────────────────────────────────────────────────
    if not _has_table("algorithm_def"):
        op.create_table(
            "algorithm_def",
            *_versioned_columns(),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.Text(), nullable=False),
            sa.UniqueConstraint(
                "slug", "version", name="uq_algorithm_def_slug_version"
            ),
        )
        op.create_index("ix_algorithm_def_slug", "algorithm_def", ["slug"])
        op.create_index("ix_algorithm_def_status", "algorithm_def", ["status"])
        _create_partial_unique_published("algorithm_def")

    # ── scheduled_report ───────────────────────────────────────────────
    if not _has_table("scheduled_report"):
        op.create_table(
            "scheduled_report",
            sa.Column(
                "id",
                sa.String(length=36).with_variant(UUID(as_uuid=False), "postgresql"),
                primary_key=True,
            ),
            sa.Column("owner_user_id", sa.String(length=200), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("report_ref", sa.String(length=300), nullable=False),
            sa.Column(
                "params",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("schedule_cron", sa.String(length=100), nullable=False),
            sa.Column(
                "recipients",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "enabled", sa.Integer(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(length=20), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_scheduled_report_owner", "scheduled_report", ["owner_user_id"]
        )


def downgrade() -> None:
    for tbl in ("scheduled_report", "algorithm_def", "rule_def", "app_def"):
        if _has_table(tbl):
            op.drop_table(tbl)
