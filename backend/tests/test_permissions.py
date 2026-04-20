"""Unit tests for capability model and require_permission dependency.

Spec 015-rbac-ui-lib, tasks T018 + MVP test plan.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    ROLE_CAPABILITIES,
    USERS_MANAGE,
    METERS_COMMAND,
    DER_CONTROL,
    METERS_READ,
    capabilities_for,
    require_permission,
)
from app.models.user import UserRole


class _FakeUser:
    """Minimal stand-in for the SQLAlchemy User model."""

    def __init__(self, role: UserRole, is_active: bool = True, perm=None):
        self.role = role
        self.is_active = is_active
        self.permissions_override = None
        if perm is not None:
            self._jwt_perm = list(perm)


def test_admin_has_all_capabilities():
    admin = _FakeUser(UserRole.ADMIN)
    caps = capabilities_for(admin)
    assert USERS_MANAGE in caps
    assert METERS_COMMAND in caps
    assert DER_CONTROL in caps


def test_operator_lacks_admin_caps():
    op = _FakeUser(UserRole.OPERATOR)
    caps = capabilities_for(op)
    assert METERS_READ in caps  # baseline read access
    assert USERS_MANAGE not in caps
    assert METERS_COMMAND not in caps
    assert DER_CONTROL not in caps


def test_supervisor_has_operational_caps_but_not_users_manage():
    sup = _FakeUser(UserRole.SUPERVISOR)
    caps = capabilities_for(sup)
    assert METERS_COMMAND in caps
    assert DER_CONTROL in caps
    assert USERS_MANAGE not in caps


def test_permissions_override_adds_to_capabilities():
    op = _FakeUser(UserRole.OPERATOR)
    op.permissions_override = [USERS_MANAGE]
    caps = capabilities_for(op)
    assert USERS_MANAGE in caps


def test_require_permission_uses_jwt_claim():
    """When the JWT perm claim is populated, require_permission honours it."""
    dep = require_permission(USERS_MANAGE)
    admin = _FakeUser(UserRole.ADMIN, perm=ROLE_CAPABILITIES[UserRole.ADMIN])
    # Should return the user (no exception).
    assert dep(admin) is admin


def test_require_permission_raises_403_for_operator_on_admin_endpoint():
    dep = require_permission(USERS_MANAGE)
    op = _FakeUser(UserRole.OPERATOR, perm=ROLE_CAPABILITIES[UserRole.OPERATOR])
    with pytest.raises(HTTPException) as exc:
        dep(op)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "forbidden"
    assert exc.value.detail["permission"] == USERS_MANAGE


def test_require_permission_falls_back_to_role_when_claim_missing():
    """Legacy tokens without a perm claim must still be authorised via role."""
    dep = require_permission(METERS_COMMAND)
    sup = _FakeUser(UserRole.SUPERVISOR)  # no _jwt_perm set
    assert dep(sup) is sup


def test_require_permission_denies_operator_mutating_endpoints():
    """Operator must be blocked from der.control and meters.command."""
    for cap in (METERS_COMMAND, DER_CONTROL):
        dep = require_permission(cap)
        op = _FakeUser(UserRole.OPERATOR)
        with pytest.raises(HTTPException) as exc:
            dep(op)
        assert exc.value.status_code == 403
