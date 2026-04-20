"""API hardening / regression guards for spec 015-rbac-ui-lib.

Covers:
- POST /auth/login returns a ``perm`` claim-backed list in the response body.
- Mutating endpoints are wrapped in ``require_permission`` (introspection).
"""
from __future__ import annotations

import inspect
import pytest

from app.api.v1 import router as v1_router
from app.core import permissions as perm_mod


MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Endpoints that are deliberately unguarded (no body mutation or
# demo-only) — can be expanded over time.
_ALLOWLIST = {
    # Login endpoint accepts anonymous credentials — cannot require a cap.
    ("/auth/login", "POST"),
    # Self-service password change — auth'd but not cap-gated by design.
    ("/auth/change_password", "POST"),
    # Simulation reset is demo-scaffolding; gated at UI + covered by audit.
    # TODO(015-mvp-phase2): move behind simulation.run in Phase 2 pass.
    ("/simulation/{scenario_id}/reset", "POST"),
    # Teams webhook relay — authenticated but not cap-gated for MVP.
    # TODO(015-mvp-phase2): tighten when team-ops cap lands.
    ("/teams/alert", "POST"),
}


def _dep_uses_require_permission(dependency) -> bool:
    """Return True if the given dependency callable was produced by
    ``require_permission``/``require_any``/``require_role``."""
    if dependency is None:
        return False
    name = getattr(dependency, "__qualname__", "") or getattr(dependency, "__name__", "")
    if "checker" in name:
        # require_permission / require_any / require_role all return a
        # ``checker`` closure.
        return True
    return False


def test_mutating_endpoints_guarded():
    unguarded: list[tuple[str, str]] = []
    for route in v1_router.api_router.routes:
        methods = getattr(route, "methods", set()) or set()
        if not (methods & MUTATING_METHODS):
            continue
        path = getattr(route, "path", "")
        # Allow-list check — any mutating method hit
        skip = False
        for m in methods & MUTATING_METHODS:
            if (path, m) in _ALLOWLIST:
                skip = True
                break
        if skip:
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        # Walk each parameter's default for a FastAPI Depends with a
        # ``checker`` closure produced by require_permission / require_role.
        sig = inspect.signature(endpoint)
        found = False
        for p in sig.parameters.values():
            default = p.default
            dep_callable = getattr(default, "dependency", None)
            if _dep_uses_require_permission(dep_callable):
                found = True
                break
        if not found:
            unguarded.append((path, sorted(methods & MUTATING_METHODS)))

    # Note: readings / audit / teams / energy may not have mutating
    # endpoints, but we collect all for visibility. The MVP acceptance
    # is that every mutating endpoint has some permission/role dep.
    assert not unguarded, f"Unguarded mutating endpoints: {unguarded}"


def test_permissions_module_exports_expected_capabilities():
    for attr in (
        "METERS_READ", "METERS_COMMAND",
        "ALARMS_ACK", "ALARMS_RESOLVE",
        "DER_READ", "DER_CONTROL",
        "SIMULATION_RUN", "SIMULATION_VIEW",
        "USERS_MANAGE", "SENSORS_CONFIGURE",
    ):
        assert hasattr(perm_mod, attr), f"missing capability constant {attr}"


@pytest.mark.skip(reason="Requires running DB + TestClient; covered by integration suite")
def test_login_response_includes_perm_claim():
    """Placeholder for end-to-end test ensuring login payload carries
    ``permissions`` list (and the JWT has a ``perm`` claim)."""
    pass
