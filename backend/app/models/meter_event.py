"""Raw meter events ingested from the HES Kafka stream — spec 018 W2.T2.

`hesv2.meter.events` → one row per event_id. Keeps the original
DLMS event code alongside the normalised `event_type` so the outage
correlator (Wave 3) and NTL service (Wave 3) can pick from either
representation.
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class MeterEventLog(Base):
    __tablename__ = "meter_event_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    meter_serial = Column(String(64), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    dlms_event_code = Column(Integer, nullable=True)
    dcu_id = Column(String(64), nullable=True, index=True)
    event_ts = Column(DateTime(timezone=True), nullable=False, index=True)
    received_ts = Column(DateTime(timezone=True), server_default=func.now())
    source_trace_id = Column(String(64), nullable=True)
    raw_payload = Column(String, nullable=True)  # JSON-string for debug; keep small


class OutageCorrelatorInput(Base):
    """Lightweight queue table read by the Wave-3 outage correlator.

    Populated from the meter.events consumer on power_failure / power_restored.
    Wave 3 will add a Redis-backed fast path; until then this Postgres table
    keeps the signal durable and queryable.
    """
    __tablename__ = "outage_correlator_input"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    meter_serial = Column(String(64), nullable=False, index=True)
    dtr_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(30), nullable=False)  # power_failure|power_restored
    event_ts = Column(DateTime(timezone=True), nullable=False, index=True)
    processed = Column(Boolean, nullable=False, default=False, index=True)
    source_trace_id = Column(String(64), nullable=True)
