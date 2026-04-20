"""Unit tests for spec 018 W4.T13 — RBAC dependency + role matrix.

Tests the 5-role × 10-endpoint matrix called out in the Wave 4 task entry.
Uses the existing `client` fixture (in-memory SQLite) and swaps
`get_current_user` per test to a User with the desired role.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
from app.core.deps import get_current_user
from app.db.base import Base
from app.core.rbac import (
    P_ADMIN_ALL,
    P_ALARM_MANAGE,
    P_DASHBOARD_READ,
    P_DER_COMMAND,
    P_METER_COMMAND,
    ROLE_PERMISSIONS,
    get_permissions,
    has_permission,
    require_permission,
)
from app.main import app
from app.models.user import User, UserRole


ROLES = ["admin", "supervisor", "operator", "analyst", "viewer"]


def _user(role: str) -> User:
    return User(
        id=hash(role) % 100000,
        username=role,
        email=f"{role}@example.com",
        full_name=role.title(),
        hashed_password="x",
        role=UserRole(role),
        is_active=True,
    )


# ── Pure-function tests ─────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix_has_entry(role):
    assert role in ROLE_PERMISSIONS
    assert isinstance(ROLE_PERMISSIONS[role], set)
    # Every role can at least see the dashboard.
    assert P_DASHBOARD_READ in ROLE_PERMISSIONS[role]


def test_admin_has_admin_all_fallback():
    assert P_ADMIN_ALL in ROLE_PERMISSIONS["admin"]


def test_supervisor_has_no_admin_all():
    assert P_ADMIN_ALL not in ROLE_PERMISSIONS["supervisor"]


def test_viewer_is_read_only():
    # Viewer must have NO mutating permissions.
    perms = ROLE_PERMISSIONS["viewer"]
    mutating = {
        "meter.command", "der.command", "fota.manage", "outage.flisr",
        "outage.manage", "alarm.manage", "alarm.configure",
        "app_builder.publish", "report.schedule", "dashboard.admin",
        "data_accuracy.reconcile", "sensor.manage", "simulation.manage",
    }
    assert perms.isdisjoint(mutating)


def test_operator_can_command_meters():
    u = _user("operator")
    assert has_permission(u, P_METER_COMMAND)
    assert has_permission(u, P_DER_COMMAND)


def test_analyst_cannot_command_meters():
    u = _user("analyst")
    assert not has_permission(u, P_METER_COMMAND)
    assert not has_permission(u, P_DER_COMMAND)


def test_admin_all_is_superuser():
    u = _user("admin")
    # Even a permission that's not enumerated passes because admin.all is set.
    assert has_permission(u, "some.future.permission")


def test_get_permissions_merges_extra_claims():
    u = _user("viewer")
    perms = get_permissions(u, extra_claims=["custom.grant"])
    assert "custom.grant" in perms


# ── FastAPI dependency integration ─────────────────────────────────────────


@pytest.fixture
def SessionLocal():
    """In-memory SQLite session factory for the test app."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Register all models on Base.metadata via the package import.
    import app.models  # noqa: F401

    Base.metadata.create_all(eng)
    yield sessionmaker(autocommit=False, autoflush=False, bind=eng)
    eng.dispose()


@pytest.fixture
def override_user():
    """Lets each test swap the authenticated user in the TestClient."""
    ref = {"user": None}

    def _set(u: User):
        ref["user"] = u
        app.dependency_overrides[get_current_user] = lambda: ref["user"]

    yield _set
    app.dependency_overrides.pop(get_current_user, None)


# ── 5-role × representative endpoint matrix ───────────────────────────────
#
# Each row: (method, path, required_permission_name). We assert the expected
# HTTP status per role. We stub the DB dependency so routes don't 500 before
# the permission dep runs.


ENDPOINT_MATRIX = [
    # Mutating endpoints gated by require_permission:
    ("POST", "/api/v1/meters/batch/disconnect", "meter.command", {"meter_serials": ["M0001"], "reason": "test"}),
    ("POST", "/api/v1/meters/M0001/connect", "meter.command", None),
    ("POST", "/api/v1/meters/M0001/disconnect", "meter.command", None),
    ("POST", "/api/v1/der/ASSET-1/command", "der.command", {
        "command_type": "DER_CURTAIL", "setpoint": 0.5, "trace_id": None,
    }),
    ("POST", "/api/v1/fota/jobs/JOB-1/poll", "fota.manage", None),
    ("POST", "/api/v1/outages/inc-1/acknowledge", "outage.manage", {"note": "ack"}),
    ("POST", "/api/v1/outages/inc-1/flisr/isolate", "outage.flisr", {
        "switch_id": "SW1", "reason": "test"
    }),
    ("POST", "/api/v1/alarms/1/acknowledge", "alarm.manage", {"acknowledged_by": "tester"}),
    ("POST", "/api/v1/sensors/1/threshold", "sensor.manage", {
        "threshold_warning": 10.0, "threshold_critical": 20.0
    }),
    ("POST", "/api/v1/simulation/1/reset", "simulation.manage", None),
]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("method,path,perm,body", ENDPOINT_MATRIX)
def test_rbac_endpoint_matrix(override_user, SessionLocal, role, method, path, perm, body):
    """For each (role, endpoint), the first gate hit should be RBAC.

    • If the role has the permission → we expect anything EXCEPT 403
      (the route may still 404/409/503 because DB rows don't exist, which
      is fine — that proves we got past the auth dependency).
    • If the role lacks the permission → we expect exactly 403.
    """
    override_user(_user(role))

    def _get_db_override():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_base.get_db] = _get_db_override
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.request(method, path, json=body)
    finally:
        app.dependency_overrides.pop(db_base.get_db, None)

    expected_allowed = perm in ROLE_PERMISSIONS[role] or "admin.all" in ROLE_PERMISSIONS[role]

    if expected_allowed:
        assert resp.status_code != 403, (
            f"{role} should have {perm}; got 403 on {method} {path}"
        )
    else:
        assert resp.status_code == 403, (
            f"{role} lacks {perm}; expected 403 but got {resp.status_code} on "
            f"{method} {path} — body={resp.text[:200]}"
        )


# ── Direct dependency tests ─────────────────────────────────────────────────


def test_require_permission_raises_403_without_perm():
    dep = require_permission("does.not.exist.for.viewer")
    u = _user("viewer")
    with pytest.raises(Exception) as exc:  # HTTPException
        dep(u)
    assert getattr(exc.value, "status_code", None) == 403


def test_require_permission_allows_admin():
    dep = require_permission("anything")
    u = _user("admin")
    # Should not raise — admin.all short-circuits.
    assert dep(u) is u


def test_require_permission_allows_matching_role():
    dep = require_permission(P_ALARM_MANAGE)
    u = _user("operator")
    assert dep(u) is u
