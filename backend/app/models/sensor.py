"""Transformer sensor model — REQ-25 Transformer Sensor Assets."""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class SensorStatus(str, enum.Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


class TransformerSensor(Base):
    __tablename__ = "transformer_sensors"

    id = Column(Integer, primary_key=True, index=True)
    transformer_id = Column(Integer, ForeignKey("transformers.id"), nullable=False)
    sensor_type = Column(String(30), nullable=False)   # winding_temp, oil_temp, oil_level, vibration, humidity, current_phase_a/b/c
    name = Column(String(100), nullable=False)
    value = Column(Float, default=0.0)
    unit = Column(String(10), nullable=False)            # degC, %, mm/s, A
    threshold_warning = Column(Float, nullable=True)
    threshold_critical = Column(Float, nullable=True)
    status = Column(Enum(SensorStatus), default=SensorStatus.NORMAL)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    transformer = relationship("Transformer", back_populates="sensors")
