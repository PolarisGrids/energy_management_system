"""Dashboard layout model — spec 018 W4.T11.

Persists per-user dashboard widget configurations (layout + widget binding +
refresh cadence). Rows can be shared with other roles via
`shared_with_roles`. One default layout per user is marked with
`is_default=True` (endpoint layer enforces uniqueness).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


def _jsonb_or_json():
    # SQLite (unit tests) does not support JSONB — fall back to JSON. The
    # SQLAlchemy type variant dispatch picks the right column per dialect.
    from sqlalchemy import JSON

    return JSON().with_variant(JSONB(), "postgresql")


def _uuid_col():
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")


def _text_array():
    from sqlalchemy import JSON

    # PostgreSQL: native TEXT[]. Other dialects (SQLite tests): stored as JSON.
    return JSON().with_variant(ARRAY(Text()), "postgresql")


class DashboardLayout(Base):
    """Per-user saved dashboard widget configuration."""

    __tablename__ = "dashboard_layout"

    id = Column(_uuid_col(), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id = Column(String(200), nullable=False, index=True)
    name = Column(Text, nullable=False)
    # widgets: [{id, type, x, y, w, h, config: {...}, refresh_s: 30}]
    widgets = Column(_jsonb_or_json(), nullable=False, default=list)
    # Roles (by lowercase name) that may read this layout.
    shared_with_roles = Column(_text_array(), nullable=False, default=list)
    # Exactly zero or one row per owner may have is_default=True (endpoint
    # layer enforces; no partial unique index since SQLite in tests lacks the
    # feature).
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
