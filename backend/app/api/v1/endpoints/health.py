"""
GET /api/v1/health — upstream probe for the SSOT layer (spec 018 W1.T10).

Checked components:
  * hes   — HES routing-service `/health`
  * mdms  — MDMS gateway `/health`
  * kafka — broker metadata fetch (aiokafka)
  * db    — `SELECT 1` on the EMS Postgres
  * redis — PING on the configured Redis

Each component returns:
  { "status": "ok|degraded|fail",
    "detail": "<short error if not ok>",
    "latency_ms": <int> }

Top-level `overall` is:
  ok       — every *required* component is ok
  degraded — at least one non-critical component is fail OR kafka is fail
             (EMS can still render most screens without Kafka)
  fail     — the backend Postgres or the SSOT upstream (mode-dependent) is
             down — UI banner must show a red bar.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import SSOTMode, settings
from app.db.base import engine
from app.services.hes_client import hes_client
from app.services.mdms_client import mdms_client

router = APIRouter()


async def _probe_db() -> dict[str, Any]:
    started = time.monotonic()
    try:
        # Use a short-lived connection to avoid hanging on pool exhaustion.
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:
        return {
            "status": "fail",
            "detail": str(exc)[:200],
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


async def _probe_redis() -> dict[str, Any]:
    if not settings.REDIS_URL:
        return {"status": "ok", "detail": "REDIS_URL not configured; skipped"}
    started = time.monotonic()
    try:
        import redis.asyncio as aioredis  # type: ignore

        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        pong = await r.ping()
        await r.close()
        return {
            "status": "ok" if pong else "fail",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "status": "fail",
            "detail": str(exc)[:200],
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


async def _probe_kafka() -> dict[str, Any]:
    if not settings.KAFKA_ENABLED:
        return {"status": "ok", "detail": "disabled; skipped"}
    started = time.monotonic()
    try:
        from aiokafka import AIOKafkaConsumer  # type: ignore

        kwargs = {
            "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
        }
        if settings.KAFKA_SASL_USERNAME:
            kwargs.update(
                sasl_mechanism=settings.KAFKA_SASL_MECHANISM or "SCRAM-SHA-512",
                sasl_plain_username=settings.KAFKA_SASL_USERNAME,
                sasl_plain_password=settings.KAFKA_SASL_PASSWORD or "",
            )
        consumer = AIOKafkaConsumer(**kwargs)
        await asyncio.wait_for(consumer.start(), timeout=3)
        try:
            topics = await consumer.topics()
        finally:
            await consumer.stop()
        return {
            "status": "ok",
            "topic_count": len(topics),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "status": "fail",
            "detail": str(exc)[:200],
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


async def _probe_hes() -> dict[str, Any]:
    if not settings.HES_ENABLED:
        return {"status": "ok", "detail": "disabled; skipped"}
    started = time.monotonic()
    ok = False
    try:
        ok = await asyncio.wait_for(hes_client.ping(), timeout=settings.HES_READ_TIMEOUT_SECONDS + 1)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": str(exc)[:200],
            "breaker": str(hes_client.breaker.state),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    return {
        "status": "ok" if ok else "fail",
        "breaker": str(hes_client.breaker.state),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


async def _probe_mdms() -> dict[str, Any]:
    if not settings.MDMS_ENABLED:
        return {"status": "ok", "detail": "disabled; skipped"}
    started = time.monotonic()
    try:
        ok = await asyncio.wait_for(mdms_client.ping(), timeout=settings.MDMS_READ_TIMEOUT_SECONDS + 1)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": str(exc)[:200],
            "breaker": str(mdms_client.breaker.state),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    return {
        "status": "ok" if ok else "fail",
        "breaker": str(mdms_client.breaker.state),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


def _roll_up(components: dict[str, dict]) -> str:
    """Map per-component outcomes to the top-level label.

    * DB fail         → fail (EMS cannot serve anything)
    * In strict mode, HES or MDMS fail → fail (SSOT contract)
    * Anything else failing → degraded
    """
    if components["db"]["status"] == "fail":
        return "fail"
    ssot_components = ("hes", "mdms")
    if settings.SSOT_MODE == SSOTMode.strict:
        for key in ssot_components:
            if components.get(key, {}).get("status") == "fail":
                return "fail"
    if any(c.get("status") == "fail" for c in components.values()):
        return "degraded"
    return "ok"


@router.get("/health", include_in_schema=True)
async def health() -> dict[str, Any]:
    """Aggregate upstream health for the frontend banner."""
    db_t, redis_t, kafka_t, hes_t, mdms_t = await asyncio.gather(
        _probe_db(),
        _probe_redis(),
        _probe_kafka(),
        _probe_hes(),
        _probe_mdms(),
    )
    components = {
        "db": db_t,
        "redis": redis_t,
        "kafka": kafka_t,
        "hes": hes_t,
        "mdms": mdms_t,
    }
    overall = _roll_up(components)
    return {
        "overall": overall,
        "ssot_mode": settings.SSOT_MODE.value,
        "deploy_env": settings.DEPLOY_ENV.value,
        "components": components,
    }
