from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.db.base import Base


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    meter_serial = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    energy_import_kwh = Column(Float, default=0.0)
    energy_export_kwh = Column(Float, default=0.0)
    demand_kw = Column(Float, default=0.0)
    voltage_v = Column(Float, nullable=True)
    current_a = Column(Float, nullable=True)
    power_factor = Column(Float, nullable=True)
    frequency_hz = Column(Float, default=50.0)
    thd_percent = Column(Float, nullable=True)
    is_estimated = Column(Integer, default=0)  # 0=actual, 1=estimated

    __table_args__ = (
        Index("ix_meter_readings_serial_ts", "meter_serial", "timestamp"),
    )
