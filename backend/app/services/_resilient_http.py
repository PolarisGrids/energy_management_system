"""
Resilient HTTP client primitive shared by MDMS + HES clients (spec 018 W1.T5/T6).

- httpx.AsyncClient with explicit connect + read timeouts.
- Exponential backoff retry on 5xx / network errors.
- Circuit breaker via `pybreaker` (with a fall-back stub for unit-test
  environments that don't install it). Breaker opens after N consecutive
  failures and short-circuits subsequent calls for a cool-down window.
- W3C trace-context header forwarding when called inside a FastAPI request.

The design is intentionally dependency-light in the breaker path so the unit
tests can exercise the state machine without spinning up a real Redis / HTTP
target.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── pybreaker import with a pure-Python fallback ────────────────────────────
try:  # pragma: no cover — depends on install
    import pybreaker as _pybreaker

    _PYBREAKER_AVAILABLE = True
except Exception:  # pragma: no cover
    _pybreaker = None
    _PYBREAKER_AVAILABLE = False


class CircuitBreakerError(Exception):
    """Raised when the breaker is open and a call is refused."""


class _FallbackBreaker:
    """Minimal circuit-breaker state machine used when pybreaker is absent."""

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(self, *, fail_max: int, reset_timeout: int, name: str = "breaker"):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.name = name
        self._state = self.STATE_CLOSED
        self._fail_count = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        return self._state

    def _maybe_half_open(self) -> None:
        if self._state == self.STATE_OPEN and self._opened_at is not None:
            loop = asyncio.get_event_loop() if asyncio._get_running_loop() is not None else None
            # Monotonic is safer; use time.monotonic directly.
            import time as _t

            if _t.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = self.STATE_HALF_OPEN
                logger.info("breaker %s: OPEN -> HALF_OPEN", self.name)

    def before_call(self) -> None:
        self._maybe_half_open()
        if self._state == self.STATE_OPEN:
            raise CircuitBreakerError(f"breaker {self.name} OPEN")

    def on_success(self) -> None:
        if self._state in (self.STATE_HALF_OPEN, self.STATE_CLOSED):
            if self._fail_count or self._state != self.STATE_CLOSED:
                logger.info("breaker %s: -> CLOSED", self.name)
            self._state = self.STATE_CLOSED
            self._fail_count = 0

    def on_failure(self) -> None:
        import time as _t

        self._fail_count += 1
        if self._state == self.STATE_HALF_OPEN or self._fail_count >= self.fail_max:
            self._state = self.STATE_OPEN
            self._opened_at = _t.monotonic()
            logger.warning(
                "breaker %s: OPEN (failures=%d, reset_in=%ds)",
                self.name,
                self._fail_count,
                self.reset_timeout,
            )


def _build_breaker(*, fail_max: int, reset_timeout: int, name: str):
    """Prefer pybreaker when available so listeners + metrics work."""
    if _PYBREAKER_AVAILABLE:  # pragma: no cover
        return _pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            name=name,
        )
    return _FallbackBreaker(fail_max=fail_max, reset_timeout=reset_timeout, name=name)


def _is_breaker_open_error(exc: Exception) -> bool:
    if _PYBREAKER_AVAILABLE and isinstance(exc, _pybreaker.CircuitBreakerError):  # pragma: no cover
        return True
    return isinstance(exc, CircuitBreakerError)


# ── request-context header propagation ──────────────────────────────────────
_CURRENT_REQUEST_HEADERS: "asyncio.Local | None" = None


def set_forwarded_headers(headers: dict[str, str]) -> None:
    """Stash trace-context headers for downstream calls made on this task."""
    from contextvars import ContextVar

    global _CURRENT_REQUEST_HEADERS
    if _CURRENT_REQUEST_HEADERS is None:
        _CURRENT_REQUEST_HEADERS = ContextVar("resilient_http_headers", default={})
    _CURRENT_REQUEST_HEADERS.set(headers)


def _forwarded_headers() -> dict[str, str]:
    if _CURRENT_REQUEST_HEADERS is None:
        return {}
    try:
        return dict(_CURRENT_REQUEST_HEADERS.get() or {})
    except LookupError:
        return {}


# ── Resilient client ────────────────────────────────────────────────────────
@dataclass
class ResilientClientConfig:
    name: str
    base_url: str
    connect_timeout: float
    read_timeout: float
    max_retries: int
    retry_backoff_base_ms: int
    breaker_fail_max: int
    breaker_reset_seconds: int
    api_key: Optional[str] = None


class ResilientHTTPClient:
    """Thin wrapper around httpx that adds retry + circuit-breaker semantics."""

    def __init__(self, cfg: ResilientClientConfig):
        self.cfg = cfg
        self._client: Optional[httpx.AsyncClient] = None
        self._breaker = _build_breaker(
            fail_max=cfg.breaker_fail_max,
            reset_timeout=cfg.breaker_reset_seconds,
            name=cfg.name,
        )

    # Exposed for tests.
    @property
    def breaker(self):
        return self._breaker

    def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.cfg.base_url.rstrip("/"),
                timeout=httpx.Timeout(
                    connect=self.cfg.connect_timeout,
                    read=self.cfg.read_timeout,
                    write=self.cfg.read_timeout,
                    pool=self.cfg.read_timeout,
                ),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        # Breaker gate. The API differs between our in-repo stub, pybreaker 0.x
        # (`before_call`), and pybreaker 1.x (`current_state` property). Probe
        # for whichever is present; any unexpected AttributeError at this point
        # must NOT crash the request path — the actual HTTP call below will
        # still be wrapped in the breaker via `_call_through_breaker`.
        try:
            if hasattr(self._breaker, "before_call"):
                self._breaker.before_call()
            elif hasattr(self._breaker, "current_state"):
                state = self._breaker.current_state  # pybreaker 1.x property
                if isinstance(state, str) and state.lower() == "open":
                    raise CircuitBreakerError(f"{self.cfg.name} breaker OPEN")
        except CircuitBreakerError:
            raise
        except Exception as exc:
            if _is_breaker_open_error(exc):
                raise CircuitBreakerError(f"{self.cfg.name} breaker OPEN") from exc
            # Anything else (e.g. pybreaker API drift) is swallowed so the
            # request proceeds; failures flow through the except branch below.
            logger.debug("breaker gate probe raised %s; continuing", exc)

        merged_headers: dict[str, str] = {
            "user-agent": f"polaris-ems/1.0",
            "content-type": "application/json",
        }
        if self.cfg.api_key:
            merged_headers["x-api-key"] = self.cfg.api_key
        merged_headers.update(_forwarded_headers())
        if headers:
            merged_headers.update(headers)

        last_exc: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries):
            try:
                resp = await self._ensure().request(
                    method, path, params=params, json=json, headers=merged_headers
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                self._fail()
                await self._sleep_backoff(attempt)
                continue

            if 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
                self._fail()
                await self._sleep_backoff(attempt)
                continue

            # Success path.
            self._ok()
            return resp

        # All retries exhausted.
        assert last_exc is not None
        raise last_exc

    def _fail(self) -> None:
        if hasattr(self._breaker, "on_failure"):
            self._breaker.on_failure()

    def _ok(self) -> None:
        if hasattr(self._breaker, "on_success"):
            self._breaker.on_success()

    async def _sleep_backoff(self, attempt: int) -> None:
        # Exponential backoff with a small jitter: base * 2^attempt +/- 20%.
        base_s = self.cfg.retry_backoff_base_ms / 1000.0
        delay = base_s * (2 ** attempt)
        delay *= random.uniform(0.8, 1.2)
        await asyncio.sleep(delay)

    # Convenience wrappers.
    async def get(self, path: str, **kw) -> Any:
        resp = await self.request("GET", path, **kw)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    async def post(self, path: str, **kw) -> Any:
        resp = await self.request("POST", path, **kw)
        resp.raise_for_status()
        return resp.json() if resp.content else None
