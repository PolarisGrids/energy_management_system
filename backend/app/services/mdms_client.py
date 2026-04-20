"""
MDMS Integration Client — spec 018 W1.T6 rewrite.

See hes_client.py for the sibling implementation. Shape and resilience
behaviour are identical; only the URL map differs.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.services._resilient_http import (
    CircuitBreakerError,
    ResilientClientConfig,
    ResilientHTTPClient,
)

__all__ = ["MDMSClient", "mdms_client", "CircuitBreakerError"]


def _build_cfg() -> ResilientClientConfig:
    return ResilientClientConfig(
        name="mdms",
        base_url=settings.MDMS_BASE_URL,
        connect_timeout=settings.MDMS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.MDMS_READ_TIMEOUT_SECONDS,
        max_retries=settings.MDMS_MAX_RETRIES,
        retry_backoff_base_ms=settings.MDMS_RETRY_BACKOFF_BASE_MS,
        breaker_fail_max=settings.MDMS_BREAKER_FAIL_MAX,
        breaker_reset_seconds=settings.MDMS_BREAKER_RESET_SECONDS,
        api_key=settings.MDMS_API_KEY,
    )


class MDMSClient:
    def __init__(self, cfg: Optional[ResilientClientConfig] = None):
        self._http = ResilientHTTPClient(cfg or _build_cfg())

    @property
    def breaker(self):
        return self._http.breaker

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── CIS ──
    async def get_consumer(self, account: str):
        return await self._http.get(f"/api/v1/cis/consumers/{account}")

    async def list_consumers(self, params: dict | None = None):
        return await self._http.get("/api/v1/cis/consumers", params=params or {})

    async def get_hierarchy(self, node: str | None = None):
        params = {"node": node} if node else {}
        return await self._http.get("/api/v1/cis/hierarchy", params=params)

    # ── Readings ──
    async def get_readings(self, meter: str, frm: str, to: str, interval: str = "half_hour"):
        return await self._http.get(
            "/api/v1/readings", params={"meter": meter, "from": frm, "to": to, "interval": interval}
        )

    # ── VEE ──
    async def vee_summary(self, date: str | None = None):
        return await self._http.get("/api/v1/vee/summary", params={"date": date} if date else {})

    async def vee_exceptions(self, params: dict | None = None):
        return await self._http.get("/api/v1/vee/exceptions", params=params or {})

    # ── Tariff / Billing ──
    async def list_tariffs(self):
        return await self._http.get("/api/v1/tariffs")

    async def get_tariff(self, tariff_id: str):
        return await self._http.get(f"/api/v1/tariffs/{tariff_id}")

    async def billing_determinants(self, account: str, month: str):
        return await self._http.get(
            "/api/v1/billing-determinants", params={"account": account, "month": month}
        )

    # ── Prepaid ──
    async def prepaid_registers(self, account: str):
        return await self._http.get("/api/v1/prepaid/registers", params={"account": account})

    async def prepaid_token_log(self, account: str):
        return await self._http.get("/api/v1/prepaid/token-log", params={"account": account})

    async def prepaid_recharge(self, payload: dict):
        return await self._http.post("/api/v1/prepaid/recharge", json=payload)

    # ── NTL ──
    async def ntl_suspects(self, params: dict | None = None):
        return await self._http.get("/api/v1/ntl/suspects", params=params or {})

    async def ntl_energy_balance(self, dtr: str):
        return await self._http.get("/api/v1/ntl/energy-balance", params={"dtr": dtr})

    # ── Analytics / Reports ──
    async def load_profile(self, params: dict):
        return await self._http.get("/api/v1/analytics/load-profile", params=params)

    # ── EGSM reports (mdms-reports Fastify service, reached via mdms-api gateway) ──
    async def list_egsm_report(self, category: str, report: str, params: dict | None = None):
        """Proxy helper for the mdms-reports EGSM catalogue.

        Upstream path follows ``/api/v1/reports/egsm/<category>/<report>`` per
        ``contracts/mdms-integration.md``. Errors bubble up; callers are
        expected to catch and fall back to local data with ``source: ems-local``.
        """
        return await self._http.get(
            f"/api/v1/reports/egsm/{category}/{report}",
            params=params or {},
        )

    # ── CIS lookups (device search + hierarchy browser) ──
    async def search_consumers(self, query: str, limit: int = 20):
        return await self._http.get(
            "/api/v1/cis/consumers",
            params={"search": query, "limit": limit},
        )

    # ── WFM (spec 018 W3.T4) ──
    async def create_wfm_work_order(self, payload: dict):
        """POST to MDMS WFM proxy — called by the outage dispatch endpoint."""
        return await self._http.post("/api/v1/wfm/work-orders", json=payload)

    async def ping(self) -> bool:
        """Health probe — MDMS gateway exposes unauthenticated `/healthz`.
        (`/health` is 404, and `/api/v1/health` needs auth → 401.)"""
        try:
            resp = await self._http.request("GET", "/healthz")
            return 200 <= resp.status_code < 300
        except Exception:
            return False


mdms_client = MDMSClient()
