"""Meter endpoints — spec 018 W2B refactor.

connect/disconnect (and the new batch variant) publish commands via the HES
routing-service instead of mutating `meter.relay_state` directly. A
`command_log` row is persisted as `status=QUEUED` and the `command_id` is
returned. The Kafka `hesv2.command.status` consumer (W2A) updates the row on
ACK/EXECUTED/CONFIRMED and — only on CONFIRMED — flips the meter's relay_state.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rbac import require_permission, P_METER_COMMAND
from app.db.base import get_db
from app.models.alarm import Alarm, AlarmStatus
from app.models.command_log import CommandLog
from app.models.meter import Feeder, Meter, MeterStatus, Transformer
from app.models.user import User
from app.schemas.command import (
    BatchCommandResult,
    BatchDisconnectRequest,
    BatchDisconnectResponse,
    CommandIssueResponse,
)
from app.schemas.meter import FeederOut, MeterListResponse, MeterOut, NetworkSummary, TransformerOut
from app.services.hes_client import CircuitBreakerError, hes_client

try:
    from otel_common.audit import audit  # type: ignore
except ImportError:  # pragma: no cover
    async def audit(**_kwargs):
        return None


logger = logging.getLogger(__name__)
router = APIRouter()


# ── Read endpoints (unchanged from pre-W2B) ──


@router.get("/", response_model=MeterListResponse)
def list_meters(
    skip: int = 0,
    limit: int = 100,
    status: Optional[MeterStatus] = None,
    transformer_id: Optional[int] = None,
    feeder_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Meter)
    if status:
        q = q.filter(Meter.status == status)
    if transformer_id:
        q = q.filter(Meter.transformer_id == transformer_id)
    if feeder_id:
        q = q.join(Transformer).filter(Transformer.feeder_id == feeder_id)
    total = q.count()
    meters = q.offset(skip).limit(limit).all()
    return MeterListResponse(total=total, meters=meters)


@router.get("/summary", response_model=NetworkSummary)
def network_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(Meter.id)).scalar()
    online = db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.ONLINE).scalar()
    offline = db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.OFFLINE).scalar()
    tamper = db.query(func.count(Meter.id)).filter(Meter.status == MeterStatus.TAMPER).scalar()
    disconnected = db.query(func.count(Meter.id)).filter(
        Meter.status == MeterStatus.DISCONNECTED
    ).scalar()
    feeders = db.query(func.count(Feeder.id)).scalar()
    transformers = db.query(func.count(Transformer.id)).scalar()
    active_alarms = db.query(func.count(Alarm.id)).filter(Alarm.status == AlarmStatus.ACTIVE).scalar()
    comm_rate = round((online / total * 100), 1) if total else 0.0
    return NetworkSummary(
        total_meters=total,
        online_meters=online,
        offline_meters=offline,
        tamper_meters=tamper,
        disconnected_meters=disconnected,
        comm_success_rate=comm_rate,
        total_feeders=feeders,
        total_transformers=transformers,
        active_alarms=active_alarms,
    )


@router.get("/{serial}", response_model=MeterOut)
def get_meter(serial: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    meter = db.query(Meter).filter(Meter.serial == serial).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


# ── Command endpoints (W2.T8 / W2.T9) ──


async def _issue_command(
    *,
    db: Session,
    meter_serial: str,
    command_type: str,
    payload: dict | None,
    issuer_user_id: Optional[str],
) -> tuple[CommandLog, Optional[str]]:
    """Persist a QUEUED command_log row and publish to HES routing.

    Returns (log_row, error_detail). On HES success the row stays QUEUED
    (Kafka consumer will drive it forward). On transport failure the row is
    updated to FAILED and the error is returned so the endpoint can report it.
    """
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled (HES_ENABLED=false)",
        )

    command_id = str(uuid.uuid4())
    log = CommandLog(
        id=command_id,
        meter_serial=meter_serial,
        command_type=command_type,
        payload=payload or {},
        status="QUEUED",
        issued_at=datetime.now(timezone.utc),
        issuer_user_id=issuer_user_id,
        trace_id=current_trace_id(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        resp = await hes_client.post_command(
            type_=command_type,
            meter_serial=meter_serial,
            payload={**(payload or {}), "command_id": command_id},
        )
        # HES may echo its own id; we keep ours as canonical.
        body = resp.json() if hasattr(resp, "json") else {}
        log.response_payload = body
        db.commit()
        return log, None
    except CircuitBreakerError as exc:
        log.status = "FAILED"
        log.response_payload = {"error": "circuit_open", "detail": str(exc)}
        db.commit()
        return log, f"HES circuit open: {exc}"
    except Exception as exc:  # pragma: no cover — defensive
        log.status = "FAILED"
        log.response_payload = {"error": "transport", "detail": str(exc)[:500]}
        db.commit()
        return log, f"HES transport failure: {exc}"


# ── Batch disconnect (W2.T9) — registered before /{serial}/... so FastAPI
#    matches the literal "batch" segment first instead of treating it as a
#    meter serial.


@router.post(
    "/batch/disconnect",
    response_model=BatchDisconnectResponse,
    dependencies=[Depends(require_permission(P_METER_COMMAND))],
)
async def batch_disconnect(
    payload: BatchDisconnectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Concurrently issue DISCONNECT commands (bounded by semaphore)."""
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled (HES_ENABLED=false)",
        )

    serials = payload.meter_serials
    existing = {
        m.serial
        for m in db.query(Meter.serial).filter(Meter.serial.in_(serials)).all()
    }
    sem = asyncio.Semaphore(10)

    async def _one(serial: str) -> BatchCommandResult:
        if serial not in existing:
            return BatchCommandResult(meter_serial=serial, status="FAILED", error="meter_not_found")
        async with sem:
            log, err = await _issue_command(
                db=db,
                meter_serial=serial,
                command_type="DISCONNECT",
                payload={"action": "disconnect", "reason": payload.reason},
                issuer_user_id=str(current_user.id),
            )
            return BatchCommandResult(
                meter_serial=serial,
                command_id=log.id,
                status=log.status,
                error=err,
            )

    results = await asyncio.gather(*(_one(s) for s in serials))
    queued = sum(1 for r in results if r.status == "QUEUED")
    failed = len(results) - queued
    await audit(
        action_type="WRITE",
        action_name="meter_batch_disconnect",
        entity_type="Meter",
        entity_id=f"batch:{len(serials)}",
        request_data={"meter_count": len(serials), "reason": payload.reason},
        status=200,
        method="POST",
        path="/api/v1/meters/batch/disconnect",
        user_id=str(current_user.id),
    )
    return BatchDisconnectResponse(
        total=len(results),
        queued=queued,
        failed=failed,
        results=results,
    )


