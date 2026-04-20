from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class AlarmSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlarmType(str, enum.Enum):
    TAMPER = "tamper"
    OUTAGE = "outage"
    POWER_RESTORE = "power_restore"
    OVERVOLTAGE = "overvoltage"
    UNDERVOLTAGE = "undervoltage"
    OVERCURRENT = "overcurrent"
    BATTERY_LOW = "battery_low"
    COMM_LOSS = "comm_loss"
    COVER_OPEN = "cover_open"
    REVERSE_POWER = "reverse_power"
    TRANSFORMER_OVERLOAD = "transformer_overload"
    DER_CURTAILMENT = "der_curtailment"
    FAULT_DETECTED = "fault_detected"
    NTS_DETECTED = "nts_detected"


class AlarmStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Alarm(Base):
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, index=True)
    alarm_type = Column(Enum(AlarmType), nullable=False)
    severity = Column(Enum(AlarmSeverity), nullable=False)
    status = Column(Enum(AlarmStatus), default=AlarmStatus.ACTIVE)
    meter_serial = Column(String(50), nullable=True, index=True)
    transformer_id = Column(Integer, ForeignKey("transformers.id"), nullable=True)
    feeder_id = Column(Integer, ForeignKey("feeders.id"), nullable=True)
    der_asset_id = Column(Integer, ForeignKey("der_assets.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    scenario_id = Column(Integer, nullable=True, index=True)
    # Spec 018 W2.T3 — populated by the `hesv2.meter.alarms` Kafka consumer so
    # the Wave-3 outage correlator can bundle alarms triggered by the same
    # upstream trace / incident group.
    source_trace_id = Column(String(64), nullable=True, index=True)
    correlation_group_id = Column(String(64), nullable=True, index=True)
