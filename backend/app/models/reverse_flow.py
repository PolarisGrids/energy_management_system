"""Spec 018 W3.T13 — `reverse_flow_event` model.

Persists feeder reverse-flow incidents. Written by
`app.services.reverse_flow_detector` on the 5-min rolling window; read by
the `/api/v1/reverse-flow/*` endpoints that power the DER feeder banner.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


_BIG_PK = BigInteger().with_variant(Integer(), "sqlite")


class ReverseFlowEvent(Base):
    __tablename__ = "reverse_flow_event"

    id = Column(_BIG_PK, primary_key=True, autoincrement=True)
    feeder_id = Column(String(100), nullable=False, index=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    net_flow_kw = Column(Numeric(14, 4), nullable=True)
    duration_s = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="OPEN")
    details = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
