"""Metrology reading tables — sourced from HES Kafka or MDMS VEE.

These replace the synthesized `meter_readings` table for production API paths.
See specs/013-metrology-ingest for contract.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Date,
    Boolean,
    Integer,
    Index,
    CHAR,
    BigInteger,
    SmallInteger,
    PrimaryKeyConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


# Source enum kept as plain VARCHAR + CHECK for portability with ON CONFLICT upserts.
READING_SOURCES = ("HES_KAFKA", "MDMS_VEE", "MDMS_VEE_BACKFILL", "HES_REST")
READING_QUALITIES = ("valid", "estimated", "failed", "raw")


class MeterReadingInterval(Base):
    """Per-meter, per-interval reading — populated from HES Kafka or MDMS VEE.

    NOTE: Partitioning by month is a follow-up; current MVP ships as a single
    table with a composite PK + supporting indexes. See TODO(013-mvp-phase2).
    """

    __tablename__ = "meter_reading_interval"

    meter_serial = Column(String(50), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    channel = Column(Integer, nullable=False, default=0)
    value = Column(Float, nullable=False, default=0.0)
    quality = Column(String(16), nullable=False, default="raw")
    source = Column(String(32), nullable=False)
    energy_kwh = Column(Float, nullable=True)
    energy_export_kwh = Column(Float, nullable=True)
    demand_kw = Column(Float, nullable=True)
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    power_factor = Column(Float, nullable=True)
    frequency = Column(Float, nullable=True)
    thd = Column(Float, nullable=True)
    is_estimated = Column(Boolean, nullable=False, default=False)
    is_edited = Column(Boolean, nullable=False, default=False)
    is_validated = Column(Boolean, nullable=False, default=False)
    source_priority = Column(SmallInteger, nullable=False, default=10)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    trace_id = Column(String(64), nullable=True)
    kafka_partition = Column(SmallInteger, nullable=True)
    kafka_offset = Column(BigInteger, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("meter_serial", "ts", "channel", name="pk_mri_serial_ts_ch"),
        Index("ix_mri_serial_ts", "meter_serial", "ts"),
        Index("ix_mri_ingested_at", "ingested_at"),
        Index("ix_mri_source", "source"),
    )


class MeterReadingDaily(Base):
    __tablename__ = "meter_reading_daily"

    meter_serial = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    kwh_import = Column(Float, nullable=False, default=0.0)
    kwh_export = Column(Float, nullable=False, default=0.0)
    max_demand_kw = Column(Float, nullable=True)
    min_voltage = Column(Float, nullable=True)
    max_voltage = Column(Float, nullable=True)
    avg_pf = Column(Float, nullable=True)
    reading_count = Column(Integer, nullable=True)
    estimated_count = Column(Integer, nullable=True)
    source = Column(String(32), nullable=False, default="MDMS_VEE")
    source_mix = Column(JSONB, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("meter_serial", "date", name="pk_mrd_serial_date"),
        Index("ix_mrd_serial_date", "meter_serial", "date"),
        Index("ix_mrd_date", "date"),
    )


class MeterReadingMonthly(Base):
    __tablename__ = "meter_reading_monthly"

    meter_serial = Column(String(50), nullable=False)
    year_month = Column(CHAR(7), nullable=False)  # 'YYYY-MM'
    kwh_import = Column(Float, nullable=False, default=0.0)
    kwh_export = Column(Float, nullable=False, default=0.0)
    max_demand_kw = Column(Float, nullable=True)
    avg_pf = Column(Float, nullable=True)
    reading_days = Column(Integer, nullable=True)
    vee_billing_kwh = Column(Float, nullable=True)
    reconciliation_delta_pct = Column(Float, nullable=True)
    source = Column(String(32), nullable=False, default="MDMS_VEE")
    source_mix = Column(JSONB, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("meter_serial", "year_month", name="pk_mrm_serial_month"),
        Index("ix_mrm_serial_month", "meter_serial", "year_month"),
    )
