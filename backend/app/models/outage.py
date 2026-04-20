"""Outage management models — spec 018 W3.

Distinct from the spec-016 `outage_incidents` (plural) feeder-scoped table.
These tables back the Wave-3 outage correlator, FLISR, and reliability
indices workflows.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class TextArray(TypeDecorator):
    """``ARRAY(Text)`` on PostgreSQL, JSON list fallback elsewhere (SQLite tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text()))
        return dialect.type_descriptor(JSON())


class JsonbOrJson(TypeDecorator):
    """JSONB on PostgreSQL, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class OutageIncidentW3(Base):
    """Spec-018 outage incident — DTR-scoped with PostGIS fault geometry.

    Table name: ``outage_incident`` (singular). Separate from spec-016's
    ``outage_incidents``.
    """
    __tablename__ = "outage_incident"

    id = Column(String(36), primary_key=True)  # UUID as string for SQLite test compat
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="DETECTED", index=True)
    affected_dtr_ids = Column(TextArray, nullable=True)
    affected_meter_count = Column(Integer, default=0)
    restored_meter_count = Column(Integer, default=0)
    confidence_pct = Column(Numeric(5, 2), nullable=True)
    timeline = Column(JsonbOrJson, nullable=False, default=list)
    saidi_contribution_s = Column(Integer, nullable=True)
    trigger_trace_id = Column(String(64), nullable=True)
    # ``suspected_fault_point`` is a PostGIS geometry column in Postgres.
    # On SQLite we ignore the column at model level; the migration falls back
    # to JSONB when PostGIS is unavailable.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    timeline_events = relationship(
        "OutageTimelineEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="OutageTimelineEvent.at",
    )
    flisr_actions = relationship(
        "OutageFlisrAction",
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class OutageTimelineEvent(Base):
    __tablename__ = "outage_timeline"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    incident_id = Column(
        String(36),
        ForeignKey("outage_incident.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(40), nullable=False)
    actor_user_id = Column(String(200), nullable=True)
    details = Column(JsonbOrJson, nullable=True)
    trace_id = Column(String(64), nullable=True)
    at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    incident = relationship("OutageIncidentW3", back_populates="timeline_events")


class OutageFlisrAction(Base):
    __tablename__ = "outage_flisr_action"

    id = Column(String(36), primary_key=True)
    incident_id = Column(
        String(36),
        ForeignKey("outage_incident.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(20), nullable=False)  # isolate | restore
    target_switch_id = Column(String(100), nullable=True)
    hes_command_id = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="QUEUED")
    issuer_user_id = Column(String(200), nullable=True)
    trace_id = Column(String(64), nullable=True)
    response_payload = Column(JsonbOrJson, nullable=True)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("OutageIncidentW3", back_populates="flisr_actions")
