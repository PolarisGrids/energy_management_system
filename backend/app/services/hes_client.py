"""
HES Integration Client — spec 018 W1.T5 rewrite.

Always makes a real call. The caller is responsible for honouring SSOT_MODE /
HES_ENABLED flags; this client is intentionally *not* a fallback shim.

Features:
* real base URL from `settings.HES_BASE_URL`
* 5 s connect + 10 s read timeouts (settings-driven)
* 3 retries with exponential backoff (100 ms base) on 5xx / transport errors
* circuit breaker via pybreaker (opens after 5 consecutive failures, 30 s cooldown)
* W3C trace-context headers propagated on every call
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.services._resilient_http import (
    CircuitBreakerError,
    ResilientClientConfig,
    ResilientHTTPClient,
)

__all__ = ["HESClient", "hes_client", "CircuitBreakerError"]


def _build_cfg() -> ResilientClientConfig:
    return ResilientClientConfig(
        name="hes",
        base_url=settings.HES_BASE_URL,
        connect_timeout=settings.HES_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.HES_READ_TIMEOUT_SECONDS,
        max_retries=settings.HES_MAX_RETRIES,
        retry_backoff_base_ms=settings.HES_RETRY_BACKOFF_BASE_MS,
        breaker_fail_max=settings.HES_BREAKER_FAIL_MAX,
        breaker_reset_seconds=settings.HES_BREAKER_RESET_SECONDS,
        api_key=settings.HES_API_KEY,
    )


class HESClient:
    """Named REST calls to HES routing-service."""

    def __init__(self, cfg: Optional[ResilientClientConfig] = None):
        self._http = ResilientHTTPClient(cfg or _build_cfg())

    # Expose the breaker for /health and tests.
    @property
    def breaker(self):
        return self._http.breaker

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── REST calls (align with contracts/hes-integration.md) ──
    async def get_dcus(self):
        return await self._http.get("/api/v1/dcus")

    async def get_dcu_health(self, dcu_id: str):
        return await self._http.get(f"/api/v1/dcus/{dcu_id}/health")

    async def get_network_health(self):
        return await self._http.get("/api/v1/network/health")

    async def get_meter_status(self, serial: str):
        return await self._http.get(f"/api/v1/meters/{serial}/status")

    async def post_command(self, type_: str, meter_serial: str, payload: dict | None = None):
        return await self._http.post(
            "/api/v1/commands",
            json={"type": type_, "meter_serial": meter_serial, "payload": payload or {}},
        )

    async def post_command_batch(self, commands: list[dict]):
        return await self._http.post("/api/v1/commands/batch", json={"commands": commands})

    async def post_timesync(self):
        return await self._http.post("/api/v1/commands/timesync", json={})

    async def create_fota_job(self, payload: dict):
        return await self._http.post("/api/v1/firmware-upgrade", json=payload)

    async def get_fota_job(self, job_id: str):
        return await self._http.get(f"/api/v1/firmware-upgrade/{job_id}")

    async def ping(self) -> bool:
        """Health probe — returns True on 2xx within the short read budget."""
        try:
            resp = await self._http.request("GET", "/health")
            return 200 <= resp.status_code < 300
        except Exception:
            return False


hes_client = HESClient()
