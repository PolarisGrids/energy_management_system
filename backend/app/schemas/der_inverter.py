"""Pydantic schemas for DER inverter records + telemetry (W5)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Inverter equipment ───────────────────────────────────────────────────────


class DERInverterBase(BaseModel):
    asset_id: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    rated_ac_kw: Optional[float] = None
    rated_dc_kw: Optional[float] = None
    num_mppt_trackers: Optional[int] = None
    num_strings: Optional[int] = None
    phase_config: Optional[str] = None  # single | three
    ac_voltage_nominal_v: Optional[float] = None
    comms_protocol: Optional[str] = None
    ip_address: Optional[str] = None
    installation_date: Optional[date] = None
    commissioned_at: Optional[datetime] = None
    warranty_expires: Optional[date] = None
    last_firmware_update: Optional[datetime] = None
    status: str = "online"


class DERInverterCreate(DERInverterBase):
    id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DERInverterUpdate(BaseModel):
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    rated_ac_kw: Optional[float] = None
    rated_dc_kw: Optional[float] = None
    num_mppt_trackers: Optional[int] = None
    num_strings: Optional[int] = None
    phase_config: Optional[str] = None
    ac_voltage_nominal_v: Optional[float] = None
    comms_protocol: Optional[str] = None
    ip_address: Optional[str] = None
    installation_date: Optional[date] = None
    commissioned_at: Optional[datetime] = None
    warranty_expires: Optional[date] = None
    last_firmware_update: Optional[datetime] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DERInverterOut(DERInverterBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # See DERConsumerOut — `inverter_metadata` is the model attribute name.
    inverter_metadata: Optional[dict[str, Any]] = Field(
        default=None, serialization_alias="metadata"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Inverter telemetry ───────────────────────────────────────────────────────


class DERInverterStringReading(BaseModel):
    idx: int
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_w: Optional[float] = None


class DERInverterTelemetryOut(BaseModel):
    inverter_id: str
    ts: datetime
    ac_voltage_v: Optional[float] = None
    ac_current_a: Optional[float] = None
    ac_power_kw: Optional[float] = None
    ac_frequency_hz: Optional[float] = None
    power_factor: Optional[float] = None
    dc_voltage_v: Optional[float] = None
    dc_current_a: Optional[float] = None
    strings: Optional[List[DERInverterStringReading]] = None
    temperature_c: Optional[float] = None
    efficiency_pct: Optional[float] = None
    fault_code: Optional[str] = None
    fault_description: Optional[str] = None
    state: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
