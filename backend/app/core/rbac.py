"""Role-based access control — spec 018 W4.T13.

Maps the five project roles (admin / supervisor / operator / analyst / viewer)
to a flat set of permission strings. Endpoints declare a required permission
via the `require_permission("perm")` FastAPI dependency. The dependency reads
the authenticated user (via the existing `get_current_user` dep), resolves
their role → permissions, merges any explicit grants from the JWT claim
`permissions`, and raises HTTP 403 if the user lacks the permission.

The role matrix is kept deliberately explicit rather than wildcard-driven, so
reviewers can audit exactly what each role can do.
"""
from __future__ import annotations

from typing import Iterable, Set

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User, UserRole


# ── Permission catalogue ────────────────────────────────────────────────────
# Keep the strings stable; they're baked into tests and may surface in audit
# logs. When adding a new permission, also add it to ROLE_PERMISSIONS below.

# Read permissions
P_DASHBOARD_READ = "dashboard.read"
P_ALARM_READ = "alarm.read"
P_METER_READ = "meter.read"
P_DER_READ = "der.read"
P_SENSOR_READ = "sensor.read"
P_HES_READ = "hes.read"
P_MDMS_READ = "mdms.read"
P_OUTAGE_READ = "outage.read"
P_SIMULATION_READ = "simulation.read"
P_ENERGY_READ = "energy.read"
P_REPORT_READ = "report.read"
P_ENERGY_AUDIT_READ = "energy_audit.read"
P_RELIABILITY_READ = "reliability.read"
P_NTL_READ = "ntl.read"
P_APP_BUILDER_READ = "app_builder.read"
P_AUDIT_READ = "audit.read"
P_DATA_ACCURACY_READ = "data_accuracy.read"
P_DASHBOARD_LAYOUT_READ = "dashboard_layout.read"

# Write / admin permissions
P_METER_COMMAND = "meter.command"      # connect / disconnect / batch disconnect
P_DER_COMMAND = "der.command"          # inverter / BESS / EV commands
P_FOTA_MANAGE = "fota.manage"          # create / rollback / poll FOTA jobs
P_OUTAGE_FLISR = "outage.flisr"        # isolate / restore switching
P_OUTAGE_MANAGE = "outage.manage"      # acknowledge / dispatch / note
P_ALARM_MANAGE = "alarm.manage"        # acknowledge / resolve
P_ALARM_CONFIGURE = "alarm.configure"  # create / edit alarm_rule, groups
P_APP_BUILDER_PUBLISH = "app_builder.publish"
P_REPORT_SCHEDULE = "report.schedule"
P_DASHBOARD_ADMIN = "dashboard.admin"  # edit any dashboard, not just own
P_DATA_ACCURACY_RECONCILE = "data_accuracy.reconcile"
P_SENSOR_MANAGE = "sensor.manage"      # threshold changes
P_SIMULATION_MANAGE = "simulation.manage"  # start / next-step / reset
P_ADMIN_ALL = "admin.all"              # super-user fallback


# Flat read set (every role-read permission listed above)
_READ_PERMS: Set[str] = {
    P_DASHBOARD_READ, P_ALARM_READ, P_METER_READ, P_DER_READ, P_SENSOR_READ,
    P_HES_READ, P_MDMS_READ, P_OUTAGE_READ, P_SIMULATION_READ, P_ENERGY_READ,
    P_REPORT_READ, P_ENERGY_AUDIT_READ, P_RELIABILITY_READ, P_NTL_READ,
    P_APP_BUILDER_READ, P_AUDIT_READ, P_DATA_ACCURACY_READ,
    P_DASHBOARD_LAYOUT_READ,
}


