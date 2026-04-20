"""NTL (Non-Technical Loss) suspect schemas.

Pydantic v2 schemas for NTL detection workflows. Minimal surface area for
Wave 3 (`endpoints/ntl.py`); extend as MDMS scoring engine integration lands.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class NTLSuspectOut(BaseModel):
    id: int
    meter_serial: str
    customer_name: Optional[str] = None
    pattern_description: Optional[str] = None
    risk_score: int
    flag: str
    detected_at: datetime

    model_config = {"from_attributes": True}


class NTLSuspectListResponse(BaseModel):
    total: int
    suspects: List[NTLSuspectOut]


class NTLFeedback(BaseModel):
    """Operator feedback on a suspect classification (confirm / false-positive)."""
    suspect_id: int
    verdict: str = Field(..., pattern="^(confirmed|false_positive|investigating)$")
    notes: Optional[str] = None
    reviewed_by: str


class NTLScoringStatus(BaseModel):
    """Health of the upstream MDMS NTL scoring engine."""
    available: bool
    source: str  # "mdms" | "local"
    last_refresh: Optional[datetime] = None
    message: Optional[str] = None
