"""AppBuilder schemas — spec 018 W4.T6.

Pydantic v2 schemas for user-defined apps, rules, and Python algorithms
authored via the visual AppBuilder. Versioned (slug, version) identity per
data-model.md; status lifecycle DRAFT → PREVIEW → PUBLISHED → ARCHIVED.

Also holds schemas for scheduled reports (W4.T10).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Common ───────────────────────────────────────────────────────────────────

STATUS_PATTERN = r"^(DRAFT|PREVIEW|PUBLISHED|ARCHIVED)$"
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,119}$"


class _VersionedBase(BaseModel):
    id: str
    slug: str
    version: int
    name: str
    author_user_id: str
    status: str
    definition: Dict[str, Any]
    published_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── App Definition ───────────────────────────────────────────────────────────


class AppDefOut(_VersionedBase):
    description: Optional[str] = None
    required_role: Optional[str] = None


class AppDefCreate(BaseModel):
    slug: str = Field(..., pattern=SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    definition: Dict[str, Any] = Field(default_factory=dict)
    required_role: Optional[str] = None


class AppDefUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None
    required_role: Optional[str] = None


# ─── Rule Definition (AppBuilder-scope) ───────────────────────────────────────


class RuleDefOut(_VersionedBase):
    app_slug: Optional[str] = None


class RuleDefCreate(BaseModel):
    slug: str = Field(..., pattern=SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)
    definition: Dict[str, Any] = Field(default_factory=dict)
    app_slug: Optional[str] = Field(None, pattern=SLUG_PATTERN)


class RuleDefUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    definition: Optional[Dict[str, Any]] = None
    app_slug: Optional[str] = None


# ─── Algorithm Definition ────────────────────────────────────────────────────


class AlgorithmDefOut(_VersionedBase):
    description: Optional[str] = None
    source: str


class AlgorithmDefCreate(BaseModel):
    slug: str = Field(..., pattern=SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    source: str
    definition: Dict[str, Any] = Field(default_factory=dict)


class AlgorithmDefUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    source: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None


class AlgorithmRunRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(5.0, ge=0.1, le=30.0)


class AlgorithmRunResponse(BaseModel):
    status: str  # ok | error | timeout
    result: Optional[Any] = None
    stdout: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


# ─── Publish workflow ────────────────────────────────────────────────────────


class PublishRequest(BaseModel):
    notes: Optional[str] = None


# ─── Scheduled Reports (W4.T10) ──────────────────────────────────────────────


class ScheduledReportOut(BaseModel):
    id: str
    owner_user_id: str
    name: str
    report_ref: str
    params: Dict[str, Any] = Field(default_factory=dict)
    schedule_cron: str
    recipients: List[str] = Field(default_factory=list)
    enabled: bool
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduledReportCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_ref: str = Field(..., min_length=1, max_length=300)
    params: Dict[str, Any] = Field(default_factory=dict)
    schedule_cron: str = Field(..., min_length=1, max_length=100)
    recipients: List[str] = Field(default_factory=list)
    enabled: bool = True


class ScheduledReportUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    report_ref: Optional[str] = Field(None, min_length=1, max_length=300)
    params: Optional[Dict[str, Any]] = None
    schedule_cron: Optional[str] = Field(None, min_length=1, max_length=100)
    recipients: Optional[List[str]] = None
    enabled: Optional[bool] = None


class ScheduledReportRunResult(BaseModel):
    scheduled_report_id: str
    status: str  # ok | error
    started_at: datetime
    finished_at: datetime
    bytes_sent: Optional[int] = None
    recipients_sent: int = 0
    error: Optional[str] = None
