"""DER endpoints — legacy read + spec-018 W2B command path.

Reads expose both legacy `der_assets` (int PK seeded data) and the new
spec-018 `der_asset` table (string PK, populated by simulator bulk-import).

Commands go through HES routing-service (`POST /api/v1/commands`) with type
∈ {DER_CURTAIL, DER_SET_ACTIVE_POWER, DER_SET_REACTIVE_POWER, EV_CHARGER_SET_POWER},
gated by `SMART_INVERTER_COMMANDS_ENABLED`. A row is persisted in `der_command`
as QUEUED; Kafka consumer flips it to CONFIRMED (not implemented here — W2A).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_DER_COMMAND
from app.db.base import get_db
from app.models.der import DERAsset, DERType
from app.models.der_ems import DERAssetEMS, DERCommandEMS
from app.models.user import User
from app.schemas.der import DERAssetOut, DERCommand
from app.schemas.der_bulk import DERCommandIssueRequest, DERCommandIssueResponse
from app.services.hes_client import CircuitBreakerError, hes_client

try:
    from otel_common.audit import audit  # type: ignore
except ImportError:  # pragma: no cover
    async def audit(**_kwargs):
        return None


logger = logging.getLogger(__name__)
router = APIRouter()


# ── Legacy (int-PK) reads — kept for existing UI ──


@router.get("/", response_model=List[DERAssetOut])
def list_der_assets(
    asset_type: Optional[DERType] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(DERAsset)
    if asset_type:
        q = q.filter(DERAsset.asset_type == asset_type)
    return q.all()


@router.get("/legacy/{asset_id}", response_model=DERAssetOut)
def get_legacy_der_asset(
    asset_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    asset = db.query(DERAsset).filter(DERAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="DER asset not found")
    return asset


@router.post(
    "/legacy/{asset_id}/command",
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def legacy_send_der_command(
    asset_id: int,
    cmd: DERCommand,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Legacy in-DB command — retained for tests that still mutate seed data."""
    from app.models.der import DERStatus  # local import to avoid circular surprises

    asset = db.query(DERAsset).filter(DERAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="DER asset not found")
    if cmd.command == "curtail":
        asset.status = DERStatus.CURTAILED
        if cmd.value is not None:
            asset.current_output_kw = min(asset.rated_capacity_kw, cmd.value)
    elif cmd.command == "connect":
        asset.status = DERStatus.ONLINE
    elif cmd.command == "disconnect":
        asset.status = DERStatus.OFFLINE
        asset.current_output_kw = 0.0
    elif cmd.command == "set_power" and cmd.value is not None:
        asset.current_output_kw = min(asset.rated_capacity_kw, max(0.0, cmd.value))
    db.commit()
    return {
        "success": True,
        "asset_id": asset_id,
        "command": cmd.command,
        "issued_by": cmd.issued_by,
    }


# ── Spec 018 W2B — DER command via HES (string asset_id) ──


@router.post(
    "/{asset_id}/command",
    response_model=DERCommandIssueResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
async def send_der_command(
    asset_id: str,
    payload: DERCommandIssueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forward a DER/EV command to HES routing and persist `der_command`."""
    # Feature flag gate (spec 018 REQ + plan): default OFF outside dev.
    if not settings.SMART_INVERTER_COMMANDS_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="feature disabled",
        )
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled",
        )

    asset = db.query(DERAssetEMS).filter(DERAssetEMS.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="DER asset not found")

    command_id = str(uuid.uuid4())
    row = DERCommandEMS(
        id=command_id,
        asset_id=asset.id,
        command_type=payload.command_type,
        setpoint=payload.setpoint,
        status="QUEUED",
        issued_at=datetime.now(timezone.utc),
        issuer_user_id=str(current_user.id),
        trace_id=current_trace_id(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    hes_payload = {
        "asset_id": asset_id,
        "setpoint": payload.setpoint,
        "command_id": command_id,
    }
    err: Optional[str] = None
    try:
        resp = await hes_client.post_command(
            type_=payload.command_type,
            meter_serial=asset_id,  # HES command uses asset_id in meter_serial slot for DER
            payload=hes_payload,
        )
        if hasattr(resp, "json"):
            row.response_payload = resp.json()
            db.commit()
    except CircuitBreakerError as exc:
        err = f"HES circuit open: {exc}"
        row.status = "FAILED"
        row.response_payload = {"error": "circuit_open"}
        db.commit()
    except Exception as exc:
        err = f"HES transport failure: {exc}"
        row.status = "FAILED"
        row.response_payload = {"error": "transport", "detail": str(exc)[:500]}
        db.commit()

    await audit(
        action_type="WRITE",
        action_name="der_command_issue",
        entity_type="DERAsset",
        entity_id=asset_id,
        request_data={"command_id": command_id, **payload.model_dump()},
        status=202 if err is None else 503,
        method="POST",
        path=f"/api/v1/der/{asset_id}/command",
        user_id=str(current_user.id),
    )

    if err:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"command_id": command_id, "error": err},
        )

    return DERCommandIssueResponse(
        command_id=command_id,
        asset_id=asset_id,
        command_type=payload.command_type,
        setpoint=payload.setpoint,
        status=row.status,
        issued_at=row.issued_at,
    )
