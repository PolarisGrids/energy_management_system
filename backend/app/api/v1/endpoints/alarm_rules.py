"""Alarm-rule CRUD endpoints — spec 018 W4.T4.

    GET    /api/v1/alarm-rules                    — list active + inactive rules
    POST   /api/v1/alarm-rules                    — create
    GET    /api/v1/alarm-rules/{id}               — detail
    PATCH  /api/v1/alarm-rules/{id}               — update (incl. toggle active)
    DELETE /api/v1/alarm-rules/{id}               — delete
    POST   /api/v1/alarm-rules/{id}/acknowledge   — ack a specific firing
    GET    /api/v1/alarm-rules/{id}/firings       — recent firing history
    GET    /api/v1/alarm-rules/{id}/deliveries    — notification delivery log

Writes emit audit events.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.alarm_rule import AlarmRule, AlarmRuleFiring
from app.models.notification_delivery import NotificationDelivery
from app.models.user import User
from app.models.virtual_object_group import VirtualObjectGroup
from app.services.audit_publisher import publish_audit

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────


class AlarmRuleCreate(BaseModel):
    group_id: str
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    condition: dict = Field(..., description="AST: {source, field, op, value, duration_seconds}")
    action: dict = Field(..., description="{channels: [...], webhook_url?, priority}")
    priority: int = Field(3, ge=1, le=5)
    active: bool = True
    schedule: Optional[dict] = None
    dedup_window_seconds: int = Field(300, ge=0, le=86400)


class AlarmRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    condition: Optional[dict] = None
    action: Optional[dict] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    active: Optional[bool] = None
    schedule: Optional[dict] = None
    dedup_window_seconds: Optional[int] = Field(None, ge=0, le=86400)


class AlarmRuleOut(BaseModel):
    id: str
    group_id: str
    name: str
    description: Optional[str]
    condition: dict
    action: dict
    priority: int
    active: bool
    schedule: Optional[dict]
    dedup_window_seconds: int
    owner_user_id: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AlarmRuleFiringOut(BaseModel):
    id: str
    rule_id: str
    fired_at: datetime
    dedup_key: str
    match_count: int
    sample_meter_serial: Optional[str]
    sample_dtr_id: Optional[str]
    context: Optional[dict]
    trace_id: Optional[str]
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    escalation_tier: int
    model_config = {"from_attributes": True}


class AckIn(BaseModel):
    firing_id: str
    note: Optional[str] = None


class NotificationDeliveryOut(BaseModel):
    id: str
    rule_id: Optional[str]
    firing_id: Optional[str]
    channel: str
    recipient: str
    subject: Optional[str]
    status: str
    provider_reference: Optional[str]
    error: Optional[str]
    escalation_tier: int
    sent_at: datetime
    send_after: Optional[datetime]
    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_rule_or_404(db: Session, rule_id: str) -> AlarmRule:
    r = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="alarm rule not found")
    return r


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("", response_model=List[AlarmRuleOut])
@router.get("/", response_model=List[AlarmRuleOut])
def list_rules(
    active: Optional[bool] = Query(None),
    group_id: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[AlarmRuleOut]:
    q = db.query(AlarmRule)
    if active is not None:
        q = q.filter(AlarmRule.active == active)
    if group_id:
        q = q.filter(AlarmRule.group_id == group_id)
    rows = q.order_by(AlarmRule.updated_at.desc()).offset(offset).limit(limit).all()
    return [AlarmRuleOut.model_validate(r) for r in rows]


@router.post("", response_model=AlarmRuleOut, status_code=201)
async def create_rule(
    payload: AlarmRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlarmRuleOut:
    if not db.query(VirtualObjectGroup).filter(
        VirtualObjectGroup.id == payload.group_id
    ).first():
        raise HTTPException(status_code=400, detail="group_id does not exist")

    rid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    row = AlarmRule(
        id=rid,
        group_id=payload.group_id,
        name=payload.name,
        description=payload.description,
        condition=payload.condition,
        action=payload.action,
        priority=payload.priority,
        active=payload.active,
        schedule=payload.schedule,
        dedup_window_seconds=payload.dedup_window_seconds,
        owner_user_id=str(current_user.id),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    await publish_audit(
        action_type="WRITE",
        action_name="create_alarm_rule",
        entity_type="AlarmRule",
        entity_id=rid,
        method="POST",
        path="/api/v1/alarm-rules",
        response_status=201,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
    )
    return AlarmRuleOut.model_validate(row)


@router.get("/{rule_id}", response_model=AlarmRuleOut)
def get_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AlarmRuleOut:
    return AlarmRuleOut.model_validate(_get_rule_or_404(db, rule_id))


@router.patch("/{rule_id}", response_model=AlarmRuleOut)
async def update_rule(
    rule_id: str,
    payload: AlarmRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlarmRuleOut:
    row = _get_rule_or_404(db, rule_id)
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
        action_name="update_alarm_rule",
        entity_type="AlarmRule",
        entity_id=rule_id,
        method="PATCH",
        path=f"/api/v1/alarm-rules/{rule_id}",
        response_status=200,
        user_id=str(current_user.id),
        request_data=data,
        changes=changes,
    )
    return AlarmRuleOut.model_validate(row)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _get_rule_or_404(db, rule_id)
    db.delete(row)
    db.commit()
    await publish_audit(
        action_type="DELETE",
        action_name="delete_alarm_rule",
        entity_type="AlarmRule",
        entity_id=rule_id,
        method="DELETE",
        path=f"/api/v1/alarm-rules/{rule_id}",
        response_status=204,
        user_id=str(current_user.id),
    )
    return None


@router.post("/{rule_id}/acknowledge", response_model=AlarmRuleFiringOut)
async def acknowledge_firing(
    rule_id: str,
    payload: AckIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlarmRuleFiringOut:
    _get_rule_or_404(db, rule_id)
    firing = (
        db.query(AlarmRuleFiring)
        .filter(AlarmRuleFiring.id == payload.firing_id, AlarmRuleFiring.rule_id == rule_id)
        .first()
    )
    if not firing:
        raise HTTPException(status_code=404, detail="firing not found for rule")
    if firing.acknowledged_at is not None:
        raise HTTPException(status_code=409, detail="already acknowledged")
    firing.acknowledged_at = datetime.now(timezone.utc)
    firing.acknowledged_by = str(current_user.id)
    db.commit()
    db.refresh(firing)
    await publish_audit(
        action_type="WRITE",
        action_name="acknowledge_alarm_firing",
        entity_type="AlarmRuleFiring",
        entity_id=payload.firing_id,
        method="POST",
        path=f"/api/v1/alarm-rules/{rule_id}/acknowledge",
        response_status=200,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
    )
    return AlarmRuleFiringOut.model_validate(firing)


@router.get("/{rule_id}/firings", response_model=List[AlarmRuleFiringOut])
def list_firings(
    rule_id: str,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[AlarmRuleFiringOut]:
    _get_rule_or_404(db, rule_id)
    rows = (
        db.query(AlarmRuleFiring)
        .filter(AlarmRuleFiring.rule_id == rule_id)
        .order_by(desc(AlarmRuleFiring.fired_at))
        .limit(limit)
        .all()
    )
    return [AlarmRuleFiringOut.model_validate(r) for r in rows]


@router.get("/{rule_id}/deliveries", response_model=List[NotificationDeliveryOut])
def list_deliveries(
    rule_id: str,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[NotificationDeliveryOut]:
    _get_rule_or_404(db, rule_id)
    rows = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.rule_id == rule_id)
        .order_by(desc(NotificationDelivery.sent_at))
        .limit(limit)
        .all()
    )
    return [NotificationDeliveryOut.model_validate(r) for r in rows]
