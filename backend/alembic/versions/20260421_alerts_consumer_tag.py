"""Alert Management — consumer_tag table for site-type classification.

Revision ID: alerts_consumer_tag
Revises: w4a_userrole_enum
Create Date: 2026-04-21

Supports the "critical customers" virtual-object-group (hospital / data_centre /
fire_station) by tagging MDMS consumers with a site_type local to EMS.
MDMS's consumer_master_data is authoritative; we only persist the tag here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "alerts_consumer_tag"
down_revision: Union[str, Sequence[str], None] = "w4a_userrole_enum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("consumer_tag"):
        op.create_table(
            "consumer_tag",
            sa.Column("meter_serial", sa.String(50), primary_key=True),
            sa.Column("site_type", sa.String(32), nullable=False, server_default="residential"),
            sa.Column("account_id", sa.String(30), nullable=True, index=True),
            sa.Column("consumer_name", sa.String(200), nullable=True),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("tagged_by", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_consumer_tag_site_type", "consumer_tag", ["site_type"])


def downgrade() -> None:
    if _has_table("consumer_tag"):
        op.drop_index("ix_consumer_tag_site_type", table_name="consumer_tag")
        op.drop_table("consumer_tag")
