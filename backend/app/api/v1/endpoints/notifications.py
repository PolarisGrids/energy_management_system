"""Notification admin + user-preference endpoints — spec 016 US1 + US5."""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import (
    NOTIFICATIONS_READ,
    require_permission,
)
from app.db.base import get_db
from app.models.notifications import (
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    UserNotificationPreference,
)
from app.models.user import User

router = APIRouter()


class DeliveryOut(BaseModel):
    id: int
    channel: str
    recipient: str
    template_id: Optional[int]
    status: str
    retries: int
    last_error: Optional[str]
    meta: Optional[dict]
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class PreferenceIn(BaseModel):
    channels: list[str] = []
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    tz: Optional[str] = "Asia/Kolkata"


class PreferenceOut(PreferenceIn):
    user_id: int

    class Config:
        from_attributes = True


@router.get("/deliveries", response_model=list[DeliveryOut])
def list_deliveries(
    status: Optional[NotificationStatus] = None,
    channel: Optional[NotificationChannel] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(NOTIFICATIONS_READ)),
):
    q = db.query(NotificationDelivery)
    if status:
        q = q.filter(NotificationDelivery.status == status.value)
    if channel:
        q = q.filter(NotificationDelivery.channel == channel.value)
    return q.order_by(NotificationDelivery.id.desc()).offset(offset).limit(limit).all()


@router.get("/preferences", response_model=PreferenceOut)
def get_my_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = (
        db.query(UserNotificationPreference)
        .filter(UserNotificationPreference.user_id == user.id)
        .first()
    )
    if pref is None:
        return PreferenceOut(
            user_id=user.id,
            channels=[],
            quiet_hours_start=None,
            quiet_hours_end=None,
            tz="Asia/Kolkata",
        )
    return PreferenceOut(
        user_id=pref.user_id,
        channels=list(pref.channels or []),
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        tz=pref.tz,
    )


@router.put("/preferences", response_model=PreferenceOut)
def update_my_preferences(
    payload: PreferenceIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = (
        db.query(UserNotificationPreference)
        .filter(UserNotificationPreference.user_id == user.id)
        .first()
    )
    if pref is None:
        pref = UserNotificationPreference(
            user_id=user.id,
            channels=payload.channels,
            quiet_hours_start=payload.quiet_hours_start,
            quiet_hours_end=payload.quiet_hours_end,
            tz=payload.tz or "Asia/Kolkata",
        )
        db.add(pref)
    else:
        pref.channels = payload.channels
        pref.quiet_hours_start = payload.quiet_hours_start
        pref.quiet_hours_end = payload.quiet_hours_end
        pref.tz = payload.tz or pref.tz
    db.commit()
    db.refresh(pref)
    return PreferenceOut(
        user_id=pref.user_id,
        channels=list(pref.channels or []),
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        tz=pref.tz,
    )
