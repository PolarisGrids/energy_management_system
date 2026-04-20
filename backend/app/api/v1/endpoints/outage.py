"""Outage endpoints — spec 018 W3.T4 + W3.T17.

    GET    /api/v1/outages                       — list (filter status/date)
    GET    /api/v1/outages/{id}                  — detail + timeline
    POST   /api/v1/outages/{id}/acknowledge
    POST   /api/v1/outages/{id}/dispatch-crew    — feature-flag WFM_ENABLED
    POST   /api/v1/outages/{id}/note
    POST   /api/v1/outages/{id}/flisr/isolate    — feature-flag SMART_INVERTER_COMMANDS_ENABLED
    POST   /api/v1/outages/{id}/flisr/restore    — feature-flag SMART_INVERTER_COMMANDS_ENABLED

All writes emit an audit event via :mod:`app.services.audit_publisher`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rbac import (
    require_permission,
    P_OUTAGE_FLISR,
    P_OUTAGE_MANAGE,
)
from app.db.base import get_db
from app.models.outage import (
    OutageFlisrAction,
    OutageIncidentW3,
    OutageTimelineEvent,
)
from app.models.user import User
from app.schemas.outage_w3 import (
    OutageAcknowledgeIn,
    OutageDispatchCrewIn,
    OutageFlisrActionIn,
    OutageFlisrActionOut,
    OutageIncidentW3Detail,
    OutageIncidentW3Out,
    OutageListResponse,
    OutageNoteIn,
    OutageTimelineEventOut,
)
from app.services.audit_publisher import publish_audit
from app.services.hes_client import CircuitBreakerError, hes_client
from app.services.mdms_client import mdms_client

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_incident_or_404(db: Session, incident_id: str) -> OutageIncidentW3:
    inc = db.query(OutageIncidentW3).filter(OutageIncidentW3.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="outage incident not found")
    return inc


def _append_timeline(
    db: Session,
    incident: OutageIncidentW3,
    event_type: str,
    details: Optional[dict],
    actor_user_id: Optional[str],
) -> OutageTimelineEvent:
    now = datetime.now(timezone.utc)
    row = OutageTimelineEvent(
        incident_id=incident.id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        details=details,
        trace_id=current_trace_id() or incident.trigger_trace_id,
        at=now,
    )
    db.add(row)
    tl = list(incident.timeline or [])
    tl.append(
        {
            "event_type": event_type,
            "details": details,
            "actor_user_id": actor_user_id,
            "at": now.isoformat(),
        }
    )
    incident.timeline = tl
    incident.updated_at = now
    return row


# ── Reads ───────────────────────────────────────────────────────────────────


@router.get("", response_model=OutageListResponse)
@router.get("/", response_model=OutageListResponse)
def list_outages(
    status: Optional[str] = Query(None, description="DETECTED/INVESTIGATING/DISPATCHED/RESTORED"),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> OutageListResponse:
    q = db.query(OutageIncidentW3)
    if status:
        q = q.filter(OutageIncidentW3.status == status.upper())
    if from_date:
        q = q.filter(OutageIncidentW3.opened_at >= from_date)
    if to_date:
        q = q.filter(OutageIncidentW3.opened_at <= to_date)
    total = q.count()
    rows = q.order_by(desc(OutageIncidentW3.opened_at)).offset(offset).limit(limit).all()
    return OutageListResponse(
        total=total,
        incidents=[OutageIncidentW3Out.model_validate(r) for r in rows],
    )


@router.get("/{incident_id}", response_model=OutageIncidentW3Detail)
def get_outage(
    incident_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> OutageIncidentW3Detail:
    inc = _get_incident_or_404(db, incident_id)
    events = (
        db.query(OutageTimelineEvent)
        .filter(OutageTimelineEvent.incident_id == incident_id)
        .order_by(OutageTimelineEvent.at.asc())
        .all()
    )
    return OutageIncidentW3Detail(
        **OutageIncidentW3Out.model_validate(inc).model_dump(),
        timeline=[OutageTimelineEventOut.model_validate(e) for e in events],
    )


# ── Writes ──────────────────────────────────────────────────────────────────


@router.post(
    "/{incident_id}/acknowledge",
    response_model=OutageIncidentW3Out,
    dependencies=[Depends(require_permission(P_OUTAGE_MANAGE))],
)
async def acknowledge_outage(
    incident_id: str,
    payload: OutageAcknowledgeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutageIncidentW3Out:
    inc = _get_incident_or_404(db, incident_id)
    if inc.status in ("RESTORED", "CLOSED"):
        raise HTTPException(status_code=409, detail="incident already closed")
    _append_timeline(
        db,
        inc,
        "acknowledged",
        {"note": payload.note},
        actor_user_id=str(current_user.id),
    )
    # Status stays DETECTED/INVESTIGATING — acknowledge is a soft action.
    db.commit()
    db.refresh(inc)
    await publish_audit(
        action_type="WRITE",
        action_name="acknowledge_outage",
        entity_type="OutageIncident",
        entity_id=incident_id,
        method="POST",
        path=f"/api/v1/outages/{incident_id}/acknowledge",
        response_status=200,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
    )
    return OutageIncidentW3Out.model_validate(inc)


@router.post(
    "/{incident_id}/note",
    response_model=OutageIncidentW3Out,
    dependencies=[Depends(require_permission(P_OUTAGE_MANAGE))],
)
async def add_outage_note(
    incident_id: str,
    payload: OutageNoteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutageIncidentW3Out:
    inc = _get_incident_or_404(db, incident_id)
    _append_timeline(
        db,
        inc,
        "note",
        {"note": payload.note},
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(inc)
    await publish_audit(
        action_type="WRITE",
        action_name="add_outage_note",
        entity_type="OutageIncident",
        entity_id=incident_id,
        method="POST",
        path=f"/api/v1/outages/{incident_id}/note",
        response_status=200,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
    )
    return OutageIncidentW3Out.model_validate(inc)


@router.post(
    "/{incident_id}/dispatch-crew",
    response_model=OutageIncidentW3Out,
    dependencies=[Depends(require_permission(P_OUTAGE_MANAGE))],
)
async def dispatch_outage_crew(
    incident_id: str,
    payload: OutageDispatchCrewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutageIncidentW3Out:
    if not settings.WFM_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WFM not configured",
        )
    inc = _get_incident_or_404(db, incident_id)
    if inc.status in ("RESTORED", "CLOSED"):
        raise HTTPException(status_code=409, detail="incident already closed")

    wfm_payload = {
        "incident_id": incident_id,
        "crew_id": payload.crew_id,
        "eta_minutes": payload.eta_minutes,
        "note": payload.note,
        "affected_dtr_ids": inc.affected_dtr_ids,
        "affected_meter_count": inc.affected_meter_count,
        "trace_id": current_trace_id(),
    }
    work_order_id: Optional[str] = None
    err: Optional[str] = None
    try:
        resp = await mdms_client.create_wfm_work_order(wfm_payload)
        body = resp.json() if hasattr(resp, "json") else {}
        work_order_id = body.get("work_order_id") or body.get("id")
    except CircuitBreakerError as exc:
        err = f"MDMS WFM circuit open: {exc}"
    except Exception as exc:
        err = f"MDMS WFM transport failure: {exc}"

    _append_timeline(
        db,
        inc,
        "crew_dispatched",
        {
            "crew_id": payload.crew_id,
            "eta_minutes": payload.eta_minutes,
            "note": payload.note,
            "work_order_id": work_order_id,
            "error": err,
        },
        actor_user_id=str(current_user.id),
    )
    if err is None:
        inc.status = "DISPATCHED"
    db.commit()
    db.refresh(inc)

    await publish_audit(
        action_type="WRITE",
        action_name="dispatch_outage_crew",
        entity_type="OutageIncident",
        entity_id=incident_id,
        method="POST",
        path=f"/api/v1/outages/{incident_id}/dispatch-crew",
        response_status=200 if err is None else 503,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
        response_data={"work_order_id": work_order_id, "error": err},
    )

    if err is not None:
        raise HTTPException(status_code=503, detail=err)
    return OutageIncidentW3Out.model_validate(inc)


# ── FLISR actions (W3.T17) ──────────────────────────────────────────────────


async def _flisr_send(
    db: Session,
    incident: OutageIncidentW3,
    action: str,  # isolate | restore
    payload: OutageFlisrActionIn,
    current_user: User,
) -> OutageFlisrActionOut:
    if not getattr(settings, "SMART_INVERTER_COMMANDS_ENABLED", False):
        # Spec gate — re-use the networked-switch simulation flag.
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FLISR network switching not enabled",
        )
    if not settings.HES_ENABLED:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HES integration disabled",
        )

    action_id = str(uuid.uuid4())
    hes_cmd_type = "switch_open" if action == "isolate" else "switch_close"
    target = payload.target_switch_id or (
        (incident.affected_dtr_ids or [None])[0]
    )
    if not target:
        raise HTTPException(
            status_code=400, detail="target_switch_id required (no DTR on incident)"
        )

    row = OutageFlisrAction(
        id=action_id,
        incident_id=incident.id,
        action=action,
        target_switch_id=target,
        status="QUEUED",
        issuer_user_id=str(current_user.id),
        trace_id=current_trace_id(),
    )
    db.add(row)
    db.flush()

    hes_payload = {
        "action": action,
        "target_switch_id": target,
        "incident_id": incident.id,
        "command_id": action_id,
    }
    err: Optional[str] = None
    hes_cmd_id: Optional[str] = None
    try:
        resp = await hes_client.post_command(
            type_=hes_cmd_type,
            meter_serial=target,
            payload=hes_payload,
        )
        body = resp.json() if hasattr(resp, "json") else {}
        row.response_payload = body
        hes_cmd_id = body.get("command_id") or action_id
        row.hes_command_id = hes_cmd_id
        row.status = "ACCEPTED"
    except CircuitBreakerError as exc:
        err = f"HES circuit open: {exc}"
        row.status = "FAILED"
        row.response_payload = {"error": "circuit_open"}
    except Exception as exc:
        err = f"HES transport failure: {exc}"
        row.status = "FAILED"
        row.response_payload = {"error": "transport", "detail": str(exc)[:500]}

    _append_timeline(
        db,
        incident,
        f"flisr_{action}",
        {
            "action_id": action_id,
            "target_switch_id": target,
            "hes_command_id": hes_cmd_id,
            "note": payload.note,
            "error": err,
        },
        actor_user_id=str(current_user.id),
    )
    db.commit()
    db.refresh(row)

    await publish_audit(
        action_type="WRITE",
        action_name=f"flisr_{action}",
        entity_type="OutageIncident",
        entity_id=incident.id,
        method="POST",
        path=f"/api/v1/outages/{incident.id}/flisr/{action}",
        response_status=200 if err is None else 503,
        user_id=str(current_user.id),
        request_data=payload.model_dump(),
        response_data={"action_id": action_id, "hes_command_id": hes_cmd_id, "error": err},
    )

    if err is not None:
        raise HTTPException(status_code=503, detail=err)
    return OutageFlisrActionOut.model_validate(row)


@router.post(
    "/{incident_id}/flisr/isolate",
    response_model=OutageFlisrActionOut,
    dependencies=[Depends(require_permission(P_OUTAGE_FLISR))],
)
async def flisr_isolate(
    incident_id: str,
    payload: OutageFlisrActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutageFlisrActionOut:
    inc = _get_incident_or_404(db, incident_id)
    return await _flisr_send(db, inc, "isolate", payload, current_user)


@router.post(
    "/{incident_id}/flisr/restore",
    response_model=OutageFlisrActionOut,
    dependencies=[Depends(require_permission(P_OUTAGE_FLISR))],
)
async def flisr_restore(
    incident_id: str,
    payload: OutageFlisrActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutageFlisrActionOut:
    inc = _get_incident_or_404(db, incident_id)
    return await _flisr_send(db, inc, "restore", payload, current_user)