@router.post(
    "/{serial}/connect",
    response_model=CommandIssueResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(P_METER_COMMAND))],
)
async def remote_connect(
    serial: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a CONNECT command via HES. Relay state updates on CONFIRMED."""
    meter = db.query(Meter).filter(Meter.serial == serial).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")

    log, err = await _issue_command(
        db=db,
        meter_serial=serial,
        command_type="CONNECT",
        payload={"action": "connect"},
        issuer_user_id=str(current_user.id),
    )
    await audit(
        action_type="WRITE",
        action_name="meter_connect",
        entity_type="Meter",
        entity_id=str(meter.id),
        request_data={"serial": serial, "command_id": log.id},
        status=202 if err is None else 503,
        method="POST",
        path=f"/api/v1/meters/{serial}/connect",
        user_id=str(current_user.id),
    )
    if err:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"command_id": log.id, "error": err},
        )
    return CommandIssueResponse(
        command_id=log.id,
        meter_serial=serial,
        command_type="CONNECT",
        status=log.status,
        issued_at=log.issued_at,
    )


@router.post(
    "/{serial}/disconnect",
    response_model=CommandIssueResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(P_METER_COMMAND))],
)
async def remote_disconnect(
    serial: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a DISCONNECT command via HES. Relay state updates on CONFIRMED."""
    meter = db.query(Meter).filter(Meter.serial == serial).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")

    log, err = await _issue_command(
        db=db,
        meter_serial=serial,
        command_type="DISCONNECT",
        payload={"action": "disconnect"},
        issuer_user_id=str(current_user.id),
    )
    await audit(
        action_type="WRITE",
        action_name="meter_disconnect",
        entity_type="Meter",
        entity_id=str(meter.id),
        request_data={"serial": serial, "command_id": log.id},
        status=202 if err is None else 503,
        method="POST",
        path=f"/api/v1/meters/{serial}/disconnect",
        user_id=str(current_user.id),
    )
    if err:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"command_id": log.id, "error": err},
        )
    return CommandIssueResponse(
        command_id=log.id,
        meter_serial=serial,
        command_type="DISCONNECT",
        status=log.status,
        issued_at=log.issued_at,
    )


# ── Hierarchy helpers ──


@router.get("/transformers/list", response_model=List[TransformerOut])
def list_transformers(
    feeder_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Transformer)
    if feeder_id:
        q = q.filter(Transformer.feeder_id == feeder_id)
    return q.all()


@router.get("/feeders/list", response_model=List[FeederOut])
def list_feeders(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Feeder).all()
