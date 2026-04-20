"""Bring the live DB up to the current SQLAlchemy model state.

The live `smoc_ems` DB was originally materialised via `Base.metadata.create_all()`
a month ago and predates Alembic. Phase A (meter.py restore, supplier.py add)
and spec 015 (user.py columns) evolved the models without migrations, relying
on `create_all()` in dev. This migration closes that gap so the production DB
matches `app.models.*` at this point.

Revision ID: c1_align_phase_a_015
Revises: b1_outage_notifications
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c1_align_phase_a_015"
down_revision: Union[str, Sequence[str], None] = "b1_outage_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row is not None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    # --- Phase A: suppliers table + meter columns that meter.py references ---
    if not _has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("country", sa.String(100), nullable=True),
            sa.Column("rating", sa.Float, nullable=True),
            sa.Column("onboarded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    meter_adds = [
        ("manufacturer", sa.Column("manufacturer", sa.String(100), nullable=True)),
        ("model", sa.Column("model", sa.String(100), nullable=True)),
        ("meter_class", sa.Column("meter_class", sa.String(20), nullable=True)),
        ("supplier_id", sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=True)),
        ("discovered_at", sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True)),
        ("provisioned_at", sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True)),
        ("provisioned_by", sa.Column("provisioned_by", sa.String(100), nullable=True)),
        ("commissioned_at", sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True)),
    ]
    for col_name, col in meter_adds:
        if not _has_column("meters", col_name):
            op.add_column("meters", col)

    # MeterStatus enum gained DISCOVERED / PROVISIONAL / DECOMMISSIONED in Phase A.
    # Live DB's enum may still be the old 4-value version; extend it if needed.
    conn = op.get_bind()
    existing_labels = {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = 'meterstatus'"
            )
        ).fetchall()
    }
    for label in ("discovered", "provisional", "decommissioned"):
        if label not in existing_labels and existing_labels:
            op.execute(sa.text(f"ALTER TYPE meterstatus ADD VALUE IF NOT EXISTS '{label}'"))

    # --- Spec 015: RBAC columns on users ---
    if not _has_column("users", "permissions_override"):
        op.add_column("users", sa.Column("permissions_override", JSONB, nullable=True))
    if not _has_column("users", "password_changed_at"):
        op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("users", "failed_login_count"):
        op.add_column(
            "users",
            sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    # 015 columns
    for col in ("failed_login_count", "password_changed_at", "permissions_override"):
        if _has_column("users", col):
            op.drop_column("users", col)

    # Phase A meter columns (do not drop supplier FK if rows reference it)
    for col in (
        "commissioned_at",
        "provisioned_by",
        "provisioned_at",
        "discovered_at",
        "supplier_id",
        "meter_class",
        "model",
        "manufacturer",
    ):
        if _has_column("meters", col):
            op.drop_column("meters", col)

    if _has_table("suppliers"):
        op.drop_table("suppliers")

    # Enum ALTER TYPE ADD VALUE cannot be reversed in Postgres without dropping
    # and recreating the enum. Leaving the extra labels in place is safe.
