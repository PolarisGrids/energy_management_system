"""Saved dashboard layouts — spec 018 W4.T11.

CRUD under `/api/v1/dashboards`:

    GET    /                — list layouts (owned + shared with current role)
    POST   /                — create layout
    GET    /{id}            — get layout (own or shared-with-role)
    PATCH  /{id}            — update (own, or dashboard.admin)
    DELETE /{id}            — delete (own, or dashboard.admin)
    POST   /{id}/duplicate  — clone to a new layout owned by the caller

RBAC (spec 018 W4.T13):
  • Read requires no extra permission beyond authenticated user; visibility is
    scoped by owner/shared_with_roles.
  • Write on own layout is always allowed. Write on another user's layout
    requires ``dashboard.admin`` — enforced inline per-endpoint so we can
    still return owner-friendly 404s.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import P_DASHBOARD_ADMIN, has_permission
from app.db.base import get_db
from app.models.dashboard_layout import DashboardLayout
from app.models.user import User
from app.schemas.dashboard import (
    DashboardLayoutCreate,
    DashboardLayoutListItem,
    DashboardLayoutOut,
    DashboardLayoutUpdate,
)
from app.services.audit_publisher import publish_audit

router = APIRouter()


def _role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def _user_can_read(user: User, layout: DashboardLayout) -> bool:
    if layout.owner_user_id == str(user.id):
        return True
    role = _role_value(user)
    # shared_with_roles may be stored as JSON list on SQLite, TEXT[] on PG.
    roles = layout.shared_with_roles or []
    if role in roles:
        return True
    return has_permission(user, P_DASHBOARD_ADMIN)


def _user_can_write(user: User, layout: DashboardLayout) -> bool:
    if layout.owner_user_id == str(user.id):
        return True
    return has_permission(user, P_DASHBOARD_ADMIN)


def _get_or_404(db: Session, layout_id: str) -> DashboardLayout:
    row = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="dashboard layout not found")
    return row


@router.get("", response_model=List[DashboardLayoutListItem])
def list_layouts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return layouts owned by the user plus layouts shared with the user's role.

    Default layouts sort first, then by updated_at desc.
    """
    me = str(current_user.id)
    role = _role_value(current_user)

    owned = db.query(DashboardLayout).filter(DashboardLayout.owner_user_id == me).all()

    # For sharing, fetch all layouts then filter in Python. We can't rely on a
    # portable JSON-contains query across PG+SQLite without dialect-specific
    # code, and the layout count per site is expected to stay small (< 1000).
    shared_candidates = db.query(DashboardLayout).filter(
        DashboardLayout.owner_user_id != me
    ).all()
    shared = [r for r in shared_candidates if role in (r.shared_with_roles or [])]

    items: List[DashboardLayoutListItem] = []
    for r in owned:
        items.append(
            DashboardLayoutListItem(
                id=r.id,
                name=r.name,
                owner_user_id=r.owner_user_id,
                is_default=bool(r.is_default),
                shared=False,
                updated_at=r.updated_at,
            )
        )
    for r in shared:
        items.append(
            DashboardLayoutListItem(
                id=r.id,
                name=r.name,
                owner_user_id=r.owner_user_id,
                is_default=bool(r.is_default),
                shared=True,
                updated_at=r.updated_at,
            )
        )

    items.sort(key=lambda x: (not x.is_default, -x.updated_at.timestamp()))
    return items


