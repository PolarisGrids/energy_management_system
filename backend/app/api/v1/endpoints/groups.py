"""Virtual object group endpoints — spec 018 W4.T3.

    GET    /api/v1/groups                  — list visible groups
    POST   /api/v1/groups                  — create
    GET    /api/v1/groups/{id}             — detail (selector + metadata)
    GET    /api/v1/groups/{id}/members     — resolved meter_serial list
    PATCH  /api/v1/groups/{id}             — update (owner or shared role)
    DELETE /api/v1/groups/{id}             — owner-only

Every write emits an audit event via :mod:`app.services.audit_publisher`.
Read access: owner, any role present in ``shared_with_roles``, or ADMIN.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.user import User, UserRole
from app.models.virtual_object_group import VirtualObjectGroup
from app.schemas.virtual_object_group import (
    VirtualObjectGroupCreate,
    VirtualObjectGroupMembersOut,
    VirtualObjectGroupOut,
    VirtualObjectGroupUpdate,
)
from app.services.audit_publisher import publish_audit
from app.services.group_resolver import resolve_group_members

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────


def _visible_filter(current_user: User):
    """Return a SQLAlchemy predicate for rows the user may read."""
    # Lightweight helper — callers use VirtualObjectGroup columns directly.
    return VirtualObjectGroup.owner_user_id == str(current_user.id)


def _user_can_read(group: VirtualObjectGroup, current_user: User) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    if group.owner_user_id == str(current_user.id):
        return True
    shared = list(group.shared_with_roles or [])
    return current_user.role.value in shared or current_user.role.name in shared


def _user_can_write(group: VirtualObjectGroup, current_user: User) -> bool:
    # Only owner + admin can update/delete; "shared" roles are read-only.
    return (
        current_user.role == UserRole.ADMIN
        or group.owner_user_id == str(current_user.id)
    )


def _get_or_404(db: Session, group_id: str) -> VirtualObjectGroup:
    row = db.query(VirtualObjectGroup).filter(VirtualObjectGroup.id == group_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="group not found")
    return row


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("", response_model=List[VirtualObjectGroupOut])
@router.get("/", response_model=List[VirtualObjectGroupOut])
def list_groups(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    name_contains: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[VirtualObjectGroupOut]:
    q = db.query(VirtualObjectGroup)
    if name_contains:
        q = q.filter(VirtualObjectGroup.name.ilike(f"%{name_contains}%"))
    rows = q.order_by(VirtualObjectGroup.updated_at.desc()).offset(offset).limit(limit).all()
    # Filter visibility in Python — the shared_with_roles JSON column isn't
    # easily indexable cross-dialect.
    visible = [r for r in rows if _user_can_read(r, current_user)]
    return [VirtualObjectGroupOut.model_validate(r) for r in visible]


@router.post("", response_model=VirtualObjectGroupOut, status_code=201)
async def create_group(
    payload: VirtualObjectGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VirtualObjectGroupOut:
    row_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    row = VirtualObjectGroup(
        id=row_id,
        name=payload.name,
        description=payload.description,
        selector=payload.selector or {},
        owner_user_id=str(current_user.id),
        shared_with_roles=payload.shared_with_roles,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    await publish_audit(
        action_type="WRITE",
        action_name="create_group",
        entity_type="VirtualObjectGroup",
        entity_id=row_id,
        method="POST",
        path="/api/v1/groups",
        response_status=201,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
    )
    return VirtualObjectGroupOut.model_validate(row)


@router.get("/{group_id}", response_model=VirtualObjectGroupOut)
def get_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VirtualObjectGroupOut:
    row = _get_or_404(db, group_id)
    if not _user_can_read(row, current_user):
        raise HTTPException(status_code=403, detail="forbidden")
    return VirtualObjectGroupOut.model_validate(row)


@router.get("/{group_id}/members", response_model=VirtualObjectGroupMembersOut)
def get_group_members(
    group_id: str,
    limit: int = Query(1000, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VirtualObjectGroupMembersOut:
    row = _get_or_404(db, group_id)
    if not _user_can_read(row, current_user):
        raise HTTPException(status_code=403, detail="forbidden")
    serials = resolve_group_members(db, row, limit=limit)
    return VirtualObjectGroupMembersOut(
        group_id=group_id, meter_serials=serials, count=len(serials)
    )


@router.patch("/{group_id}", response_model=VirtualObjectGroupOut)
async def update_group(
    group_id: str,
    payload: VirtualObjectGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VirtualObjectGroupOut:
    row = _get_or_404(db, group_id)
    if not _user_can_write(row, current_user):
        raise HTTPException(status_code=403, detail="forbidden")
    changes = {}
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if getattr(row, k) != v:
            changes[k] = {"old": getattr(row, k), "new": v}
            setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    await publish_audit(
        action_type="WRITE",
        action_name="update_group",
        entity_type="VirtualObjectGroup",
        entity_id=group_id,
        method="PATCH",
        path=f"/api/v1/groups/{group_id}",
        response_status=200,
        user_id=str(current_user.id),
        request_data=data,
        changes=changes,
    )
    return VirtualObjectGroupOut.model_validate(row)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _get_or_404(db, group_id)
    if not _user_can_write(row, current_user):
        raise HTTPException(status_code=403, detail="forbidden")
    db.delete(row)
    db.commit()
    await publish_audit(
        action_type="DELETE",
        action_name="delete_group",
        entity_type="VirtualObjectGroup",
        entity_id=group_id,
        method="DELETE",
        path=f"/api/v1/groups/{group_id}",
        response_status=204,
        user_id=str(current_user.id),
    )
    return None
