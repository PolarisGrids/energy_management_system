from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
from app.db.base import get_db
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_SIMULATION_MANAGE
from app.models.user import User
from app.models.simulation import SimulationScenario, SimulationStep, ScenarioStatus
from app.schemas.simulation import SimulationScenarioOut, ScenarioStart, ScenarioCommand
from app.services.audit_publisher import publish_audit
from app.services.simulation_engine import SimulationEngine

router = APIRouter()


@router.get("/", response_model=List[SimulationScenarioOut])
def list_scenarios(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(SimulationScenario).all()


@router.get("/{scenario_id}", response_model=SimulationScenarioOut)
def get_scenario(scenario_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    scenario = db.query(SimulationScenario).filter(SimulationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.post(
    "/{scenario_id}/start",
    response_model=SimulationScenarioOut,
    dependencies=[Depends(require_permission(P_SIMULATION_MANAGE))],
)
async def start_scenario(
    scenario_id: int,
    payload: ScenarioStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = db.query(SimulationScenario).filter(SimulationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.status == ScenarioStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Scenario already running")

    scenario.status = ScenarioStatus.RUNNING
    scenario.current_step = 0
    scenario.started_at = datetime.now(timezone.utc)
    scenario.completed_at = None
    if payload.parameters:
        scenario.parameters = {**(scenario.parameters or {}), **payload.parameters}
    db.commit()
    db.refresh(scenario)
    await publish_audit(
        action_type="WRITE",
        action_name="start_simulation_scenario",
        entity_type="SimulationScenario",
        entity_id=str(scenario.id),
        request_data=payload.model_dump() if payload else None,
        response_status=200,
        method="POST",
        path=f"/api/v1/simulation/{scenario_id}/start",
        user_id=str(current_user.id),
    )
    return scenario


@router.post(
    "/{scenario_id}/next-step",
    response_model=SimulationScenarioOut,
    dependencies=[Depends(require_permission(P_SIMULATION_MANAGE))],
)
async def advance_step(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = db.query(SimulationScenario).filter(SimulationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.status != ScenarioStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Scenario not running")

    engine = SimulationEngine(db)
    engine.apply_step(scenario)
    db.commit()
    db.refresh(scenario)
    await publish_audit(
        action_type="WRITE",
        action_name="advance_simulation_step",
        entity_type="SimulationScenario",
        entity_id=str(scenario.id),
        response_status=200,
        method="POST",
        path=f"/api/v1/simulation/{scenario_id}/next-step",
        user_id=str(current_user.id),
    )
    return scenario


@router.post(
    "/{scenario_id}/command",
    dependencies=[Depends(require_permission(P_SIMULATION_MANAGE))],
)
async def send_scenario_command(
    scenario_id: int,
    cmd: ScenarioCommand,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = db.query(SimulationScenario).filter(SimulationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    engine = SimulationEngine(db)
    result = engine.apply_command(scenario, cmd.command, cmd.target_id, cmd.value)
    db.commit()
    await publish_audit(
        action_type="WRITE",
        action_name="send_simulation_command",
        entity_type="SimulationScenario",
        entity_id=str(scenario.id),
        request_data=cmd.model_dump(),
        response_status=200,
        method="POST",
        path=f"/api/v1/simulation/{scenario_id}/command",
        user_id=str(current_user.id),
    )
    return {"success": True, "result": result}


@router.post(
    "/{scenario_id}/reset",
    response_model=SimulationScenarioOut,
    dependencies=[Depends(require_permission(P_SIMULATION_MANAGE))],
)
async def reset_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = db.query(SimulationScenario).filter(SimulationScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.status = ScenarioStatus.IDLE
    scenario.current_step = 0
    scenario.started_at = None
    scenario.completed_at = None
    db.commit()
    db.refresh(scenario)
    await publish_audit(
        action_type="WRITE",
        action_name="reset_simulation_scenario",
        entity_type="SimulationScenario",
        entity_id=str(scenario.id),
        response_status=200,
        method="POST",
        path=f"/api/v1/simulation/{scenario_id}/reset",
        user_id=str(current_user.id),
    )
    return scenario
