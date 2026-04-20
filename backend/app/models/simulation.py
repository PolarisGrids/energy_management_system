from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, JSON, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class ScenarioType(str, enum.Enum):
    SOLAR_OVERVOLTAGE = "solar_overvoltage"
    EV_FAST_CHARGING = "ev_fast_charging"
    PEAKING_MICROGRID = "peaking_microgrid"
    NETWORK_FAULT = "network_fault"
    SENSOR_ASSET = "sensor_asset"


class ScenarioStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"


class SimulationScenario(Base):
    __tablename__ = "simulation_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    scenario_type = Column(Enum(ScenarioType), nullable=False)
    status = Column(Enum(ScenarioStatus), default=ScenarioStatus.IDLE)
    description = Column(Text, nullable=True)
    feeder_id = Column(Integer, nullable=True)
    transformer_id = Column(Integer, nullable=True)
    der_asset_id = Column(Integer, nullable=True)
    parameters = Column(JSON, nullable=True)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    steps = relationship("SimulationStep", back_populates="scenario", order_by="SimulationStep.step_number")


class SimulationStep(Base):
    __tablename__ = "simulation_steps"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("simulation_scenarios.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    description = Column(String(500), nullable=False)
    network_state = Column(JSON, nullable=True)
    alarms_triggered = Column(JSON, nullable=True)
    commands_available = Column(JSON, nullable=True)
    duration_seconds = Column(Float, default=5.0)
    scenario = relationship("SimulationScenario", back_populates="steps")