# ── Role → Permission matrix ────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, Set[str]] = {
    # Admin: everything.
    "admin": _READ_PERMS | {
        P_METER_COMMAND, P_DER_COMMAND, P_FOTA_MANAGE, P_OUTAGE_FLISR,
        P_OUTAGE_MANAGE, P_ALARM_MANAGE, P_ALARM_CONFIGURE,
        P_APP_BUILDER_PUBLISH, P_REPORT_SCHEDULE, P_DASHBOARD_ADMIN,
        P_DATA_ACCURACY_RECONCILE, P_SENSOR_MANAGE, P_SIMULATION_MANAGE,
        P_ADMIN_ALL,
    },
    # Supervisor: everything except admin.all (no system admin ops).
    "supervisor": _READ_PERMS | {
        P_METER_COMMAND, P_DER_COMMAND, P_FOTA_MANAGE, P_OUTAGE_FLISR,
        P_OUTAGE_MANAGE, P_ALARM_MANAGE, P_ALARM_CONFIGURE,
        P_APP_BUILDER_PUBLISH, P_REPORT_SCHEDULE, P_DASHBOARD_ADMIN,
        P_DATA_ACCURACY_RECONCILE, P_SENSOR_MANAGE, P_SIMULATION_MANAGE,
    },
    # Operator: operational screens + commands, but no publish / schedule.
    "operator": {
        P_DASHBOARD_READ, P_ALARM_READ, P_METER_READ, P_DER_READ,
        P_SENSOR_READ, P_HES_READ, P_OUTAGE_READ, P_SIMULATION_READ,
        P_APP_BUILDER_READ, P_DASHBOARD_LAYOUT_READ, P_DATA_ACCURACY_READ,
        P_METER_COMMAND, P_DER_COMMAND, P_OUTAGE_FLISR, P_OUTAGE_MANAGE,
        P_ALARM_MANAGE, P_SIMULATION_MANAGE, P_SENSOR_MANAGE,
        P_DATA_ACCURACY_RECONCILE,
    },
    # Analyst: reports / MDMS / NTL / energy; read AppBuilder & audit.
    "analyst": {
        P_DASHBOARD_READ, P_ENERGY_READ, P_REPORT_READ, P_MDMS_READ,
        P_ENERGY_AUDIT_READ, P_RELIABILITY_READ,
        P_NTL_READ, P_APP_BUILDER_READ, P_AUDIT_READ,
        P_DASHBOARD_LAYOUT_READ, P_DATA_ACCURACY_READ,
        P_REPORT_SCHEDULE,
    },
    # Viewer: read-only dashboards, alarms list, reports list.
    "viewer": {
        P_DASHBOARD_READ, P_ALARM_READ, P_REPORT_READ,
        P_ENERGY_AUDIT_READ, P_RELIABILITY_READ,
        P_DASHBOARD_LAYOUT_READ,
    },
}


def _role_key(role) -> str:
    """Normalise a UserRole enum / raw string into the matrix key."""
    if role is None:
        return ""
    if isinstance(role, UserRole):
        return role.value
    return str(role).lower()


def get_permissions(user: User, extra_claims: Iterable[str] | None = None) -> Set[str]:
    """Resolve the effective permission set for a user.

    Combines role-derived permissions with any explicit grants from JWT
    claims (for ad-hoc scope upgrades without changing the role).
    """
    role = _role_key(user.role)
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    if extra_claims:
        perms.update(str(c) for c in extra_claims)
    return perms


def has_permission(user: User, permission: str) -> bool:
    perms = get_permissions(user)
    return permission in perms or P_ADMIN_ALL in perms


def require_permission(permission: str):
    """FastAPI dependency factory — raise 403 unless user has permission.

    Usage:

        @router.post("/x", dependencies=[Depends(require_permission("meter.command"))])
        async def x(...): ...

    For endpoints that already take `current_user` via
    `Depends(get_current_user)`, prefer adding this as a `dependencies=[...]`
    entry so the existing current_user dep stays wired for audit logging.
    """

    def dep(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return current_user

    return dep


def require_any_permission(*permissions: str):
    """FastAPI dependency — pass if the user has ANY of the listed permissions.

    Used for endpoints that accept multiple valid grants (e.g. dashboard
    own-write OR dashboard.admin).
    """

    def dep(current_user: User = Depends(get_current_user)) -> User:
        user_perms = get_permissions(current_user)
        if P_ADMIN_ALL in user_perms:
            return current_user
        if not any(p in user_perms for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing one of required permissions: {', '.join(permissions)}",
            )
        return current_user

    return dep


__all__ = [
    "ROLE_PERMISSIONS",
    "get_permissions",
    "has_permission",
    "require_permission",
    "require_any_permission",
    # Permission string constants
    "P_DASHBOARD_READ", "P_ALARM_READ", "P_METER_READ", "P_DER_READ",
    "P_SENSOR_READ", "P_HES_READ", "P_MDMS_READ", "P_OUTAGE_READ",
    "P_SIMULATION_READ", "P_ENERGY_READ", "P_REPORT_READ",
    "P_ENERGY_AUDIT_READ", "P_RELIABILITY_READ", "P_NTL_READ",
    "P_APP_BUILDER_READ", "P_AUDIT_READ", "P_DATA_ACCURACY_READ",
    "P_DASHBOARD_LAYOUT_READ", "P_METER_COMMAND", "P_DER_COMMAND",
    "P_FOTA_MANAGE", "P_OUTAGE_FLISR", "P_OUTAGE_MANAGE", "P_ALARM_MANAGE",
    "P_ALARM_CONFIGURE", "P_APP_BUILDER_PUBLISH", "P_REPORT_SCHEDULE",
    "P_DASHBOARD_ADMIN", "P_DATA_ACCURACY_RECONCILE", "P_SENSOR_MANAGE",
    "P_SIMULATION_MANAGE", "P_ADMIN_ALL",
]
