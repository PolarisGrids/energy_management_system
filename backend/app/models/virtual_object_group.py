"""Virtual object group — spec 018 W4.T3.

A saved selection of meters / DTRs / feeders that alarm rules + dashboards
target. The selector is stored as JSON describing the hierarchy scope and
post-filters; it is materialised at rule-evaluation time by
:func:`app.services.group_resolver.resolve_group_members`.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, JSON, String, TypeDecorator, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class _TextArray(TypeDecorator):
    """``ARRAY(Text)`` on Postgres, JSON list elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text()))
        return dialect.type_descriptor(JSON())


class _JsonbOrJson(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class VirtualObjectGroup(Base):
    __tablename__ = "virtual_object_group"

    id = Column(String(36), primary_key=True)  # UUID hex
    name = Column(String(200), nullable=False, index=True)
    description = Column(String(500), nullable=True)
    # selector shape: {"hierarchy": {"substation_ids": [...], "feeder_ids": [...],
    #                                "dtr_ids": [...], "meter_serials": [...]},
    #                  "filters": {"tariff_class": "...", "meter_status": "..."}}
    selector = Column(_JsonbOrJson, nullable=False, default=dict)
    owner_user_id = Column(String(200), nullable=False)
    shared_with_roles = Column(_TextArray, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = ["VirtualObjectGroup"]
