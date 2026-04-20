"""Report schemas.

Pydantic v2 schemas for scheduled reports + EGSM report proxy metadata.
Used by Wave 4 `endpoints/reports.py` + scheduled report worker.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ReportDefinitionOut(BaseModel):
    id: int
    name: str
    category: str  # energy-audit | load-management | power-quality | loss-analytics | reliability-indices
    path: str  # upstream MDMS path, e.g. /api/v1/egsm-reports/energy-audit/feeder-loss-summary
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ReportRunRequest(BaseModel):
    """Trigger an ad-hoc report generation."""
    report_id: int
    filters: Optional[Dict[str, Any]] = None  # hierarchy filters (division, feeder, dtr, ...)
    format: str = Field("json", pattern="^(json|csv|pdf)$")


class ReportRunResponse(BaseModel):
    run_id: str
    status: str  # queued | running | complete | failed
    started_at: datetime
    finished_at: Optional[datetime] = None
    row_count: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None


class ScheduledReportOut(BaseModel):
    id: int
    report_id: int
    cron: str  # standard 5-field cron
    recipients: List[str]
    format: str
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledReportCreate(BaseModel):
    report_id: int
    cron: str
    recipients: List[str]
    format: str = Field("pdf", pattern="^(json|csv|pdf)$")
    enabled: bool = True


class ScheduledReportUpdate(BaseModel):
    cron: Optional[str] = None
    recipients: Optional[List[str]] = None
    format: Optional[str] = Field(None, pattern="^(json|csv|pdf)$")
    enabled: Optional[bool] = None
