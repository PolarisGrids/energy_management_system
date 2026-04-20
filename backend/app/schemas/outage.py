"""Outage management schemas.

Pydantic v2 schemas for outage incidents, affected customers, and crew
dispatch. Used by Wave 3 outage correlator + `endpoints/outage.py`.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class OutageIncidentOut(BaseModel):
    id: int
    status: str  # open | investigating | restored | closed
    cause: Optional[str] = None  # power_failure | feeder_trip | manual | unknown
    opened_at: datetime
    restored_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    affected_meter_count: int
    affected_customer_count: int
    feeder_id: Optional[int] = None
    transformer_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: Optional[float] = None  # 0.0 .. 1.0 correlator confidence
    saidi_contribution_min: Optional[float] = None

    model_config = {"from_attributes": True}


class OutageIncidentListResponse(BaseModel):
    total: int
    incidents: List[OutageIncidentOut]


class OutageAcknowledge(BaseModel):
    acknowledged_by: str
    notes: Optional[str] = None


class OutageDispatchCrew(BaseModel):
    crew_id: str
    eta_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)
    dispatched_by: str
    notes: Optional[str] = None


class OutageRestorationEvent(BaseModel):
    """Reported/detected restoration of an outage incident."""
    restored_by: Optional[str] = None  # None when auto-detected from meter events
    restoration_type: str = Field("automatic", pattern="^(automatic|manual|flisr)$")
    notes: Optional[str] = None


class ReliabilityIndices(BaseModel):
    """SAIDI / SAIFI / CAIDI computed from outage incidents."""
    window_start: datetime
    window_end: datetime
    saidi_min: float
    saifi: float
    caidi_min: float
    total_customers: int
    total_incidents: int
