from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.der import DERType, DERStatus


class DERAssetOut(BaseModel):
    id: int
    name: str
    asset_type: DERType
    status: DERStatus
    transformer_id: Optional[int]
    meter_serial: Optional[str]
    latitude: float
    longitude: float
    rated_capacity_kw: float
    current_output_kw: float
    panel_area_m2: Optional[float]
    inverter_efficiency: Optional[float]
    generation_today_kwh: Optional[float]
    generation_achievement_rate: Optional[float]
    capacity_kwh: Optional[float]
    state_of_charge: Optional[float]
    charge_cycles: Optional[int]
    revenue_today: Optional[float]
    num_ports: Optional[int]
    active_sessions: Optional[int]
    energy_dispensed_today_kwh: Optional[float]
    fee_collected_today: Optional[float]
    islanded: Optional[bool]
    reverse_power_flow: Optional[bool]
    last_updated: datetime

    model_config = {"from_attributes": True}


class DERCommand(BaseModel):
    command: str  # curtail, connect, disconnect, set_power
    value: Optional[float] = None
    issued_by: str
