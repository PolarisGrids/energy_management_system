"""Outage incident state machine — spec 016 US2.

Legal transitions (see spec §User Story 2):
    DETECTED   -> CONFIRMED | CANCELLED
    CONFIRMED  -> DISPATCHED | CANCELLED
    DISPATCHED -> RESTORING | CANCELLED
    RESTORING  -> RESTORED
    RESTORED   -> CLOSED
    CLOSED     -> (terminal)
    CANCELLED  -> (terminal)

Illegal transitions raise InvalidTransition (→ HTTP 400).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Set

from app.models.outage import OutageIncident, OutageStatus


class InvalidTransition(Exception):
    """Raised when a caller attempts an illegal outage lifecycle transition."""


ALLOWED: Dict[OutageStatus, Set[OutageStatus]] = {
    OutageStatus.DETECTED: {OutageStatus.CONFIRMED, OutageStatus.CANCELLED},
    OutageStatus.CONFIRMED: {OutageStatus.DISPATCHED, OutageStatus.CANCELLED},
    OutageStatus.DISPATCHED: {OutageStatus.RESTORING, OutageStatus.CANCELLED},
    OutageStatus.RESTORING: {OutageStatus.RESTORED},
    OutageStatus.RESTORED: {OutageStatus.CLOSED},
    OutageStatus.CLOSED: set(),
    OutageStatus.CANCELLED: set(),
}


# Column name on OutageIncident to stamp when the target state is entered.
_TIMESTAMP_COL: Dict[OutageStatus, str] = {
    OutageStatus.CONFIRMED: "confirmed_at",
    OutageStatus.DISPATCHED: "dispatched_at",
    OutageStatus.RESTORED: "restored_at",
    OutageStatus.CLOSED: "closed_at",
}


def can_transition(current: OutageStatus, target: OutageStatus) -> bool:
    return target in ALLOWED.get(current, set())


def transition(
    incident: OutageIncident,
    new_status: OutageStatus,
    actor: str | None = None,
) -> OutageIncident:
    """Validate + apply a lifecycle transition in-place.

    Sets the appropriate timestamp column on the incident. The caller is
    responsible for committing the SQLAlchemy session and emitting SSE /
    audit events (see `services.outage_service`).
    """
    current = (
        OutageStatus(incident.status)
        if not isinstance(incident.status, OutageStatus)
        else incident.status
    )
    if not can_transition(current, new_status):
        raise InvalidTransition(
            f"cannot move outage {incident.id} from {current.value} to {new_status.value}"
        )
    incident.status = new_status.value if hasattr(new_status, "value") else new_status
    stamp = _TIMESTAMP_COL.get(new_status)
    if stamp and getattr(incident, stamp) is None:
        setattr(incident, stamp, datetime.now(timezone.utc))
    if new_status == OutageStatus.CANCELLED and incident.closed_at is None:
        incident.closed_at = datetime.now(timezone.utc)
    # `actor` is captured by the caller into the audit log / notes — we don't
    # stamp it on the row because the incident already has created_by.
    return incident
