"""Add ANALYST + VIEWER values to userrole enum (W4.T12 5-role RBAC).

Revision ID: w4a_userrole_enum
Revises: w4_dashboards
Create Date: 2026-04-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "w4a_userrole_enum"
down_revision: Union[str, Sequence[str], None] = "w4_dashboards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres enums need separate transactions for ADD VALUE.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'ANALYST'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'VIEWER'")


def downgrade() -> None:
    # Postgres does not support DROP VALUE on enum types; no-op.
    pass
