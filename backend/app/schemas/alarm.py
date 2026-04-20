from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.alarm import AlarmSeverity, AlarmType, AlarmStatus


class AlarmOut(BaseModel):
    id: int
    alarm_type: AlarmType
    severity: AlarmSeverity
    status: AlarmStatus
    meter_serial: Optional[str]
    transformer_id: Optional[int]
    feeder_id: Optional[int]
    title: str
    description: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    value: Optional[float]
    threshold: Optional[float]
    unit: Optional[str]
    triggered_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    acknowledged_by: Optional[str]

    model_config = {"from_attributes": True}


class AlarmAcknowledge(BaseModel):
    acknowledged_by: str


class AlarmResolve(BaseModel):
    resolved_by: str
