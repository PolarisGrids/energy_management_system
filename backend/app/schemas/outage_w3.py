"""Spec-018 W3 outage schemas.

Kept distinct from ``schemas/outage.py`` which serves the spec-016 feeder-
scoped ``outage_incidents`` table. These match the ``outage_incident``
(singular) UUID/DTR-scoped model.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class OutageTimelineEventOut(BaseModel):
    event_type: str
    actor_user_id: Optional[str] = None
    details: Optional[Any] = None
    trace_id: Optional[str] = None
    at: datetime

    model_config = {"from_attributes": True}


class OutageIncidentW3Out(BaseModel):
    id: str
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    affected_dtr_ids: Optional[List[str]] = None
    affected_meter_count: int = 0
    restored_meter_count: int = 0
    confidence_pct: Optional[Decimal] = None
    saidi_contribution_s: Optional[int] = None
    trigger_trace_id: Optional[str] = None

    model_config = {"from_attributes": True}


class OutageIncidentW3Detail(OutageIncidentW3Out):
    timeline: List[OutageTimelineEventOut] = []


class OutageListResponse(BaseModel):
    total: int
    incidents: List[OutageIncidentW3Out]


class OutageAcknowledgeIn(BaseModel):
    note: Optional[str] = None


class OutageDispatchCrewIn(BaseModel):
    crew_id: str
    eta_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)
    note: Optional[str] = None


class OutageNoteIn(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class OutageFlisrActionIn(BaseModel):
    target_switch_id: Optional[str] = None
    note: Optional[str] = None


class OutageFlisrActionOut(BaseModel):
    id: str
    action: str
    target_switch_id: Optional[str] = None
    hes_command_id: Optional[str] = None
    status: str
    issued_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
