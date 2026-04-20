"""Pydantic schemas for dashboard_layout — spec 018 W4.T11."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DashboardLayoutBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    widgets: List[dict] = Field(default_factory=list)
    shared_with_roles: List[str] = Field(default_factory=list)
    is_default: bool = False


class DashboardLayoutCreate(DashboardLayoutBase):
    pass


class DashboardLayoutUpdate(BaseModel):
    name: Optional[str] = None
    widgets: Optional[List[dict]] = None
    shared_with_roles: Optional[List[str]] = None
    is_default: Optional[bool] = None


class DashboardLayoutOut(DashboardLayoutBase):
    id: str
    owner_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DashboardLayoutListItem(BaseModel):
    id: str
    name: str
    owner_user_id: str
    is_default: bool
    shared: bool  # True if this layout is shared with the current user (not owned)
    updated_at: datetime

    model_config = {"from_attributes": True}
