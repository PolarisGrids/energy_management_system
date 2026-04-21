"""DER-side metrology — billing-grade interval reads + daily rollups (W5).

Distinct from `meter_reading_interval/_daily/_monthly` which are keyed by
the customer revenue meter serial. `der_metrology` is keyed by `asset_id`
so the DER pages don't depend on a separate revenue-meter ingestion path
and can carry generation/export/import/self-consumption splits cleanly.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.sql import func

from app.db.base import Base


class DERMetrology(Base):
    __tablename__ = "der_metrology"

    asset_id = Column(String(100), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    energy_generated_kwh = Column(Numeric(14, 4), nullable=True)
    energy_exported_kwh = Column(Numeric(14, 4), nullable=True)
    energy_imported_kwh = Column(Numeric(14, 4), nullable=True)
    energy_self_consumed_kwh = Column(Numeric(14, 4), nullable=True)
    voltage_avg = Column(Numeric(8, 2), nullable=True)
    current_avg = Column(Numeric(10, 3), nullable=True)
    power_factor = Column(Numeric(4, 3), nullable=True)
    frequency_hz = Column(Numeric(6, 3), nullable=True)
    meter_serial = Column(String(50), nullable=True)
    quality = Column(String(16), nullable=False, default="raw")
    source = Column(String(32), nullable=False, default="DER_TELEMETRY")
    is_estimated = Column(Boolean, nullable=False, default=False)
    ingested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("asset_id", "ts", name="pk_der_metrology_asset_ts"),
        CheckConstraint(
            "quality IN ('valid','estimated','failed','raw')",
            name="ck_der_metrology_quality",
        ),
        Index("ix_der_metrology_asset_ts", "asset_id", "ts"),
        Index("ix_der_metrology_meter_serial", "meter_serial"),
        Index("ix_der_metrology_ingested_at", "ingested_at"),
    )


class DERMetrologyDaily(Base):
    __tablename__ = "der_metrology_daily"

    asset_id = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    kwh_generated = Column(Numeric(14, 4), nullable=False, default=0)
    kwh_exported = Column(Numeric(14, 4), nullable=False, default=0)
    kwh_imported = Column(Numeric(14, 4), nullable=False, default=0)
    kwh_self_consumed = Column(Numeric(14, 4), nullable=False, default=0)
    peak_output_kw = Column(Numeric(12, 3), nullable=True)
    equivalent_hours = Column(Numeric(6, 3), nullable=True)
    achievement_pct = Column(Numeric(5, 2), nullable=True)
    reading_count = Column(Integer, nullable=True)
    estimated_count = Column(Integer, nullable=True)
    source = Column(String(32), nullable=False, default="DER_TELEMETRY")
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "asset_id", "date", name="pk_der_metrology_daily_asset_date"
        ),
        Index("ix_der_metrology_daily_date", "date"),
    )
