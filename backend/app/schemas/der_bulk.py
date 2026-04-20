"""DER bulk-import + DER command schemas (spec 018 W2B)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class DERAssetIn(BaseModel):
    id: str
    type: Literal["pv", "bess", "ev", "microgrid"]
    name: Optional[str] = None
    dtr_id: Optional[str] = None
    feeder_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    capacity_kw: Optional[float] = None
    capacity_kwh: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None


class DERBulkImportRequest(BaseModel):
    preset: str
    seeded_at: Optional[datetime] = None
    assets: list[DERAssetIn] = Field(min_length=1, max_length=500)


class DERBulkImportError(BaseModel):
    index: int
    asset_id: str
    error_code: str
    message: str


class DERBulkImportResponse(BaseModel):
    inserted: int
    updated: int
    errors: list[DERBulkImportError]
    preset: str


class DERCommandIssueRequest(BaseModel):
    command_type: Literal[
        "DER_CURTAIL",
        "DER_SET_ACTIVE_POWER",
        "DER_SET_REACTIVE_POWER",
        "EV_CHARGER_SET_POWER",
    ]
    setpoint: Optional[float] = None


class DERCommandIssueResponse(BaseModel):
    command_id: str
    asset_id: str
    command_type: str
    setpoint: Optional[float] = None
    status: str
    issued_at: datetime