@router.post("", response_model=DashboardLayoutOut, status_code=http_status.HTTP_201_CREATED)
async def create_layout(
    payload: DashboardLayoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = perf_counter()
    new_id = str(uuid.uuid4())
    # If creating a default, demote the caller's other defaults first.
    if payload.is_default:
        db.query(DashboardLayout).filter(
            DashboardLayout.owner_user_id == str(current_user.id),
            DashboardLayout.is_default == True,  # noqa: E712
        ).update({DashboardLayout.is_default: False})

    row = DashboardLayout(
        id=new_id,
        owner_user_id=str(current_user.id),
        name=payload.name,
        widgets=payload.widgets or [],
        shared_with_roles=payload.shared_with_roles or [],
        is_default=payload.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await publish_audit(
        action_type="WRITE",
        action_name="create_dashboard_layout",
        entity_type="DashboardLayout",
        entity_id=new_id,
        method="POST",
        path="/api/v1/dashboards",
        response_status=201,
        user_id=str(current_user.id),
        request_data={"name": payload.name, "is_default": payload.is_default},
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return DashboardLayoutOut.model_validate(row, from_attributes=True)


@router.get("/{layout_id}", response_model=DashboardLayoutOut)
def get_layout(
    layout_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _get_or_404(db, layout_id)
    if not _user_can_read(current_user, row):
        raise HTTPException(status_code=404, detail="dashboard layout not found")
    return DashboardLayoutOut.model_validate(row, from_attributes=True)


@router.patch("/{layout_id}", response_model=DashboardLayoutOut)
async def update_layout(
    layout_id: str,
    payload: DashboardLayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = perf_counter()
    row = _get_or_404(db, layout_id)
    if not _user_can_write(current_user, row):
        raise HTTPException(status_code=403, detail="cannot modify another user's layout")

    changed: dict = {}
    if payload.name is not None:
        changed["name"] = {"old": row.name, "new": payload.name}
        row.name = payload.name
    if payload.widgets is not None:
        changed["widgets"] = "updated"
        row.widgets = payload.widgets
    if payload.shared_with_roles is not None:
        changed["shared_with_roles"] = {
            "old": list(row.shared_with_roles or []),
            "new": payload.shared_with_roles,
        }
        row.shared_with_roles = payload.shared_with_roles
    if payload.is_default is not None and payload.is_default:
        # Demote any other default owned by the same user.
        db.query(DashboardLayout).filter(
            DashboardLayout.owner_user_id == row.owner_user_id,
            DashboardLayout.id != row.id,
            DashboardLayout.is_default == True,  # noqa: E712
        ).update({DashboardLayout.is_default: False})
        changed["is_default"] = {"old": row.is_default, "new": True}
        row.is_default = True
    elif payload.is_default is False:
        changed["is_default"] = {"old": row.is_default, "new": False}
        row.is_default = False

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    await publish_audit(
        action_type="WRITE",
        action_name="update_dashboard_layout",
        entity_type="DashboardLayout",
        entity_id=layout_id,
        method="PATCH",
        path=f"/api/v1/dashboards/{layout_id}",
        response_status=200,
        user_id=str(current_user.id),
        changes=changed,
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return DashboardLayoutOut.model_validate(row, from_attributes=True)


@router.delete("/{layout_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_layout(
    layout_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = perf_counter()
    row = _get_or_404(db, layout_id)
    if not _user_can_write(current_user, row):
        raise HTTPException(status_code=403, detail="cannot delete another user's layout")
    db.delete(row)
    db.commit()
    await publish_audit(
        action_type="DELETE",
        action_name="delete_dashboard_layout",
        entity_type="DashboardLayout",
        entity_id=layout_id,
        method="DELETE",
        path=f"/api/v1/dashboards/{layout_id}",
        response_status=204,
        user_id=str(current_user.id),
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return None


@router.post(
    "/{layout_id}/duplicate",
    response_model=DashboardLayoutOut,
    status_code=http_status.HTTP_201_CREATED,
)
async def duplicate_layout(
    layout_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = perf_counter()
    src = _get_or_404(db, layout_id)
    if not _user_can_read(current_user, src):
        raise HTTPException(status_code=404, detail="dashboard layout not found")
    new_id = str(uuid.uuid4())
    copy = DashboardLayout(
        id=new_id,
        owner_user_id=str(current_user.id),
        name=f"Copy of {src.name}",
        widgets=list(src.widgets or []),
        shared_with_roles=[],   # duplicates reset sharing
        is_default=False,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    await publish_audit(
        action_type="WRITE",
        action_name="duplicate_dashboard_layout",
        entity_type="DashboardLayout",
        entity_id=new_id,
        method="POST",
        path=f"/api/v1/dashboards/{layout_id}/duplicate",
        response_status=201,
        user_id=str(current_user.id),
        request_data={"source_id": layout_id},
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return DashboardLayoutOut.model_validate(copy, from_attributes=True)
