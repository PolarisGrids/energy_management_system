"""Capability-based permission model for Polaris EMS.

Single source of truth for RBAC. Capabilities are dotted strings (e.g.
``meters.command``). Each role owns a set of capabilities. The JWT login
response embeds the user's capability list as a ``perm`` claim so
``require_permission`` can authorize without a DB round-trip.

Spec: 015-rbac-ui-lib
"""
from __future__ import annotations

from typing import Iterable, Set

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User, UserRole


# ── Capability catalogue ──────────────────────────────────────────────────
METERS_READ = "meters.read"
METERS_COMMAND = "meters.command"
ALARMS_ACK = "alarms.ack"
ALARMS_RESOLVE = "alarms.resolve"
DER_READ = "der.read"
DER_CONTROL = "der.control"
SIMULATION_RUN = "simulation.run"
SIMULATION_VIEW = "simulation.view"
AUDIT_READ = "audit.read"
REPORTS_GENERATE = "reports.generate"
HES_READ = "hes.read"
MDMS_READ = "mdms.read"
SENSORS_READ = "sensors.read"
SENSORS_CONFIGURE = "sensors.configure"
USERS_MANAGE = "users.manage"
SYSTEM_SETTINGS = "system.settings"
# Spec 016 — outage + notifications
OUTAGES_READ = "outages.read"
OUTAGES_MANAGE = "outages.manage"
NOTIFICATIONS_READ = "notifications.read"
NOTIFICATIONS_SEND = "notifications.send"
RELIABILITY_MANAGE = "reliability.manage"


_ADMIN_CAPS: Set[str] = {
    METERS_READ, METERS_COMMAND,
    ALARMS_ACK, ALARMS_RESOLVE,
    DER_READ, DER_CONTROL,
    SIMULATION_RUN, SIMULATION_VIEW,
    AUDIT_READ, REPORTS_GENERATE,
    HES_READ, MDMS_READ,
    SENSORS_READ, SENSORS_CONFIGURE,
    USERS_MANAGE, SYSTEM_SETTINGS,
    OUTAGES_READ, OUTAGES_MANAGE,
    NOTIFICATIONS_READ, NOTIFICATIONS_SEND,
    RELIABILITY_MANAGE,
}

_SUPERVISOR_CAPS: Set[str] = {
    METERS_READ, METERS_COMMAND,
    ALARMS_ACK, ALARMS_RESOLVE,
    DER_READ, DER_CONTROL,
    SIMULATION_RUN, SIMULATION_VIEW,
    AUDIT_READ, REPORTS_GENERATE,
    HES_READ, MDMS_READ,
    SENSORS_READ, SENSORS_CONFIGURE,
    OUTAGES_READ, OUTAGES_MANAGE,
    NOTIFICATIONS_READ,
}

_OPERATOR_CAPS: Set[str] = {
    METERS_READ,
    ALARMS_ACK,
    DER_READ,
    SIMULATION_VIEW,
    HES_READ, MDMS_READ,
    SENSORS_READ,
    REPORTS_GENERATE,
    OUTAGES_READ,
    NOTIFICATIONS_READ,
}


ROLE_CAPABILITIES: dict[UserRole, Set[str]] = {
    UserRole.ADMIN: _ADMIN_CAPS,
    UserRole.SUPERVISOR: _SUPERVISOR_CAPS,
    UserRole.OPERATOR: _OPERATOR_CAPS,
}


def capabilities_for(user: User | None) -> Set[str]:
    """Resolve the final capability set for a user.

    Union of the role-derived capability set and any per-user override
    stored in ``permissions_override`` (JSONB list). Returns ``set()`` for
    a missing or inactive user.
    """
    if user is None or not getattr(user, "is_active", False):
        return set()
    caps = set(ROLE_CAPABILITIES.get(user.role, set()))
    override = getattr(user, "permissions_override", None) or []
    if isinstance(override, list):
        caps.update(x for x in override if isinstance(x, str))
    return caps


def capabilities_from_payload(payload: dict | None) -> Set[str]:
    """Pull the capability list off a decoded JWT payload.

    Returns an empty set if no ``perm`` claim is present (older tokens
    issued before this feature will fall back to role lookup in the
    dependency below).
    """
    if not payload:
        return set()
    perm = payload.get("perm")
    if isinstance(perm, list):
        return {p for p in perm if isinstance(p, str)}
    return set()


def require_permission(*required: str):
    """FastAPI dependency gating an endpoint by capability.

    Checks the capability set encoded in the JWT ``perm`` claim first
    (stateless, no DB round-trip). If the claim is missing (legacy
    tokens), falls back to deriving caps from the user's role via
    :func:`capabilities_for`. Any missing required capability raises
    ``HTTPException(403)`` with a structured detail.
    """
    required_set: Set[str] = set(required)

    def checker(current_user: User = Depends(get_current_user)) -> User:
        claimed = getattr(current_user, "_jwt_perm", None)
        if isinstance(claimed, (list, set)):
            caps = set(claimed)
        elif claimed is None:
            caps = capabilities_for(current_user)
        else:
            caps = set()
        missing = required_set - caps
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "permission": sorted(missing)[0],
                    "missing": sorted(missing),
                },
            )
        return current_user

    return checker


def require_any(*required: str):
    """FastAPI dependency that passes if the user has ANY of the caps."""
    required_set: Set[str] = set(required)

    def checker(current_user: User = Depends(get_current_user)) -> User:
        claimed = getattr(current_user, "_jwt_perm", None)
        if isinstance(claimed, (list, set)):
            caps = set(claimed)
        else:
            caps = capabilities_for(current_user)
        if not (required_set & caps):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "permission": sorted(required_set)[0],
                    "missing": sorted(required_set),
                },
            )
        return current_user

    return checker


def roles_to_capabilities(roles: Iterable[UserRole]) -> Set[str]:
    caps: Set[str] = set()
    for r in roles:
        caps.update(ROLE_CAPABILITIES.get(r, set()))
    return caps
