from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TransformerSensorOut(BaseModel):
    id: int
    transformer_id: int
    sensor_type: str
    name: str
    value: float
    unit: str
    threshold_warning: Optional[float]
    threshold_critical: Optional[float]
    status: str
    last_updated: Optional[datetime]

    model_config = {"from_attributes": True}


class SensorThresholdUpdate(BaseModel):
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None


class SensorHistoryPoint(BaseModel):
    timestamp: str
    value: float


class SensorHistoryOut(BaseModel):
    sensor_id: int
    sensor_type: str
    unit: str
    history: List[SensorHistoryPoint]
    banner: Optional[str] = None  # spec 018 W2B.T11 — empty-history hint
