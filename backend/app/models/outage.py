"""Outage management models — spec 018 W3 + spec 016.

Two coexisting outage record tables:
* ``outage_incident`` (singular) — spec-018 W3 DTR-scoped model with PostGIS
  fault geometry, timeline events, and FLISR actions. Class: ``OutageIncidentW3``.
* ``outage_incidents`` (plural) — spec-016 feeder-scoped lifecycle record
  used by the reliability calc and notification dispatcher. Class:
  ``OutageIncident``.
"""
from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
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


# ─────────────────────────────────────────────────────────────────────────────
# Spec-016 outage lifecycle — feeder-scoped, used by reliability_calc + dispatcher.
# ─────────────────────────────────────────────────────────────────────────────


class OutageStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    DISPATCHED = "DISPATCHED"
    RESTORING = "RESTORING"
    RESTORED = "RESTORED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class OutageIncident(Base):
    """Spec-016 feeder-scoped outage incident. Table: ``outage_incidents``."""

    __tablename__ = "outage_incidents"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(
        Enum(OutageStatus, name="outage_status", native_enum=False),
        nullable=False,
        default=OutageStatus.DETECTED,
        index=True,
    )
    feeder_id = Column(Integer, ForeignKey("feeders.id"), nullable=False, index=True)
    outage_area_id = Column(Integer, ForeignKey("outage_areas.id"), nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    restored_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    etr_at = Column(DateTime(timezone=True), nullable=True)

    affected_customers = Column(Integer, default=0)
    cause = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
