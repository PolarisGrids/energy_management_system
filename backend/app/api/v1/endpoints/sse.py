import asyncio
import json
import logging
import warnings
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.core.config import settings
from app.models.alarm import Alarm, AlarmStatus
from app.models.meter import Meter, MeterStatus
from app.models.simulation import SimulationScenario, ScenarioStatus

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── Deprecation tracking for legacy `?token=` auth ──────────────────────────
# Header auth is the primary path; `?token=` remains as a transitional
# backward-compat fallback. Target removal: Wave 1 (spec 018, W1).
#
# We surface usage two ways so it's visible in both Prometheus (via OTel
# meter) and operator logs:
#   1. OTel Counter `sse_query_token_requests_total` when OTel is wired.
#   2. Module-level int fallback (+ log.warning) when OTel is not available
#      (e.g. local dev without otel-common-py).

_sse_query_token_requests_total: int = 0
_otel_sse_query_token_counter = None

try:  # Best-effort OTel meter wiring — never fail the request path.
    from opentelemetry import metrics as _otel_metrics  # type: ignore

    _otel_sse_query_token_counter = _otel_metrics.get_meter(
        "polaris-ems.sse"
    ).create_counter(
        name="sse_query_token_requests_total",
        description=(
            "Count of SSE /events/stream requests that used the deprecated "
            "`?token=` query-string auth fallback. Target removal: Wave 1."
        ),
        unit="1",
    )
except Exception:  # pragma: no cover - OTel optional
    _otel_sse_query_token_counter = None


def _record_legacy_token_usage(request: Request) -> None:
    """Emit DeprecationWarning, bump counter, and log when `?token=` is used."""
    global _sse_query_token_requests_total
    _sse_query_token_requests_total += 1

    if _otel_sse_query_token_counter is not None:
        try:
            _otel_sse_query_token_counter.add(
                1,
                {
                    "endpoint": "/events/stream",
                    "client": request.client.host if request.client else "unknown",
                },
            )
        except Exception:
            pass  # never let telemetry break SSE

    warnings.warn(
        "SSE `?token=` query-string auth is deprecated; use the "
        "`Authorization: Bearer <token>` header instead. Query-string "
        "auth will be removed in Wave 1.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "sse.deprecated_query_token",
        extra={
            "endpoint": "/events/stream",
            "client_ip": request.client.host if request.client else None,
            "count": _sse_query_token_requests_total,
        },
    )


async def event_generator(request: Request):
    """Stream real-time events to connected clients via SSE."""
    last_alarm_id = 0
    tick = 0

    while True:
        if await request.is_disconnected():
            break

        db: Session = SessionLocal()
        try:
            events = []

            # New alarms since last poll
            new_alarms = (
                db.query(Alarm)
                .filter(Alarm.id > last_alarm_id, Alarm.status == AlarmStatus.ACTIVE)
                .order_by(Alarm.id)
                .limit(10)
                .all()
            )
            for alarm in new_alarms:
                last_alarm_id = alarm.id
                events.append({
                    "type": "alarm",
                    "data": {
                        "id": alarm.id,
                        "alarm_type": alarm.alarm_type,
                        "severity": alarm.severity,
                        "title": alarm.title,
                        "meter_serial": alarm.meter_serial,
                        "latitude": alarm.latitude,
                        "longitude": alarm.longitude,
                        "triggered_at": alarm.triggered_at.isoformat(),
                    }
                })

            # Network health snapshot every 10 ticks
            if tick % 10 == 0:
                total = db.query(Meter).count()
                online = db.query(Meter).filter(Meter.status == MeterStatus.ONLINE).count()
                active_alarms = db.query(Alarm).filter(Alarm.status == AlarmStatus.ACTIVE).count()
                events.append({
                    "type": "network_health",
                    "data": {
                        "total_meters": total,
                        "online_meters": online,
                        "comm_success_rate": round(online / total * 100, 1) if total > 0 else 0,
                        "active_alarms": active_alarms,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                })

            # Running simulation step updates
            running = db.query(SimulationScenario).filter(
                SimulationScenario.status == ScenarioStatus.RUNNING
            ).all()
            for s in running:
                events.append({
                    "type": "simulation_update",
                    "data": {
                        "scenario_id": s.id,
                        "scenario_type": s.scenario_type,
                        "current_step": s.current_step,
                        "total_steps": s.total_steps,
                        "status": s.status,
                    }
                })

            for event in events:
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"]),
                }

            # Heartbeat
            yield {
                "event": "heartbeat",
                "data": json.dumps({"ts": datetime.now(timezone.utc).isoformat()}),
            }

        finally:
            db.close()

        tick += 1
        await asyncio.sleep(settings.SSE_HEARTBEAT_INTERVAL)


@router.get("/stream")
async def stream_events(request: Request):
    # Deprecated `?token=` auth — header path is primary. Keep fallback
    # working; target removal: Wave 1 (see W0.T8 / W1 follow-up).
    if "token" in request.query_params:
        _record_legacy_token_usage(request)
    return EventSourceResponse(event_generator(request))


@router.get("/stream/metrics")
def stream_deprecation_metrics():
    """Expose the legacy-token counter for diagnostic scraping.

    Prometheus should prefer the OTel-exported `sse_query_token_requests_total`
    series. This endpoint is a fallback for environments where OTel is not
    wired (local dev, bare Docker Compose).
    """
    return {
        "sse_query_token_requests_total": _sse_query_token_requests_total,
        "otel_exported": _otel_sse_query_token_counter is not None,
    }
