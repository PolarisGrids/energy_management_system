"""Spec 018 `transformer_sensor_reading` — time-series of sensor values from Kafka.

Populated by W2A's `hesv2.sensor.readings` consumer. W2B reads from it for the
`/api/v1/sensors/{id}/history` endpoint (replacing the old `random.uniform`
synthesiser).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.base import Base


# Portable 64-bit PK: BIGINT on PostgreSQL, INTEGER (auto-incrementing) on SQLite.
_BIG_PK = BigInteger().with_variant(Integer(), "sqlite")


class TransformerSensorReading(Base):
    __tablename__ = "transformer_sensor_reading"

    id = Column(_BIG_PK, primary_key=True, autoincrement=True)
    sensor_id = Column(String(100), nullable=False, index=True)
    dtr_id = Column(String(100), nullable=True, index=True)
    type = Column(String(50), nullable=False)  # oil_temp, load_current, humidity, etc.
    value = Column(Numeric(12, 4), nullable=True)
    unit = Column(String(20), nullable=True)
    breach_flag = Column(Boolean, default=False)
    threshold_max = Column(Numeric(12, 4), nullable=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_sensor_reading_sensor_ts", "sensor_id", "ts"),
    )
