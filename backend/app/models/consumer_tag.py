"""Consumer site-type tagging — Alert Management (2026-04-21).

The authoritative consumer master lives in MDMS (db_cis.consumer_master_data)
and is read-only from EMS's perspective. To support the "critical customers"
virtual-object-group (hospitals, data centres, fire stations), we keep a
local tag table keyed by MDMS ``meterSrno`` (== EMS meter serial).

One row per tagged consumer. Untagged consumers are treated as ``residential``
by the alert engine.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.db.base import Base


# Canonical site types the UI lets an operator pick.
SITE_TYPES = (
    "residential",
    "commercial",
    "industrial",
    "hospital",
    "data_centre",
    "fire_station",
    "government",
    "school",
)


class ConsumerTag(Base):
    __tablename__ = "consumer_tag"

    # MDMS meterSrno is a VARCHAR(16). We key on serial (not account_id) so the
    # tag can be joined against EMS meters.serial for local grouping too.
    meter_serial = Column(String(50), primary_key=True)
    site_type = Column(String(32), nullable=False, default="residential")
    account_id = Column(String(30), nullable=True, index=True)
    consumer_name = Column(String(200), nullable=True)
    notes = Column(String(500), nullable=True)
    tagged_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = ["ConsumerTag", "SITE_TYPES"]
