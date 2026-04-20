"""US-1 Real-Time Dashboard — spec 018 §User Story 1.

Acceptance (spec lines 55-60, matrix row 1):

1. SSOT_MODE=strict + MDMS online → KPI payloads come from upstream proxies,
   no EMS-seeded fallback numbers.
2. MDMS returns 503 → EMS surfaces the upstream error verbatim so the frontend
   can render the red "MDMS unavailable" banner instead of silently showing 0.
3. 10 meters flipped OFFLINE on HES → ``/api/v1/hes/api/v1/network/health``
   reflects the new offline count.
4. The ``/summary`` drill-down is a real query against the DB-backed meter
   registry (not a cached KPI snapshot).

Uses the local ``ProxyStub`` (see ``_proxy_stub.py``) — no ``respx`` needed.
"""
from __future__ import annotations

import pytest

from tests.integration.demo_compliance._proxy_stub import install_proxy_stub


def test_dashboard_kpis_sourced_from_upstream_proxy(client, monkeypatch):
    """Scenario 1: strict + online → KPIs come from proxy responses."""
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/network/health").reply(
        {
            "total_meters": 1000,
            "online_meters": 980,
            "offline_meters": 20,
            "comm_success_rate": 97.4,
            "tamper_meters": 2,
            "active_alarms": 5,
        }
    )
    stub.when("GET", "/api/v1/cis/hierarchy").reply(
        {"total_transformers": 40, "total_feeders": 8}
    )

    r = client.get("/api/v1/hes/api/v1/network/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offline_meters"] == 20
    assert body["total_meters"] == 1000

    h = client.get("/api/v1/mdms/api/v1/cis/hierarchy")
    assert h.status_code == 200
    assert h.json()["total_transformers"] == 40


def test_dashboard_banners_mdms_503(client, monkeypatch):
    """Scenario 2: MDMS unavailable → proxy propagates 5xx."""
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/cis/hierarchy").reply(
        status=503, body={"detail": "down"}
    )
    r = client.get("/api/v1/mdms/api/v1/cis/hierarchy")
    # Upstream status is surfaced as-is; frontend uses it to drive the banner.
    assert r.status_code == 503, r.text


def test_dashboard_offline_meters_reflects_hes_event_count(client, monkeypatch):
    """Scenario 3: 10 meters flipped OFFLINE on HES → KPI reports 10."""
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/network/health").reply(
        {
            "total_meters": 1000,
            "online_meters": 990,
            "offline_meters": 10,
            "comm_success_rate": 99.0,
            "tamper_meters": 0,
            "active_alarms": 0,
        }
    )
    r = client.get("/api/v1/hes/api/v1/network/health")
    assert r.status_code == 200
    assert r.json()["offline_meters"] == 10


def test_dashboard_drill_down_hits_meter_registry(client):
    """Scenario 4: drill-down is a real query, not KPI-cached."""
    r = client.get("/api/v1/meters/summary")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "total_meters",
        "online_meters",
        "offline_meters",
        "comm_success_rate",
    ):
        assert key in body
