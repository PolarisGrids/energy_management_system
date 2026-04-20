"""Data Accuracy cache — spec 018 W4.T14.

One row per active meter. Refreshed by a background scheduler that fans out
HES + MDMS + CIS calls every 5 minutes. The `updated_at` stamp lets the UI
show a "last refreshed" banner; the three source timestamps drive a
server-side health badge (healthy / lagging / missing).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.db.base import Base


class SourceStatus(Base):
    """Materialised last-seen snapshot across HES / MDMS / CIS per meter."""

    __tablename__ = "source_status"

    meter_serial = Column(String(100), primary_key=True)
    hes_last_seen = Column(DateTime(timezone=True), nullable=True)
    mdms_last_validated = Column(DateTime(timezone=True), nullable=True)
    cis_last_billing = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
