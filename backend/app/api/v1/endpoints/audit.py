from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from app.db.base import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.audit import AuditEvent

router = APIRouter()


@router.get("/events")
def list_events(
    event_type: Optional[str] = None,
    user: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(AuditEvent)
    if event_type and event_type != "All":
        q = q.filter(AuditEvent.event_type == event_type)
    if user and user != "All":
        q = q.filter(AuditEvent.user_name == user)
    if from_date:
        q = q.filter(AuditEvent.timestamp >= from_date)
    if to_date:
        q = q.filter(AuditEvent.timestamp <= to_date)
    total = q.count()
    events = q.order_by(desc(AuditEvent.timestamp)).offset(offset).limit(limit).all()
    return {
        "total": total,
        "events": [
            {"ts": e.timestamp.isoformat(), "user": e.user_name, "role": e.user_role,
             "type": e.event_type, "action": e.action, "resource": e.resource,
             "ip": e.ip_address, "result": e.result}
            for e in events
        ],
    }


@router.get("/summary")
def event_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(AuditEvent.id)).scalar()
    type_counts = db.query(AuditEvent.event_type, func.count()).group_by(AuditEvent.event_type).all()
    counts = {t: c for t, c in type_counts}
    users = [r[0] for r in db.query(AuditEvent.user_name).distinct().all()]
    return {
        "total": total, "commands": counts.get("Command", 0),
        "alarms": counts.get("Alarm", 0), "configs": counts.get("Configuration", 0),
        "logins": counts.get("Login", 0), "systems": counts.get("System", 0),
        "users": users,
    }
