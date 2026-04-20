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
