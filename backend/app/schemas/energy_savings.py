"""Pydantic schemas for /api/v1/energy-savings/* endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Hierarchy ────────────────────────────────────────────────────────────────


class OrgUnitNode(BaseModel):
    id: str
    parent_id: Optional[str] = None
    level: str
    name: str
    code: Optional[str] = None
    meter_serial: Optional[str] = None
    children: List["OrgUnitNode"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


OrgUnitNode.model_rebuild()


# ── Tariff ───────────────────────────────────────────────────────────────────


class TouTariffOut(BaseModel):
    id: int
    name: str
    currency: str = "ZAR"
    peak_rate: float
    standard_rate: float
    offpeak_rate: float
    peak_windows: str
    offpeak_windows: str
    is_default: bool = False
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TouTariffUpdate(BaseModel):
    peak_rate: Optional[float] = Field(default=None, gt=0)
    standard_rate: Optional[float] = Field(default=None, gt=0)
    offpeak_rate: Optional[float] = Field(default=None, gt=0)
    peak_windows: Optional[str] = None
    offpeak_windows: Optional[str] = None


# ── Appliance ────────────────────────────────────────────────────────────────


class ApplianceCatalogOut(BaseModel):
    code: str
    category: str
    display_name: str
    typical_kw: float
    typical_running_hours: float
    shiftable_hours: float
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApplianceUsageOut(BaseModel):
    id: str
    org_unit_id: str
    appliance_code: str
    display_name: str
    category: str
    typical_kw: float
    count: int
    peak_hours: float
    standard_hours: float
    offpeak_hours: float
    shiftable_peak_hours: float
    # Derived convenience fields for the frontend table.
    total_hours: float
    daily_kwh: float

    model_config = ConfigDict(from_attributes=True)


# ── Summary (TOU breakdown + cost) ───────────────────────────────────────────


class BandTotals(BaseModel):
    kwh: float
    cost: float


class TouSummary(BaseModel):
    org_unit_id: str
    org_unit_name: str
    level: str
    customer_count: int
    appliance_count: int
    total_kwh: float
    peak: BandTotals
    standard: BandTotals
    offpeak: BandTotals
    total_cost: float
    currency: str = "ZAR"
    # 24h profile split by band — each list has 24 floats (kW per hour).
    hourly_peak_kw: List[float]
    hourly_standard_kw: List[float]
    hourly_offpeak_kw: List[float]
    tariff: TouTariffOut


# ── Scenario (shift peak -> offpeak) ─────────────────────────────────────────


class ApplianceShiftOverride(BaseModel):
    appliance_usage_id: str
    shift_hours: float = Field(..., ge=0)


class ShiftScenarioRequest(BaseModel):
    org_unit_id: str
    # If omitted, applies each appliance's `shiftable_peak_hours` as the shift.
    overrides: Optional[List[ApplianceShiftOverride]] = None
    # Optional one-off tariff overrides — do NOT persist.
    tariff: Optional[TouTariffUpdate] = None


class ApplianceShiftRow(BaseModel):
    appliance_usage_id: str
    display_name: str
    category: str
    shift_hours: float
    kwh_shifted: float
    saving: float


class ShiftScenarioResponse(BaseModel):
    org_unit_id: str
    before: TouSummary
    after: TouSummary
    saving_kwh: float
    saving_cost: float
    saving_pct: float
    shifted: List[ApplianceShiftRow]
