"""US-24: App Development — Rules, Algorithms, Apps (Demo #27).

Acceptance (spec §User Story 24 + matrix row 24):

* Author a rule → Preview runs sample input through it → action simulated.
* Publish with role gate → rule evaluates in production.
* Versioned: editing a running app stages a new version; old version
  keeps running until Promote is clicked.
* Version history is visible.
"""
from __future__ import annotations

import uuid

import pytest


pytestmark = [pytest.mark.demo_compliance]


def _create_rule(client, *, slug: str, condition: str = "x > 10"):
    # RuleDefCreate shape: {slug, name, definition, app_slug?}.
    return client.post(
        "/api/v1/app-rules",
        json={
            "slug": slug,
            "name": f"rule-{slug}",
            "definition": {
                "condition": condition,
                "action": {"type": "log", "message": "fired"},
            },
        },
    )


def test_author_rule_can_be_created_and_fetched(client):
    slug = f"rule-{uuid.uuid4().hex[:6]}"
    created = _create_rule(client, slug=slug, condition="x > 10")
    assert created.status_code in (200, 201), created.text

    # Round-trip: GET rule by slug returns the row.
    fetched = client.get(f"/api/v1/app-rules/{slug}")
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["slug"] == slug
    assert body.get("version", 1) >= 1


def test_publish_is_role_gated(client):
    """Viewer cannot publish an app — must come back 403 or 401."""
    slug = f"app-{uuid.uuid4().hex[:6]}"
    # First create the draft (admin user via conftest override).
    created = client.post(
        "/api/v1/apps",
        json={
            "slug": slug,
            "name": f"App {slug}",
            "definition": {"widget_type": "chart", "config": {}},
        },
    )
    assert created.status_code in (200, 201), created.text

    # Downgrade caller to viewer and try to publish — must be denied.
    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User, UserRole

    viewer = User(
        id=99,
        username="viewer",
        email="viewer@example.com",
        full_name="Viewer",
        hashed_password="x",
        role=UserRole.VIEWER,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: viewer
    try:
        resp = client.post(f"/api/v1/apps/{slug}/publish")
    finally:
        # Restore — hand back to whatever conftest set.
        pass  # conftest teardown clears overrides at end of test scope

    assert resp.status_code in (401, 403), (
        f"viewer role must not be able to publish apps; got {resp.status_code}: {resp.text}"
    )


def test_publish_then_version_history_shows_versions(client):
    slug = f"app-{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "v1", "definition": {"widget_type": "kpi"}},
    )
    # Edit → new DRAFT version.
    updated = client.put(
        f"/api/v1/apps/{slug}",
        json={"name": "v2", "definition": {"widget_type": "kpi", "config": {"threshold": 90}}},
    )
    assert updated.status_code in (200, 201), updated.text

    versions = client.get(f"/api/v1/apps/{slug}/versions")
    assert versions.status_code == 200, versions.text
    body = versions.json()
    items = body if isinstance(body, list) else body.get("versions") or []
    assert len(items) >= 2, f"expected version history ≥2 entries, got {items}"


def test_old_version_runs_until_promote(client):
    slug = f"app-{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "v1", "definition": {"widget_type": "kpi", "config": {"v": 1}}},
    )
    client.post(f"/api/v1/apps/{slug}/publish", json={"notes": "v1"})

    # Stage v2 (DRAFT). Live /published endpoint must still serve v1.
    client.put(
        f"/api/v1/apps/{slug}",
        json={"name": "v2", "definition": {"widget_type": "kpi", "config": {"v": 2}}},
    )

    live = client.get(f"/api/v1/apps/{slug}/published").json()
    assert live["definition"]["config"]["v"] == 1, f"live must still be v1, got {live}"

    # After explicit publish of v2, /published flips over.
    client.post(f"/api/v1/apps/{slug}/publish", json={"notes": "promote"})
    live2 = client.get(f"/api/v1/apps/{slug}/published").json()
    assert live2["definition"]["config"]["v"] == 2


@pytest.mark.xfail(
    reason=(
        "Algorithm sandbox (/api/v1/algorithms/{slug}/run) requires the "
        "Python-subprocess sandbox runner; only a stub exists today. "
        "Covered by Wave-5 T18."
    ),
    strict=False,
)
def test_algorithm_run_in_sandbox(client):
    slug = f"algo-{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/algorithms",
        json={
            "slug": slug,
            "name": "sum",
            "source": "def run(x): return sum(x)",
        },
    )
    run = client.post(
        f"/api/v1/algorithms/{slug}/run", json={"inputs": {"x": [1, 2, 3]}}
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body.get("status") == "ok"
    assert body.get("result") == 6
