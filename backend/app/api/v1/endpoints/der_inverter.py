"""DER inverter equipment + per-inverter telemetry endpoints (W5).

Routes mounted under `/der`:

* `GET   /der/{asset_id}/inverters`        — list inverters for an asset
* `POST  /der/{asset_id}/inverters`        — register new inverter
* `GET   /der/inverters/{inverter_id}`     — single inverter equipment record
* `PATCH /der/inverters/{inverter_id}`     — update equipment record
* `DELETE/der/inverters/{inverter_id}`     — remove (decommission)
* `GET   /der/inverters/{inverter_id}/telemetry?window=1h|24h|7d|30d`
                                           — recent operational readings
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import P_DER_COMMAND, P_DER_READ, require_permission
from app.db.base import get_db
from app.models.der_ems import DERAssetEMS
from app.models.der_inverter import DERInverter, DERInverterTelemetry
from app.models.user import User
from app.schemas.der_inverter import (
    DERInverterCreate,
    DERInverterOut,
    DERInverterTelemetryOut,
    DERInverterUpdate,
)

router = APIRouter()


_TELEMETRY_WINDOWS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


# ── Per-asset listing + create ───────────────────────────────────────────────


@router.get(
    "/{asset_id}/inverters",
    response_model=List[DERInverterOut],
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def list_asset_inverters(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(DERAssetEMS).filter(DERAssetEMS.id == asset_id).first():
        raise HTTPException(404, detail="asset not found")
    return (
        db.query(DERInverter)
        .filter(DERInverter.asset_id == asset_id)
        .order_by(DERInverter.created_at)
        .all()
    )


@router.post(
    "/{asset_id}/inverters",
    response_model=DERInverterOut,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def create_inverter(
    asset_id: str,
    payload: DERInverterCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(DERAssetEMS).filter(DERAssetEMS.id == asset_id).first():
        raise HTTPException(404, detail="asset not found")
    if payload.asset_id and payload.asset_id != asset_id:
        raise HTTPException(400, detail="payload asset_id mismatch with path")

    iid = payload.id or str(uuid.uuid4())
    if db.query(DERInverter).filter(DERInverter.id == iid).first():
        raise HTTPException(409, detail="inverter id already exists")

    row = DERInverter(
        id=iid,
        asset_id=asset_id,
        manufacturer=payload.manufacturer,
        model=payload.model,
        serial_number=payload.serial_number,
        firmware_version=payload.firmware_version,
        rated_ac_kw=payload.rated_ac_kw,
        rated_dc_kw=payload.rated_dc_kw,
        num_mppt_trackers=payload.num_mppt_trackers,
        num_strings=payload.num_strings,
        phase_config=payload.phase_config,
        ac_voltage_nominal_v=payload.ac_voltage_nominal_v,
        comms_protocol=payload.comms_protocol,
        ip_address=payload.ip_address,
        installation_date=payload.installation_date,
        commissioned_at=payload.commissioned_at,
        warranty_expires=payload.warranty_expires,
        last_firmware_update=payload.last_firmware_update,
        status=payload.status or "online",
        inverter_metadata=payload.metadata,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=f"constraint violation: {exc.orig}") from exc
    db.refresh(row)
    return row


# ── Single-inverter equipment CRUD ───────────────────────────────────────────


@router.get(
    "/inverters/{inverter_id}",
    response_model=DERInverterOut,
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def get_inverter(
    inverter_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERInverter).filter(DERInverter.id == inverter_id).first()
    if not row:
        raise HTTPException(404, detail="inverter not found")
    return row


@router.patch(
    "/inverters/{inverter_id}",
    response_model=DERInverterOut,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def update_inverter(
    inverter_id: str,
    payload: DERInverterUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERInverter).filter(DERInverter.id == inverter_id).first()
    if not row:
        raise HTTPException(404, detail="inverter not found")
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        row.inverter_metadata = data.pop("metadata")
    for k, v in data.items():
        setattr(row, k, v)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=f"constraint violation: {exc.orig}") from exc
    db.refresh(row)
    return row


@router.delete(
    "/inverters/{inverter_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def delete_inverter(
    inverter_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERInverter).filter(DERInverter.id == inverter_id).first()
    if not row:
        raise HTTPException(404, detail="inverter not found")
    db.delete(row)
    db.commit()


# ── Per-inverter telemetry read ──────────────────────────────────────────────


@router.get(
    "/inverters/{inverter_id}/telemetry",
    response_model=List[DERInverterTelemetryOut],
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def get_inverter_telemetry(
    inverter_id: str,
    window: Literal["1h", "24h", "7d", "30d"] = Query("24h"),
    limit: int = Query(720, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(DERInverter).filter(DERInverter.id == inverter_id).first():
        raise HTTPException(404, detail="inverter not found")
    cutoff = datetime.now(timezone.utc) - _TELEMETRY_WINDOWS[window]
    return (
        db.query(DERInverterTelemetry)
        .filter(
            DERInverterTelemetry.inverter_id == inverter_id,
            DERInverterTelemetry.ts >= cutoff,
        )
        .order_by(DERInverterTelemetry.ts.desc())
        .limit(limit)
        .all()
    )
