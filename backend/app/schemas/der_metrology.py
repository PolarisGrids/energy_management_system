"""Pydantic schemas for DER metrology endpoints (W5).

DER-side billing-grade readings — distinct from `meter_reading_*` (customer
revenue meters). Keyed by `asset_id`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class DERMetrologyReading(BaseModel):
    asset_id: str
    ts: datetime
    energy_generated_kwh: Optional[float] = None
    energy_exported_kwh: Optional[float] = None
    energy_imported_kwh: Optional[float] = None
    energy_self_consumed_kwh: Optional[float] = None
    voltage_avg: Optional[float] = None
    current_avg: Optional[float] = None
    power_factor: Optional[float] = None
    frequency_hz: Optional[float] = None
    meter_serial: Optional[str] = None
    quality: str = "raw"
    source: str = "DER_TELEMETRY"
    is_estimated: bool = False

    model_config = ConfigDict(from_attributes=True)


class DERMetrologyDailyRow(BaseModel):
    asset_id: str
    date: date
    kwh_generated: float = 0.0
    kwh_exported: float = 0.0
    kwh_imported: float = 0.0
    kwh_self_consumed: float = 0.0
    peak_output_kw: Optional[float] = None
    equivalent_hours: Optional[float] = None
    achievement_pct: Optional[float] = None
    reading_count: Optional[int] = None
    estimated_count: Optional[int] = None
    source: str = "DER_TELEMETRY"

    model_config = ConfigDict(from_attributes=True)


class DERMetrologyResponse(BaseModel):
    """Envelope returned by GET /der/{asset_id}/metrology."""

    asset_id: str
    window: str                      # '24h' | '7d' | '30d' | 'custom'
    interval: List[DERMetrologyReading] = []
    daily: List[DERMetrologyDailyRow] = []
    banner: Optional[str] = None
