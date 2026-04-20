"""Scenario API proxy — spec 018 W3.T14.

Forwards frontend scenario-control calls to the external simulator service
(per `contracts/simulator-cooperation.md`). Lives alongside the existing
local `simulation` engine endpoints; a distinct URL prefix
(`/api/v1/simulation-proxy/*`) prevents path collisions.

Route map:

    /scenarios                                    → GET  /scenarios
    /scenarios/{name}/start                       → POST /scenarios/{name}/start
    /scenarios/{name}/step                        → POST /scenarios/{name}/step
    /scenarios/{name}/stop                        → POST /scenarios/{name}/stop
    /scenarios/{name}/status                      → GET  /scenarios/{name}/status
    /sequences                                    → GET  /sequences
    /sequences/{name}/start                       → POST /sequences/{name}/start
    /sequences/{name}/status                      → GET  /sequences/{name}/status

All calls use the resilient HTTP client (retry + circuit breaker) and
forward incoming `traceparent` / `tracestate` / `authorization` headers.
An `ems_correlation_id` response header is emitted so the UI can
correlate the call with its trace.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status as http_status

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.services._resilient_http import (
    CircuitBreakerError,
    ResilientClientConfig,
    ResilientHTTPClient,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Lazy client (one per process) ───────────────────────────────────────────

_client: Optional[ResilientHTTPClient] = None


def _get_client() -> ResilientHTTPClient:
    """Return a lazily-initialised resilient HTTP client for the simulator."""
    global _client
    base_url = getattr(settings, "SIMULATOR_BASE_URL", None) or "http://localhost:9200"
    if _client is None or _client.cfg.base_url.rstrip("/") != base_url.rstrip("/"):
        _client = ResilientHTTPClient(
            ResilientClientConfig(
                name="simulator",
                base_url=base_url,
                connect_timeout=5.0,
                read_timeout=15.0,
                max_retries=2,
                retry_backoff_base_ms=100,
                breaker_fail_max=5,
                breaker_reset_seconds=30,
                api_key=getattr(settings, "SIMULATOR_API_KEY", None),
            )
        )
    return _client


def _forward_headers(request: Request) -> dict:
    """Copy trace + auth headers from the inbound request."""
    headers: dict = {}
    for name in ("traceparent", "tracestate", "authorization", "x-user-story-id"):
        v = request.headers.get(name)
        if v:
            headers[name] = v
    return headers


async def _proxy(
    request: Request,
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: Optional[dict] = None,
) -> Response:
    client = _get_client()
    correlation_id = str(uuid.uuid4())
    headers = _forward_headers(request)

    try:
        resp = await client.request(method, path, params=params, json=json_body, headers=headers)
    except CircuitBreakerError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "simulator_circuit_open", "message": str(exc)},
        )
    except Exception as exc:
        logger.warning("simulator proxy transport failure %s %s: %s", method, path, exc)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "simulator_unreachable", "message": str(exc)[:200]},
        )

    # Pass through upstream status + JSON body, stamp correlation header.
    out_headers = {
        "ems-correlation-id": correlation_id,
        "x-simulator-trace-id": current_trace_id() or "",
    }
    if 200 <= resp.status_code < 600:
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
            headers=out_headers,
        )
    # Defensive — unreachable given resilient client contract.
    raise HTTPException(status_code=resp.status_code, detail=resp.text)


# ── Scenario endpoints ──


@router.get("/scenarios")
async def list_scenarios(request: Request, _: User = Depends(get_current_user)):
    return await _proxy(request, "GET", "/scenarios")


@router.get("/scenarios/{name}/status")
async def scenario_status(name: str, request: Request, _: User = Depends(get_current_user)):
    return await _proxy(request, "GET", f"/scenarios/{name}/status")


@router.post("/scenarios/{name}/start")
async def scenario_start(
    name: str, request: Request, _: User = Depends(get_current_user)
):
    body = await _safe_json(request)
    return await _proxy(request, "POST", f"/scenarios/{name}/start", json_body=body)


@router.post("/scenarios/{name}/step")
async def scenario_step(
    name: str, request: Request, _: User = Depends(get_current_user)
):
    body = await _safe_json(request)
    return await _proxy(request, "POST", f"/scenarios/{name}/step", json_body=body)


@router.post("/scenarios/{name}/stop")
async def scenario_stop(name: str, request: Request, _: User = Depends(get_current_user)):
    return await _proxy(request, "POST", f"/scenarios/{name}/stop")


# ── Sequence endpoints ──


@router.get("/sequences")
async def list_sequences(request: Request, _: User = Depends(get_current_user)):
    return await _proxy(request, "GET", "/sequences")


@router.post("/sequences/{name}/start")
async def sequence_start(
    name: str, request: Request, _: User = Depends(get_current_user)
):
    body = await _safe_json(request)
    return await _proxy(request, "POST", f"/sequences/{name}/start", json_body=body)


@router.get("/sequences/{name}/status")
async def sequence_status(
    name: str, request: Request, _: User = Depends(get_current_user)
):
    return await _proxy(request, "GET", f"/sequences/{name}/status")


# ── Helpers ──


async def _safe_json(request: Request) -> Any:
    """Return JSON body or None — avoids crash on empty/invalid bodies."""
    try:
        if request.headers.get("content-length", "0") in ("", "0"):
            return None
        return await request.json()
    except Exception:
        return None
