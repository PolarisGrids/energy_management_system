"""baseline: stamp current schema state (no-op)

This revision exists purely to anchor Alembic's version chain on the existing
schema (created via Base.metadata.create_all in scripts/seed_data.py). Running
`alembic upgrade head` on an already-populated DB and stamping this revision is
a no-op — subsequent revisions add only new tables.

Revision ID: 20260418_0001
Revises:
Create Date: 2026-04-18

"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = "20260418_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — baseline marker only.
    # The pre-013 schema is created by scripts/seed_data.py via Base.metadata.create_all.
    pass


def downgrade() -> None:
    pass
