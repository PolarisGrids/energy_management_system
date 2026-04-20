"""Unit tests — spec 018 W4.T11 saved dashboard layouts CRUD."""
from __future__ import annotations

import pytest


def test_create_and_list_layout(client, test_user):
    resp = client.post(
        "/api/v1/dashboards",
        json={
            "name": "My Grid Ops",
            "widgets": [
                {"id": "w1", "type": "kpi", "x": 0, "y": 0, "w": 3, "h": 2, "config": {"metric": "online_meters"}, "refresh_s": 30}
            ],
            "shared_with_roles": [],
            "is_default": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "My Grid Ops"
    assert body["is_default"] is True
    assert body["owner_user_id"] == str(test_user.id)
    assert len(body["widgets"]) == 1

    list_resp = client.get("/api/v1/dashboards")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["is_default"] is True
    assert items[0]["shared"] is False


def test_get_update_delete_layout(client):
    created = client.post(
        "/api/v1/dashboards",
        json={"name": "L1", "widgets": []},
    ).json()
    lid = created["id"]

    got = client.get(f"/api/v1/dashboards/{lid}")
    assert got.status_code == 200
    assert got.json()["name"] == "L1"

    patched = client.patch(
        f"/api/v1/dashboards/{lid}",
        json={"name": "L1-renamed", "widgets": [{"id": "w", "type": "chart"}]},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "L1-renamed"
    assert len(patched.json()["widgets"]) == 1

    deleted = client.delete(f"/api/v1/dashboards/{lid}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/dashboards/{lid}")
    assert missing.status_code == 404


def test_default_layout_uniqueness(client):
    first = client.post("/api/v1/dashboards", json={"name": "A", "is_default": True}).json()
    second = client.post("/api/v1/dashboards", json={"name": "B", "is_default": True}).json()

    items = client.get("/api/v1/dashboards").json()
    # Exactly one layout should have is_default=True (the newer one).
    defaults = [i for i in items if i["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == second["id"]


def test_duplicate_layout(client):
    created = client.post(
        "/api/v1/dashboards",
        json={"name": "Original", "widgets": [{"id": "x"}]},
    ).json()
    dup = client.post(f"/api/v1/dashboards/{created['id']}/duplicate")
    assert dup.status_code == 201
    body = dup.json()
    assert body["id"] != created["id"]
    assert body["name"].startswith("Copy of")
    assert body["is_default"] is False
    assert body["shared_with_roles"] == []
    assert len(body["widgets"]) == 1


def test_cannot_modify_others_layout(client, SessionLocal):
    from app.models.dashboard_layout import DashboardLayout

    other_id = "other-layout-id"
    with SessionLocal() as s:
        s.add(DashboardLayout(
            id=other_id,
            owner_user_id="999",  # not the test user
            name="Someone else's",
            widgets=[],
            shared_with_roles=[],
            is_default=False,
        ))
        s.commit()

    # test_user is admin in the conftest — admin has dashboard.admin → CAN.
    # To prove cross-user blocking we drop the user to operator temporarily.
    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User, UserRole

    operator = User(
        id=7, username="op", email="op@e.com", full_name="Op",
        hashed_password="x", role=UserRole.OPERATOR, is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: operator
    try:
        # Operator without dashboard.admin can't see or modify another user's layout.
        got = client.get(f"/api/v1/dashboards/{other_id}")
        assert got.status_code == 404  # hidden from non-owner

        patched = client.patch(
            f"/api/v1/dashboards/{other_id}",
            json={"name": "hack"},
        )
        assert patched.status_code == 403
    finally:
        # Restore test_user override — conftest doesn't replace this automatically.
        from tests.unit.endpoints.conftest import (  # type: ignore
            client as _client_fixture,  # noqa: F401
        )
