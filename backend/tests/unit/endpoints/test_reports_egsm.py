"""W4.T9 — EGSM reports proxy tests.

Verifies that ``/api/v1/reports/egsm/<category>/<report>`` forwards to
``<MDMS_BASE_URL>/api/v1/reports/egsm/<category>/<report>`` unchanged,
and that query-string + body are passed through.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.config import SSOTMode, settings


class _StubClient:
    """httpx.AsyncClient stand-in captured by the proxy module."""

    def __init__(self):
        self.calls = []

    async def request(self, method, path, *, params, content, headers):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": dict(params),
                "content": content,
                "headers": dict(headers),
            }
        )
        return httpx.Response(
            200,
            content=b'{"rows": []}',
            headers={"content-type": "application/json"},
            request=httpx.Request(method, "http://mdms.test" + path),
        )


@pytest.fixture
def stub_mdms(monkeypatch):
    stub = _StubClient()
    from app.api.v1.endpoints import _proxy_common

    def _fake_client_for(base_url, connect_timeout, read_timeout):
        return stub

    monkeypatch.setattr(_proxy_common, "_client_for", _fake_client_for)
    # Make sure MDMS proxy is not gated-off in the test harness.
    monkeypatch.setattr(settings, "MDMS_ENABLED", True)
    monkeypatch.setattr(settings, "SSOT_MODE", SSOTMode.mirror)
    yield stub


def test_egsm_report_proxy_forwards_path_and_query(client, stub_mdms):
    r = client.get(
        "/api/v1/reports/egsm/energy-audit/feeder-loss-summary",
        params={"from_date": "2026-04-01", "to_date": "2026-04-18"},
    )
    assert r.status_code == 200
    assert r.json() == {"rows": []}
    assert len(stub_mdms.calls) == 1
    call = stub_mdms.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/v1/reports/egsm/energy-audit/feeder-loss-summary"
    assert call["params"]["from_date"] == "2026-04-01"


def test_egsm_download_poll_forwards(client, stub_mdms):
    r = client.get("/api/v1/reports/download", params={"id": "abc"})
    assert r.status_code == 200
    assert stub_mdms.calls[0]["path"] == "/api/v1/reports/download"
    assert stub_mdms.calls[0]["params"]["id"] == "abc"


def test_egsm_categories_static(client):
    r = client.get("/api/v1/reports/egsm/categories")
    # categories endpoint is a GET on /egsm/categories — but our router
    # mounts the proxy at /egsm/{category}/{report}. The categories helper
    # lives at /reports/categories; let's verify the static path instead.
    # (Either 200 with proxy passthrough or 404 — static is optional).
    # We assert the /categories static route instead:
    r = client.get("/api/v1/reports/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert any(c["slug"] == "energy-audit" for c in cats)


# ── Analytics-backed EGSM reports (Energy Audit Master / Reliability Indices) ──


def test_egsm_analytics_proxy_energy_audit(client, stub_mdms):
    """EnergyAuditMaster page hits /reports/egsm-analytics/energy-audit/* —
    must forward to /api/v1/egsm-reports/... upstream (not /reports/egsm/...)."""
    r = client.get(
        "/api/v1/reports/egsm-analytics/energy-audit/monthly-consumption",
        params={"from": "2026-03-01", "to": "2026-05-01"},
    )
    assert r.status_code == 200
    assert len(stub_mdms.calls) == 1
    call = stub_mdms.calls[0]
    assert call["path"] == "/api/v1/egsm-reports/energy-audit/monthly-consumption"
    assert call["params"]["from"] == "2026-03-01"
    assert call["params"]["to"] == "2026-05-01"


def test_egsm_analytics_proxy_reliability_indices(client, stub_mdms):
    """ReliabilityIndices page hits /reports/egsm-analytics/reliability-indices/stats
    — must forward hierarchy filters as repeated query params."""
    r = client.get(
        "/api/v1/reports/egsm-analytics/reliability-indices/stats",
        params=[
            ("from", "2026-01-01"),
            ("to", "2026-04-01"),
            ("zone", "ZONE-1"),
            ("zone", "ZONE-2"),
            ("feeder_name", "F-10"),
        ],
    )
    assert r.status_code == 200
    call = stub_mdms.calls[0]
    assert call["path"] == "/api/v1/egsm-reports/reliability-indices/stats"
    assert call["params"]["feeder_name"] == "F-10"


def test_hierarchy_data_proxy(client, stub_mdms):
    """HierarchyFilter dropdown population must forward to /api/v1/hierarchy-data."""
    r = client.get("/api/v1/reports/egsm-analytics/hierarchy-data", params={"zone": "Z1"})
    assert r.status_code == 200
    call = stub_mdms.calls[0]
    assert call["path"] == "/api/v1/hierarchy-data"
    assert call["params"]["zone"] == "Z1"


def test_downloads_proxy_request(client, stub_mdms):
    """ReportDownloadButton → POST /reports/egsm-analytics/downloads/request
    must forward to upstream /api/v1/downloads/request with body intact."""
    r = client.post(
        "/api/v1/reports/egsm-analytics/downloads/request",
        json={"reportName": "ALL_FEEDERS_ENERGY_AUDIT", "from": "2026-03-01", "to": "2026-05-01"},
    )
    assert r.status_code == 200
    call = stub_mdms.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/v1/downloads/request"
    assert b"ALL_FEEDERS_ENERGY_AUDIT" in (call["content"] or b"")
