from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.meter import MeterType, MeterStatus, RelayState


class FeederOut(BaseModel):
    id: int
    name: str
    substation: str
    voltage_kv: float
    capacity_kva: float
    current_load_kw: float
    geojson: Optional[dict] = None

    model_config = {"from_attributes": True}


class TransformerOut(BaseModel):
    id: int
    name: str
    feeder_id: int
    latitude: float
    longitude: float
    capacity_kva: float
    current_load_kw: float
    loading_percent: float
    voltage_pu: float
    phase: str

    model_config = {"from_attributes": True}


class MeterOut(BaseModel):
    id: int
    serial: str
    transformer_id: int
    meter_type: MeterType
    status: MeterStatus
    relay_state: RelayState
    latitude: float
    longitude: float
    address: Optional[str]
    customer_name: Optional[str]
    account_number: Optional[str]
    tariff_class: str
    prepaid_balance: Optional[float]
    firmware_version: str
    comm_tech: str
    last_seen: datetime

    model_config = {"from_attributes": True}


class MeterListResponse(BaseModel):
    total: int
    meters: List[MeterOut]


class NetworkSummary(BaseModel):
    total_meters: int
    online_meters: int
    offline_meters: int
    tamper_meters: int
    disconnected_meters: int
    comm_success_rate: float
    total_feeders: int
    total_transformers: int
    active_alarms: int
