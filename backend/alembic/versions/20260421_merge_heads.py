"""Merge heads: alerts_consumer_tag + w5b_energy_savings.

Revision ID: merge_heads_20260421
Revises: alerts_consumer_tag, w5b_energy_savings
Create Date: 2026-04-21
"""
from typing import Sequence, Union

revision: str = "merge_heads_20260421"
down_revision: Union[str, Sequence[str], None] = (
    "alerts_consumer_tag",
    "w5b_energy_savings",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
