"""W4.T6 — AppBuilder CRUD + publish workflow tests.

Covers create / list / update (version bump) / preview / publish / archive
for the three definition types (apps, rules, algorithms). Also verifies
the role-gating placeholder (X-User-Role header) and the uniqueness of the
PUBLISHED status per slug.
"""
from __future__ import annotations

import pytest

from app.models.app_builder import (
    AlgorithmDef,
    AppDef,
    RuleDef,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PREVIEW,
    STATUS_PUBLISHED,
)


# ── /apps ────────────────────────────────────────────────────────────────────


def test_app_create_and_list(client):
    r = client.post(
        "/api/v1/apps",
        json={"slug": "my-app", "name": "My App", "definition": {"grid": [[]]}},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "my-app"
    assert body["version"] == 1
    assert body["status"] == STATUS_DRAFT

    r = client.get("/api/v1/apps")
    assert r.status_code == 200
    slugs = [a["slug"] for a in r.json()]
    assert "my-app" in slugs


def test_app_slug_conflict(client):
    client.post("/api/v1/apps", json={"slug": "dup", "name": "A"})
    r = client.post("/api/v1/apps", json={"slug": "dup", "name": "B"})
    assert r.status_code == 409


def test_app_update_bumps_version(client):
    client.post("/api/v1/apps", json={"slug": "v-app", "name": "V1"})
    r = client.put("/api/v1/apps/v-app", json={"name": "V2"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert r.json()["name"] == "V2"


def test_app_publish_requires_role(client):
    client.post("/api/v1/apps", json={"slug": "pub-a", "name": "A"})
    # Without the role header the ADMIN test user passes (UserRole.ADMIN).
    r = client.post(
        "/api/v1/apps/pub-a/publish",
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == STATUS_PUBLISHED


def test_app_publish_blocked_without_role_and_non_admin(client, test_user, monkeypatch):
    from app.models.user import UserRole

    test_user.role = UserRole.VIEWER
    client.post("/api/v1/apps", json={"slug": "gate-a", "name": "A"})
    r = client.post("/api/v1/apps/gate-a/publish", json={})
    assert r.status_code == 403
    assert "MISSING_APP_BUILDER_PUBLISH_ROLE" in r.text

    # Supplying the publish role header unlocks it.
    r = client.post(
        "/api/v1/apps/gate-a/publish",
        json={},
        headers={"X-User-Role": "app_builder_publish"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == STATUS_PUBLISHED


def test_app_publish_archives_previous(client, db):
    client.post("/api/v1/apps", json={"slug": "arch-a", "name": "A1"})
    client.post("/api/v1/apps/arch-a/publish", json={})
    client.put("/api/v1/apps/arch-a", json={"name": "A2"})
    client.post("/api/v1/apps/arch-a/publish", json={})
    rows = (
        db.query(AppDef)
        .filter(AppDef.slug == "arch-a")
        .order_by(AppDef.version)
        .all()
    )
    assert [r.status for r in rows] == [STATUS_ARCHIVED, STATUS_PUBLISHED]


def test_app_preview_moves_status(client):
    client.post("/api/v1/apps", json={"slug": "prev-a", "name": "A"})
    r = client.post("/api/v1/apps/prev-a/preview")
    assert r.status_code == 200
    assert r.json()["status"] == STATUS_PREVIEW


def test_app_versions_list(client):
    client.post("/api/v1/apps", json={"slug": "v-hist", "name": "V1"})
    client.put("/api/v1/apps/v-hist", json={"name": "V2"})
    client.put("/api/v1/apps/v-hist", json={"name": "V3"})
    r = client.get("/api/v1/apps/v-hist/versions")
    assert r.status_code == 200
    versions = [v["version"] for v in r.json()]
    assert versions == [3, 2, 1]


# ── /app-rules ───────────────────────────────────────────────────────────────


def test_rule_crud(client):
    r = client.post(
        "/api/v1/app-rules",
        json={"slug": "r-1", "name": "R1", "definition": {"when": "x>1"}},
    )
    assert r.status_code == 201
    r = client.get("/api/v1/app-rules")
    assert r.status_code == 200
    assert any(x["slug"] == "r-1" for x in r.json())

    r = client.put("/api/v1/app-rules/r-1", json={"name": "R1 updated"})
    assert r.status_code == 200
    assert r.json()["version"] == 2


# ── /algorithms ──────────────────────────────────────────────────────────────


def test_algorithm_run_sandboxed(client):
    src = "def main(i):\n    return i['a'] + i['b']\n"
    client.post(
        "/api/v1/algorithms",
        json={"slug": "sum", "name": "Sum", "source": src},
    )
    r = client.post(
        "/api/v1/algorithms/sum/run",
        json={"inputs": {"a": 10, "b": 5}, "timeout_seconds": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["result"] == 15


def test_algorithm_run_forbidden_import_returns_error(client):
    src = "import os\ndef main(i):\n    return 1\n"
    client.post(
        "/api/v1/algorithms",
        json={"slug": "bad", "name": "Bad", "source": src},
    )
    r = client.post(
        "/api/v1/algorithms/bad/run",
        json={"inputs": {}, "timeout_seconds": 2},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_algorithm_publish_once_per_slug(client, db):
    src = "def main(i):\n    return 1\n"
    client.post(
        "/api/v1/algorithms",
        json={"slug": "pub-x", "name": "X", "source": src},
    )
    client.post("/api/v1/algorithms/pub-x/publish", json={})
    # Bump version + publish again; prior one should become ARCHIVED.
    client.put(
        "/api/v1/algorithms/pub-x",
        json={"source": "def main(i):\n    return 2\n"},
    )
    client.post("/api/v1/algorithms/pub-x/publish", json={})
    statuses = [
        r.status
        for r in db.query(AlgorithmDef)
        .filter(AlgorithmDef.slug == "pub-x")
        .order_by(AlgorithmDef.version)
        .all()
    ]
    assert statuses == [STATUS_ARCHIVED, STATUS_PUBLISHED]
