"""DER inverter equipment + per-inverter telemetry (W5).

An asset (PV array, BESS, EV charger) can host multiple inverters —
modelled one-to-many here. `DERInverterTelemetry` is intentionally a
single non-partitioned table at MVP; promote to weekly partitioning
mirroring `der_telemetry` once volume warrants.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


def _json_col():
    from sqlalchemy import JSON

    return JSON().with_variant(JSONB(), "postgresql")


class DERInverter(Base):
    __tablename__ = "der_inverter"

    id = Column(String(36), primary_key=True)
    asset_id = Column(String(100), nullable=False)
    manufacturer = Column(String(80), nullable=True)
    model = Column(String(80), nullable=True)
    serial_number = Column(String(80), nullable=True)
    firmware_version = Column(String(40), nullable=True)
    rated_ac_kw = Column(Numeric(10, 2), nullable=True)
    rated_dc_kw = Column(Numeric(10, 2), nullable=True)
    num_mppt_trackers = Column(SmallInteger, nullable=True)
    num_strings = Column(SmallInteger, nullable=True)
    phase_config = Column(String(10), nullable=True)
    ac_voltage_nominal_v = Column(Numeric(8, 2), nullable=True)
    comms_protocol = Column(String(20), nullable=True)
    ip_address = Column(String(45), nullable=True)
    installation_date = Column(Date, nullable=True)
    commissioned_at = Column(DateTime(timezone=True), nullable=True)
    warranty_expires = Column(Date, nullable=True)
    last_firmware_update = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="online")
    inverter_metadata = Column("metadata", _json_col(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("serial_number", name="uq_der_inverter_serial_number"),
        CheckConstraint(
            "status IN ('online','offline','fault','maintenance','commissioning')",
            name="ck_der_inverter_status",
        ),
        CheckConstraint(
            "phase_config IS NULL OR phase_config IN ('single','three')",
            name="ck_der_inverter_phase_config",
        ),
        Index("ix_der_inverter_asset_id", "asset_id"),
        Index("ix_der_inverter_status", "status"),
        Index("ix_der_inverter_manufacturer", "manufacturer"),
    )


class DERInverterTelemetry(Base):
    __tablename__ = "der_inverter_telemetry"

    inverter_id = Column(String(36), nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    ac_voltage_v = Column(Numeric(8, 2), nullable=True)
    ac_current_a = Column(Numeric(10, 3), nullable=True)
    ac_power_kw = Column(Numeric(12, 3), nullable=True)
    ac_frequency_hz = Column(Numeric(6, 3), nullable=True)
    power_factor = Column(Numeric(4, 3), nullable=True)
    dc_voltage_v = Column(Numeric(8, 2), nullable=True)
    dc_current_a = Column(Numeric(10, 3), nullable=True)
    strings = Column(_json_col(), nullable=True)
    temperature_c = Column(Numeric(5, 2), nullable=True)
    efficiency_pct = Column(Numeric(5, 2), nullable=True)
    fault_code = Column(String(40), nullable=True)
    fault_description = Column(Text, nullable=True)
    state = Column(String(20), nullable=True)
    ingested_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("inverter_id", "ts", name="pk_der_inverter_telemetry"),
        Index("ix_der_inverter_telemetry_inv_ts", "inverter_id", "ts"),
        Index("ix_der_inverter_telemetry_fault", "fault_code"),
    )
