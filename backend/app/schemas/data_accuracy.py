"""Pydantic schemas for Data Accuracy console — spec 018 W4.T14."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


AccuracyStatus = Literal[
    "healthy", "lagging", "missing_mdms", "missing_cis", "stale", "unknown"
]


class DataAccuracyRow(BaseModel):
    meter_serial: str
    hes_last_seen: Optional[datetime]
    mdms_last_validated: Optional[datetime]
    cis_last_billing: Optional[datetime]
    updated_at: Optional[datetime]
    status: AccuracyStatus


class DataAccuracyResponse(BaseModel):
    total: int
    rows: List[DataAccuracyRow]
    counts_by_status: dict[str, int]


class DataAccuracyReconcileResponse(BaseModel):
    meter_serial: str
    issue_id: str
    status: str = "reconciliation_scheduled"
