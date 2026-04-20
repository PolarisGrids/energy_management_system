from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_ALARM_MANAGE
from app.models.user import User
from app.models.alarm import Alarm, AlarmStatus, AlarmSeverity, AlarmType
from app.schemas.alarm import AlarmOut, AlarmAcknowledge, AlarmResolve
from sqlalchemy import desc

from app.services.audit_publisher import publish_audit

router = APIRouter()


@router.get("/", response_model=List[AlarmOut])
def list_alarms(
    status: Optional[AlarmStatus] = None,
    severity: Optional[AlarmSeverity] = None,
    alarm_type: Optional[AlarmType] = None,
    limit: int = Query(50, le=200),
    skip: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Alarm)
    if status:
        q = q.filter(Alarm.status == status)
    if severity:
        q = q.filter(Alarm.severity == severity)
    if alarm_type:
        q = q.filter(Alarm.alarm_type == alarm_type)
    return q.order_by(desc(Alarm.triggered_at)).offset(skip).limit(limit).all()


@router.get("/active", response_model=List[AlarmOut])
def active_alarms(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return (
        db.query(Alarm)
        .filter(Alarm.status == AlarmStatus.ACTIVE)
        .order_by(desc(Alarm.triggered_at))
        .limit(100)
        .all()
    )


@router.post(
    "/{alarm_id}/acknowledge",
    response_model=AlarmOut,
    dependencies=[Depends(require_permission(P_ALARM_MANAGE))],
)
async def acknowledge_alarm(
    alarm_id: int,
    payload: AlarmAcknowledge,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alarm not found")
    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.acknowledged_at = datetime.now(timezone.utc)
    alarm.acknowledged_by = payload.acknowledged_by
    db.commit()
    db.refresh(alarm)
    await publish_audit(
        action_type="WRITE",
        action_name="acknowledge_alarm",
        entity_type="Alarm",
        entity_id=str(alarm.id),
        response_status=200,
        method="POST",
        path=f"/api/v1/alarms/{alarm_id}/acknowledge",
        user_id=str(current_user.id),
    )
    return alarm


@router.post(
    "/{alarm_id}/resolve",
    response_model=AlarmOut,
    dependencies=[Depends(require_permission(P_ALARM_MANAGE))],
)
async def resolve_alarm(
    alarm_id: int,
    payload: AlarmResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alarm not found")
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = datetime.now(timezone.utc)
    alarm.acknowledged_by = payload.resolved_by
    db.commit()
    db.refresh(alarm)
    await publish_audit(
        action_type="WRITE",
        action_name="resolve_alarm",
        entity_type="Alarm",
        entity_id=str(alarm.id),
        response_status=200,
        method="POST",
        path=f"/api/v1/alarms/{alarm_id}/resolve",
        user_id=str(current_user.id),
    )
    return alarm
