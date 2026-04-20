from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from app.models.simulation import ScenarioType, ScenarioStatus


class SimulationStepOut(BaseModel):
    id: int
    step_number: int
    description: str
    network_state: Optional[dict]
    alarms_triggered: Optional[list]
    commands_available: Optional[list]
    duration_seconds: float

    model_config = {"from_attributes": True}


class SimulationScenarioOut(BaseModel):
    id: int
    name: str
    scenario_type: ScenarioType
    status: ScenarioStatus
    description: Optional[str]
    feeder_id: Optional[int] = None
    transformer_id: Optional[int] = None
    der_asset_id: Optional[int] = None
    parameters: Optional[dict]
    current_step: int
    total_steps: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    steps: List[SimulationStepOut] = []

    model_config = {"from_attributes": True}


class ScenarioStart(BaseModel):
    parameters: Optional[dict] = None


class ScenarioCommand(BaseModel):
    command: str
    target_id: Optional[int] = None
    value: Optional[float] = None
    issued_by: str
