"""Lightweight proxy stub for demo-compliance tests.

Replaces the ``httpx.AsyncClient`` inside :mod:`app.api.v1.endpoints._proxy_common`
with a recorder that returns programmable canned responses. This is the same
pattern used by ``tests/unit/endpoints/test_reports_egsm.py`` and lets us run
without the optional ``respx`` dependency (which is `importorskip`-d in the
shared conftest).

Usage::

    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/vee/summary").reply({"items": [...]})
    r = client.get("/api/v1/mdms/api/v1/vee/summary")
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx


class ProxyStub:
    def __init__(self):
        self.calls: list[dict] = []
        self._routes: list[tuple[str, str, dict]] = []

    def when(self, method: str, path: str):
        parent = self

        class _Binder:
            def reply(
                self,
                body: Any = None,
                status: int = 200,
                headers: Optional[dict] = None,
                content: Optional[bytes] = None,
            ):
                parent._routes.append(
                    (
                        method.upper(),
                        path,
                        {
                            "body": body,
                            "status": status,
                            "headers": headers or {},
                            "content": content,
                        },
                    )
                )
                return self

        return _Binder()

    async def request(self, method, path, *, params=None, content=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": dict(params) if params else {},
                "content": content,
                "headers": dict(headers) if headers else {},
            }
        )
        for m, p, spec in self._routes:
            if m == method and p == path:
                if spec["content"] is not None:
                    out = spec["content"]
                elif spec["body"] is None:
                    out = b""
                elif isinstance(spec["body"], (bytes, bytearray)):
                    out = bytes(spec["body"])
                else:
                    out = json.dumps(spec["body"]).encode()
                hdrs = {"content-type": "application/json", **spec["headers"]}
                return httpx.Response(
                    spec["status"],
                    content=out,
                    headers=hdrs,
                    request=httpx.Request(method, "http://stub.test" + path),
                )
        # Unmatched → 200 {}.
        return httpx.Response(
            200,
            content=b"{}",
            headers={"content-type": "application/json"},
            request=httpx.Request(method, "http://stub.test" + path),
        )


def install_proxy_stub(monkeypatch) -> ProxyStub:
    """Patch ``_proxy_common._client_for`` so every proxy call lands in the stub.

    Also flips the config flags the proxy gate reads.
    """
    from app.api.v1.endpoints import _proxy_common
    from app.core.config import SSOTMode, settings

    stub = ProxyStub()

    def _fake(_base_url, _connect_timeout, _read_timeout):
        return stub

    monkeypatch.setattr(_proxy_common, "_client_for", _fake)
    monkeypatch.setattr(settings, "MDMS_ENABLED", True)
    monkeypatch.setattr(settings, "HES_ENABLED", True)
    monkeypatch.setattr(settings, "SSOT_MODE", SSOTMode.mirror)
    return stub
