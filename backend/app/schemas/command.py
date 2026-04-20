"""Schemas for outbound command APIs (spec 018 W2B)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandIssueResponse(BaseModel):
    """Returned by single-meter connect/disconnect/command-issue endpoints."""

    command_id: str
    meter_serial: str
    command_type: str
    status: str  # QUEUED / FAILED (if HES breaker open etc.)
    issued_at: datetime
    detail: Optional[str] = None


class BatchDisconnectRequest(BaseModel):
    meter_serials: list[str] = Field(min_length=1, max_length=500)
    reason: Optional[str] = None


class BatchCommandResult(BaseModel):
    meter_serial: str
    command_id: Optional[str] = None
    status: str
    error: Optional[str] = None


class BatchDisconnectResponse(BaseModel):
    total: int
    queued: int
    failed: int
    results: list[BatchCommandResult]


class CommandLogOut(BaseModel):
    command_id: str
    meter_serial: str
    command_type: str
    status: str
    issued_at: datetime
    acked_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    response_payload: Optional[dict[str, Any]] = None
    trace_id: Optional[str] = None

    model_config = {"from_attributes": True}
