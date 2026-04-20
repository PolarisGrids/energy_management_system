from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, JSON, Boolean
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class EventType(str, enum.Enum):
    OUTAGE = "outage"
    RESTORE = "restore"
    FAULT = "fault"
    SWITCHING = "switching"
    DER_CONNECT = "der_connect"
    DER_DISCONNECT = "der_disconnect"
    OVERLOAD = "overload"
    VOLTAGE_VIOLATION = "voltage_violation"


class NetworkEvent(Base):
    __tablename__ = "network_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(Enum(EventType), nullable=False)
    feeder_id = Column(Integer, nullable=True)
    transformer_id = Column(Integer, nullable=True)
    meter_serial = Column(String(50), nullable=True)
    der_asset_id = Column(Integer, nullable=True)
    description = Column(String(500), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    affected_customers = Column(Integer, default=0)
    duration_minutes = Column(Float, nullable=True)
    resolved = Column(Boolean, default=False)
    event_data = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    scenario_id = Column(Integer, nullable=True)
