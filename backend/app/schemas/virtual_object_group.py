"""Schemas for virtual object group CRUD — spec 018 W4.T3."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GroupSelector(BaseModel):
    """Shape of ``virtual_object_group.selector``.

    All sub-fields are optional. An empty selector matches every meter in
    the catalogue — callers must intersect with role / RBAC scope.
    """

    hierarchy: Dict[str, List[str]] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class VirtualObjectGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    selector: Dict[str, Any] = Field(default_factory=dict)
    shared_with_roles: Optional[List[str]] = None


class VirtualObjectGroupCreate(VirtualObjectGroupBase):
    pass


class VirtualObjectGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    selector: Optional[Dict[str, Any]] = None
    shared_with_roles: Optional[List[str]] = None


class VirtualObjectGroupOut(VirtualObjectGroupBase):
    id: str
    owner_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VirtualObjectGroupMembersOut(BaseModel):
    group_id: str
    meter_serials: List[str]
    count: int


__all__ = [
    "GroupSelector",
    "VirtualObjectGroupCreate",
    "VirtualObjectGroupUpdate",
    "VirtualObjectGroupOut",
    "VirtualObjectGroupMembersOut",
]
