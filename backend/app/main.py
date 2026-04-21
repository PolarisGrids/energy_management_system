import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

try:
    from otel_common.setup import init_otel, shutdown_otel
    from otel_common.logging import configure_logging
    from otel_common.audit import init_audit, shutdown_audit
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    providers = None
    if HAS_OTEL:
        providers = init_otel("polaris-ems", app=app)
        configure_logging("polaris-ems")
        await init_audit("polaris-ems")

    # Spec 018 Wave 2 — register HES Kafka consumers when the flag is on.
    kafka_started = False
    if getattr(settings, "KAFKA_ENABLED", False):
        try:
            from app.services.kafka_consumer import start_all_consumers
            from app.services.kafka_consumers import build_all

            consumers = build_all()
            await start_all_consumers(consumers)
            kafka_started = True
            log.info("kafka consumers started: %d topics", len(consumers))
        except Exception as exc:  # pragma: no cover
            log.error("failed to start kafka consumers: %s", exc)

    # Spec 018 Wave 3 — outage correlator + reliability MV refresh loop.
    # Default on whenever Kafka is on (the input queue is populated by the
    # meter-events consumer). Override with OUTAGE_CORRELATOR_ENABLED=0.
    correlator_task: "asyncio.Task | None" = None
    reliability_task: "asyncio.Task | None" = None
    correlator_stop = asyncio.Event()
    reliability_stop = asyncio.Event()
    if os.getenv("OUTAGE_CORRELATOR_ENABLED", "1") != "0" and getattr(
        settings, "KAFKA_ENABLED", False
    ):
        try:
            from app.services.outage_correlator import run_correlator_loop

            correlator_task = asyncio.create_task(
                run_correlator_loop(correlator_stop), name="outage-correlator"
            )
            log.info("outage correlator started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start outage correlator: %s", exc)

    if os.getenv("RELIABILITY_SCHEDULER_ENABLED", "1") != "0":
        try:
            from app.services.reliability_calc import run_refresh_scheduler

            reliability_task = asyncio.create_task(
                run_refresh_scheduler(reliability_stop), name="reliability-refresh"
            )
            log.info("reliability scheduler started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start reliability scheduler: %s", exc)

    # Spec 018 W4.T10 — scheduled EGSM-report worker (APScheduler).
    scheduled_reports_started = False
    if getattr(settings, "SCHEDULED_REPORTS_ENABLED", False) and os.getenv(
        "SCHEDULED_REPORTS_WORKER_ENABLED", "1"
    ) != "0":
        try:
            from app.services import scheduled_report_worker

            await scheduled_report_worker.start()
            scheduled_reports_started = True
            log.info("scheduled-report worker started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start scheduled-report worker: %s", exc)

    # Spec 018 W4.T14 — Data Accuracy source_status refresher (every 5 min).
    source_status_task: "asyncio.Task | None" = None
    source_status_stop = asyncio.Event()
    if os.getenv("SOURCE_STATUS_REFRESHER_ENABLED", "1") != "0":
        try:
            from app.services.source_status_refresher import run_refresher_loop

            interval = int(os.getenv("SOURCE_STATUS_INTERVAL_SECONDS", "300"))
            source_status_task = asyncio.create_task(
                run_refresher_loop(source_status_stop, interval_seconds=interval),
                name="source-status-refresher",
            )
            log.info("source_status refresher started (interval=%ds)", interval)
        except Exception as exc:  # pragma: no cover
            log.error("failed to start source_status refresher: %s", exc)

    # Spec 018 W3.T13 — reverse-flow detector on der_telemetry.
    reverse_flow_started = False
    if os.getenv("REVERSE_FLOW_DETECTOR_ENABLED", "1") != "0":
        try:
            from app.services.reverse_flow_detector import detector as reverse_flow_detector

            await reverse_flow_detector.start()
            reverse_flow_started = True
            log.info("reverse-flow detector started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start reverse-flow detector: %s", exc)

    # DER realtime simulator — back-fills history then ticks every 5 min.
    der_sim_task: "asyncio.Task | None" = None
    der_sim_stop = asyncio.Event()
    if os.getenv("DER_SIM_ENABLED", "1") != "0":
        try:
            from app.services.der_sim import run_sim_loop

            der_sim_task = asyncio.create_task(
                run_sim_loop(der_sim_stop), name="der-sim"
            )
            log.info("der_sim started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start der_sim: %s", exc)

    # Theft-analysis scorer — refreshes theft_score rows from MDMS every 15 min.
    # Requires MDMS_VALIDATION_DB_URL; when unset the scorer no-ops gracefully.
    theft_task: "asyncio.Task | None" = None
    theft_stop = asyncio.Event()
    if os.getenv("THEFT_SCORER_ENABLED", "1") != "0":
        try:
            from app.services.theft_analysis.runner import run_refresh_loop

            theft_task = asyncio.create_task(
                run_refresh_loop(theft_stop), name="theft-scorer"
            )
            log.info("theft scorer started")
        except Exception as exc:  # pragma: no cover
            log.error("failed to start theft scorer: %s", exc)

    try:
        yield
    finally:
        # ── Shutdown — proxy clients first (httpx pools), then kafka, then audit + otel.
        try:
            from app.api.v1.endpoints._proxy_common import shutdown_proxy_clients
            await shutdown_proxy_clients()
        except Exception:
            pass

        # Stop Wave-3 background tasks before Kafka so the correlator drains.
        for task, stop_ev, name in (
            (correlator_task, correlator_stop, "outage-correlator"),
            (reliability_task, reliability_stop, "reliability-refresh"),
            (source_status_task, source_status_stop, "source-status-refresher"),
            (der_sim_task, der_sim_stop, "der-sim"),
            (theft_task, theft_stop, "theft-scorer"),
        ):
            if task is None:
                continue
            stop_ev.set()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except Exception as exc:  # pragma: no cover
                log.warning("failed to stop %s: %s", name, exc)

        if reverse_flow_started:
            try:
                from app.services.reverse_flow_detector import detector as reverse_flow_detector
                await reverse_flow_detector.stop()
            except Exception as exc:  # pragma: no cover
                log.error("failed to stop reverse-flow detector: %s", exc)

        if scheduled_reports_started:
            try:
                from app.services import scheduled_report_worker
                await scheduled_report_worker.stop()
            except Exception as exc:  # pragma: no cover
                log.error("failed to stop scheduled-report worker: %s", exc)

        if kafka_started:
            try:
                from app.services.kafka_consumer import stop_all_consumers
                await stop_all_consumers()
            except Exception as exc:  # pragma: no cover
                log.error("failed to stop kafka consumers: %s", exc)

        if HAS_OTEL and providers:
            await shutdown_audit()
            shutdown_otel(*providers)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.APP_NAME}
