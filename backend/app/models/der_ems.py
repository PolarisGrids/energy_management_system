"""Spec 018 EMS-owned DER tables.

Complements the legacy `der_assets` table (integer PK, pre-spec-018) with
tables the simulator bulk-import populates. Keys match simulator asset IDs
(VARCHAR(100)), per `contracts/der-bulk-import.md`.
"""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


def _json_col():
    return JSON().with_variant(JSONB(), "postgresql")


def _uuid_col():
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")


class DERAssetEMS(Base):
    """Spec 018 `der_asset` (owned by EMS; keyed by simulator asset id)."""

    __tablename__ = "der_asset"

    id = Column(String(100), primary_key=True)
    type = Column(String(20), nullable=False)  # pv | bess | ev | microgrid
    name = Column(Text, nullable=True)
    dtr_id = Column(String(100), nullable=True)
    feeder_id = Column(String(100), nullable=True)
    # Store lat/lon as two numeric cols; PostGIS GEOMETRY added in W2A or
    # follow-up migration. Works without PostGIS extension for unit tests.
    lat = Column(Numeric(10, 6), nullable=True)
    lon = Column(Numeric(10, 6), nullable=True)
    capacity_kw = Column(Numeric(10, 2), nullable=True)
    capacity_kwh = Column(Numeric(10, 2), nullable=True)  # BESS only
    asset_metadata = Column("metadata", _json_col(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DERCommandEMS(Base):
    """Spec 018 `der_command` — per-asset command lifecycle."""

    __tablename__ = "der_command"

    id = Column(_uuid_col(), primary_key=True)  # command_id from HES
    asset_id = Column(String(100), ForeignKey("der_asset.id"), nullable=False, index=True)
    command_type = Column(String(40), nullable=False)
    setpoint = Column(Numeric, nullable=True)
    status = Column(String(20), nullable=False, default="QUEUED")
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    issuer_user_id = Column(String(200), nullable=True)
    trace_id = Column(String(64), nullable=True)
    response_payload = Column(_json_col(), nullable=True)
