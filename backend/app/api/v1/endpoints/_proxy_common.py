"""
Common HTTP-proxy plumbing for `/api/v1/mdms/*` and `/api/v1/hes/*`.

Responsibilities:

* Forward every allowed method (GET/POST/PUT/PATCH/DELETE) transparently.
* Propagate W3C trace-context (``traceparent``, ``tracestate``) and EMS
  conventions (``x-user-story-id``, ``x-user-id``, ``x-forwarded-for``).
* Honour SSOT mode + per-integration feature flag — disabled path returns
  503 with the contract-specified error envelope.
* Map upstream outages to a 503 with ``UPSTREAM_*_UNAVAILABLE`` (see
  contracts/mdms-integration.md §EMS Circuit-Breaker Behaviour).

Kept deliberately thin: the real resilience (retry, circuit breaker, metrics)
lives in `services.hes_client` / `services.mdms_client` for named calls.
Proxy endpoints are the escape hatch for ad-hoc reads the UI needs.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import HTTPException, Request, Response

from app.core.config import SSOTMode, settings

logger = logging.getLogger(__name__)

# A single long-lived pool per upstream keeps TLS/TCP warm.
_clients: dict[str, httpx.AsyncClient] = {}


def _client_for(base_url: str, connect_timeout: float, read_timeout: float) -> httpx.AsyncClient:
    key = f"{base_url}|{connect_timeout}|{read_timeout}"
    client = _clients.get(key)
    if client is None:
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=read_timeout),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=False,
        )
        _clients[key] = client
    return client


async def shutdown_proxy_clients() -> None:
    """Close every pooled httpx client. Wire into FastAPI shutdown."""
    for c in list(_clients.values()):
        try:
            await c.aclose()
        except Exception:  # pragma: no cover
            pass
    _clients.clear()


# Hop-by-hop / unsafe headers we should never forward.
_FORBIDDEN_FORWARD_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "accept-encoding",  # let httpx negotiate
}


def _forward_headers(request: Request, *, api_key: Optional[str]) -> dict[str, str]:
    fwd: dict[str, str] = {}
    # Always propagate W3C trace context + EMS conventions.
    for h in ("traceparent", "tracestate", "x-user-story-id", "x-user-id", "x-operator-ip"):
        v = request.headers.get(h)
        if v:
            fwd[h] = v
    # Client IP — preserve existing XFF chain + append peer.
    xff = request.headers.get("x-forwarded-for")
    peer_ip = request.client.host if request.client else ""
    fwd["x-forwarded-for"] = f"{xff}, {peer_ip}" if xff else peer_ip
    fwd["user-agent"] = f"polaris-ems/1.0 ({settings.DEPLOY_ENV.value})"
    # Best-effort auth propagation: prefer upstream API key, fall back to caller's bearer.
    if api_key:
        fwd["x-api-key"] = api_key
    if request.headers.get("authorization") and "authorization" not in fwd:
        fwd["authorization"] = request.headers["authorization"]
    # Pass content-type through for writes.
    if request.headers.get("content-type"):
        fwd["content-type"] = request.headers["content-type"]
    return fwd


def _gate(*, integration_flag_name: str, integration_name: str) -> None:
    """Raise 503 if the integration is disabled by SSOT or flag."""
    mode = settings.SSOT_MODE
    enabled = getattr(settings, integration_flag_name, False)
    if mode == SSOTMode.disabled or not enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": f"UPSTREAM_{integration_name.upper()}_DISABLED",
                    "message": (
                        f"{integration_name} integration disabled "
                        f"(SSOT_MODE={mode.value}, {integration_flag_name}={enabled})"
                    ),
                }
            },
        )


async def proxy_request(
    request: Request,
    *,
    base_url: str,
    upstream_path: str,
    integration_flag_name: str,
    integration_name: str,
    api_key: Optional[str],
    connect_timeout: float,
    read_timeout: float,
) -> Response:
    _gate(integration_flag_name=integration_flag_name, integration_name=integration_name)

    client = _client_for(base_url, connect_timeout, read_timeout)
    headers = _forward_headers(request, api_key=api_key)

    body: Optional[bytes] = None
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        body = await request.body()

    try:
        upstream = await client.request(
            request.method,
            upstream_path,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        logger.warning("%s timeout %s %s: %s", integration_name, request.method, upstream_path, exc)
        raise HTTPException(
            status_code=504,
            detail={
                "error": {
                    "code": f"UPSTREAM_{integration_name.upper()}_TIMEOUT",
                    "message": f"{integration_name} timed out after {read_timeout}s",
                }
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("%s connect failure %s %s: %s", integration_name, request.method, upstream_path, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": f"UPSTREAM_{integration_name.upper()}_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        ) from exc

    # Strip hop-by-hop headers on the way back.
    out_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _FORBIDDEN_FORWARD_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )
