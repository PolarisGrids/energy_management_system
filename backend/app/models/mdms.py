from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, Index
from sqlalchemy.sql import func
from app.db.base import Base


class VEEDailySummary(Base):
    __tablename__ = "vee_daily_summary"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True)
    validated_count = Column(Integer, default=0)
    estimated_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_vee_date", "date"),
    )


class VEEException(Base):
    __tablename__ = "vee_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    meter_serial = Column(String(50), nullable=False)
    exception_type = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    original_value = Column(String(100), nullable=True)
    corrected_value = Column(String(100), nullable=True)
    status = Column(String(20), default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_vee_exc_date", "date"),
    )


class ConsumerAccount(Base):
    __tablename__ = "consumer_accounts"

    account_number = Column(String(50), primary_key=True)
    customer_name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=True)
    tariff_name = Column(String(100), nullable=True)
    meter_serial = Column(String(50), nullable=True)
    transformer_id = Column(String(50), nullable=True)
    phase = Column(String(20), default="Single")
    prepaid_balance = Column(Float, nullable=True)


class TariffSchedule(Base):
    __tablename__ = "tariff_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    tariff_type = Column(String(50), nullable=False)
    offpeak_rate = Column(Float, nullable=False)
    standard_rate = Column(Float, nullable=False)
    peak_rate = Column(Float, nullable=False)
    effective_from = Column(Date, nullable=False)
    currency = Column(String(10), default="ZAR")


class NTLSuspect(Base):
    __tablename__ = "ntl_suspects"

    id = Column(Integer, primary_key=True, index=True)
    meter_serial = Column(String(50), nullable=False)
    customer_name = Column(String(200), nullable=True)
    pattern_description = Column(String(500), nullable=True)
    risk_score = Column(Integer, nullable=False)
    flag = Column(String(20), nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_ntl_score", "risk_score"),
    )


class PowerQualityZone(Base):
    __tablename__ = "power_quality_zones"

    id = Column(Integer, primary_key=True, index=True)
    zone_name = Column(String(200), nullable=False)
    voltage_deviation_pct = Column(Float, nullable=False)
    thd_pct = Column(Float, nullable=False)
    flicker_pst = Column(Float, nullable=False)
    compliant = Column(Boolean, default=True)
    measured_at = Column(DateTime(timezone=True), server_default=func.now())
