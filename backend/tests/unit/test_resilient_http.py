"""Unit tests for the resilient HTTP client's circuit-breaker + retry state (W1.T5/T6)."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services._resilient_http import (
    CircuitBreakerError,
    ResilientClientConfig,
    ResilientHTTPClient,
    _FallbackBreaker,
)


def test_fallback_breaker_opens_after_fail_max():
    b = _FallbackBreaker(fail_max=3, reset_timeout=1, name="t")
    assert b.state == "closed"
    for _ in range(3):
        b.on_failure()
    assert b.state == "open"
    with pytest.raises(CircuitBreakerError):
        b.before_call()


def test_fallback_breaker_half_open_after_cooldown():
    b = _FallbackBreaker(fail_max=2, reset_timeout=0, name="t")
    b.on_failure(); b.on_failure()
    assert b.state == "open"
    # Force cooldown to elapse.
    b._opened_at = time.monotonic() - 10
    b.before_call()  # should transition to half-open
    assert b.state == "half-open"
    b.on_success()
    assert b.state == "closed"


def test_fallback_breaker_reopens_on_halfopen_fail():
    b = _FallbackBreaker(fail_max=2, reset_timeout=0, name="t")
    b.on_failure(); b.on_failure()
    b._opened_at = time.monotonic() - 10
    b.before_call()
    assert b.state == "half-open"
    b.on_failure()
    assert b.state == "open"


@pytest.mark.asyncio
async def test_client_retries_then_opens_breaker(monkeypatch):
    """3 500s → 3 retries, breaker opens at fail_max, subsequent call short-circuits."""
    cfg = ResilientClientConfig(
        name="t",
        base_url="http://x.invalid",
        connect_timeout=0.1,
        read_timeout=0.1,
        max_retries=3,
        retry_backoff_base_ms=1,  # keep test snappy
        breaker_fail_max=3,
        breaker_reset_seconds=1,
    )
    client = ResilientHTTPClient(cfg)

    calls = {"n": 0}

    async def fake_request(self, method, path, **kw):
        calls["n"] += 1
        import httpx

        return httpx.Response(500, request=httpx.Request(method, path))

    # Patch the httpx.AsyncClient.request used by the resilient client.
    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    with pytest.raises(httpx.HTTPStatusError):
        await client.request("GET", "/boom")
    assert calls["n"] == 3
    # Breaker should be OPEN now.
    assert client.breaker.state == "open"

    # Next call must be refused immediately by the breaker.
    with pytest.raises(CircuitBreakerError):
        await client.request("GET", "/boom")

    await client.aclose()


@pytest.mark.asyncio
async def test_client_success_resets_failure_count(monkeypatch):
    cfg = ResilientClientConfig(
        name="t",
        base_url="http://x.invalid",
        connect_timeout=0.1,
        read_timeout=0.1,
        max_retries=3,
        retry_backoff_base_ms=1,
        breaker_fail_max=5,
        breaker_reset_seconds=30,
    )
    client = ResilientHTTPClient(cfg)
    seq = iter([500, 500, 200])

    async def fake_request(self, method, path, **kw):
        import httpx

        code = next(seq)
        return httpx.Response(code, request=httpx.Request(method, path), content=b"{}")

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    resp = await client.request("GET", "/eventual")
    assert resp.status_code == 200
    # Breaker stayed closed; two failures weren't enough to open.
    assert client.breaker.state == "closed"
    await client.aclose()
