"""aiokafka-based metrology consumer.

Pulls messages from HES Kafka topics, batches them, upserts into
`meter_reading_interval`. Malformed messages go to a DLQ topic.

Trace context is extracted from W3C traceparent headers so spans chain
continuously from HES → Polaris.

NOTE (013-mvp-phase2): full OpenTelemetry instrumentation (per-batch spans +
Prometheus metrics) to be layered on in the observability wave.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.errors import KafkaError
except ImportError:  # pragma: no cover — keeps import safe when dep missing
    AIOKafkaConsumer = None  # type: ignore
    AIOKafkaProducer = None  # type: ignore
    KafkaError = Exception  # type: ignore

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.metrology import MeterReadingInterval

log = logging.getLogger("polaris.metrology.ingest")

SOURCE_PRIORITY = {
    "HES_REST": 10,
    "HES_KAFKA": 20,
    "MDMS_VEE_BACKFILL": 25,
    "MDMS_VEE": 30,
}


@dataclass
class IngestMetrics:
    """Lightweight metrics collector — upgraded to OTel/Prometheus in phase 2."""

    inserted_total: int = 0
    malformed_total: int = 0
    dlq_total: int = 0
    last_commit_ts: Optional[float] = None
    errors: List[str] = field(default_factory=list)


class MetrologyKafkaConsumer:
    """Single-group aiokafka consumer that batches into PG."""

    def __init__(self) -> None:
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._producer: Optional[AIOKafkaProducer] = None
        self._task: Optional[asyncio.Task[Any]] = None
        self._stop = asyncio.Event()
        self.metrics = IngestMetrics()

    async def start(self) -> None:
        if AIOKafkaConsumer is None:
            log.warning("aiokafka not installed; metrology ingest disabled")
            return
        if not settings.METROLOGY_INGEST_ENABLED:
            log.info("METROLOGY_INGEST_ENABLED=false; not starting consumer")
            return

        bootstrap = settings.KAFKA_BOOTSTRAP_SERVERS
        if not bootstrap:
            log.warning("KAFKA_BOOTSTRAP_SERVERS unset; metrology ingest disabled")
            return

        self._consumer = AIOKafkaConsumer(
            *settings.METROLOGY_READING_TOPICS,
            bootstrap_servers=bootstrap,
            group_id=settings.METROLOGY_KAFKA_CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="latest",
            value_deserializer=lambda v: v,  # leave raw; parse in handler
        )
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
        try:
            await self._consumer.start()
            await self._producer.start()
        except KafkaError as exc:
            log.exception("Failed to start Kafka consumer/producer: %s", exc)
            await self._safe_stop()
            return

        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="metrology-kafka-loop")
        log.info(
            "Metrology Kafka consumer started: topics=%s group=%s",
            settings.METROLOGY_READING_TOPICS,
            settings.METROLOGY_KAFKA_CONSUMER_GROUP,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        await self._safe_stop()
        log.info("Metrology Kafka consumer stopped")

    async def _safe_stop(self) -> None:
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:  # pragma: no cover
                log.exception("error stopping consumer")
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:  # pragma: no cover
                log.exception("error stopping producer")
        self._consumer = None
        self._producer = None

    async def _run(self) -> None:
        assert self._consumer is not None
        batch: List[Dict[str, Any]] = []
        last_flush = time.monotonic()
        batch_size = settings.METROLOGY_BATCH_SIZE
        batch_interval = settings.METROLOGY_BATCH_INTERVAL_SECONDS

        while not self._stop.is_set():
            try:
                # Poll with a timeout so we can also honour the batch interval.
                result = await self._consumer.getmany(
                    timeout_ms=int(batch_interval * 1000), max_records=batch_size
                )
                for _tp, messages in result.items():
                    for msg in messages:
                        parsed = self._try_parse(msg)
                        if parsed is None:
                            continue
                        batch.append(parsed)

                now = time.monotonic()
                if batch and (len(batch) >= batch_size or (now - last_flush) >= batch_interval):
                    await self._flush(batch)
                    batch = []
                    last_flush = now
            except asyncio.CancelledError:
                break
            except Exception:  # pragma: no cover — defensive
                log.exception("metrology-ingest loop error")
                await asyncio.sleep(1.0)

        if batch:
            await self._flush(batch)

    # ------------------------------------------------------------------ parsing

    def _try_parse(self, msg: Any) -> Optional[Dict[str, Any]]:
        try:
            raw = msg.value
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            self.metrics.malformed_total += 1
            asyncio.create_task(self._publish_dlq(msg, f"parse_error: {exc}"))
            return None

        # Required fields
        meter_serial = payload.get("meter_serial") or payload.get("meter_id")
        ts_raw = payload.get("timestamp") or payload.get("ts")
        if not meter_serial or not ts_raw:
            self.metrics.malformed_total += 1
            asyncio.create_task(self._publish_dlq(msg, "missing meter_serial or timestamp"))
            return None

        try:
            ts = _parse_ts(ts_raw)
        except Exception as exc:
            self.metrics.malformed_total += 1
            asyncio.create_task(self._publish_dlq(msg, f"bad_timestamp: {exc}"))
            return None

        # Clock-skew guard: reject > 5 min in future.
        now_utc = datetime.now(timezone.utc)
        if (ts - now_utc).total_seconds() > 300:
            self.metrics.malformed_total += 1
            asyncio.create_task(self._publish_dlq(msg, "clock_skew"))
            return None

        # W3C traceparent header (if present)
        trace_id: Optional[str] = None
        try:
            for key, value in msg.headers or []:
                if key == "traceparent" and value:
                    # format: 00-<trace-id 32>-<span-id 16>-<flags>
                    parts = value.decode("utf-8").split("-")
                    if len(parts) >= 3:
                        trace_id = parts[1]
                    break
        except Exception:  # pragma: no cover
            trace_id = None

        source = (payload.get("source") or "HES_KAFKA").upper()
        quality = (payload.get("quality") or "raw").lower()
        if quality not in {"valid", "estimated", "failed", "raw"}:
            quality = "raw"

        energy_kwh = _to_float(payload.get("energy_kwh") or payload.get("energy_import_kwh"))
        return {
            "meter_serial": str(meter_serial),
            "ts": ts,
            "channel": int(payload.get("channel") or 0),
            "value": float(payload.get("value") or energy_kwh or 0.0),
            "quality": quality,
            "source": source,
            "source_priority": SOURCE_PRIORITY.get(source, 10),
            "energy_kwh": energy_kwh,
            "energy_export_kwh": _to_float(payload.get("energy_export_kwh")),
            "demand_kw": _to_float(payload.get("demand_kw")),
            "voltage": _to_float(payload.get("voltage") or payload.get("voltage_v")),
            "current": _to_float(payload.get("current") or payload.get("current_a")),
            "power_factor": _to_float(payload.get("power_factor")),
            "frequency": _to_float(payload.get("frequency") or payload.get("frequency_hz")),
            "thd": _to_float(payload.get("thd") or payload.get("thd_percent")),
            "is_estimated": bool(payload.get("is_estimated") or False),
            "is_validated": bool(payload.get("is_validated") or False),
            "is_edited": bool(payload.get("is_edited") or False),
            "ingested_at": now_utc,
            "trace_id": trace_id,
            "kafka_partition": getattr(msg, "partition", None),
            "kafka_offset": getattr(msg, "offset", None),
        }

    # ---------------------------------------------------------------- flushing

    async def _flush(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        # Run DB work in a thread so we don't block the event loop (sync engine).
        await asyncio.to_thread(self._upsert, rows)
        self.metrics.inserted_total += len(rows)
        self.metrics.last_commit_ts = time.time()
        if self._consumer is not None:
            try:
                await self._consumer.commit()
            except KafkaError:  # pragma: no cover
                log.exception("kafka commit failed")

    def _upsert(self, rows: List[Dict[str, Any]]) -> None:
        session = SessionLocal()
        try:
            stmt = pg_insert(MeterReadingInterval).values(rows)
            # upsert: higher source_priority wins; equal priority overwrites last-write.
            update_cols = {
                c.name: getattr(stmt.excluded, c.name)
                for c in MeterReadingInterval.__table__.columns
                if c.name not in {"meter_serial", "ts", "channel"}
            }
            stmt = stmt.on_conflict_do_update(
                constraint="pk_mri_serial_ts_ch",
                set_=update_cols,
                where=(MeterReadingInterval.source_priority <= stmt.excluded.source_priority),
            )
            session.execute(stmt)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("metrology upsert failed for batch size=%d", len(rows))
            self.metrics.errors.append("upsert_failed")
        finally:
            session.close()

    # ------------------------------------------------------------------- DLQ

    async def _publish_dlq(self, msg: Any, reason: str) -> None:
        self.metrics.dlq_total += 1
        if self._producer is None:
            log.warning("DLQ drop (no producer): reason=%s", reason)
            return
        try:
            payload = {
                "error": reason,
                "topic": getattr(msg, "topic", None),
                "partition": getattr(msg, "partition", None),
                "offset": getattr(msg, "offset", None),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "raw": (
                    msg.value.decode("utf-8", errors="replace")
                    if isinstance(msg.value, (bytes, bytearray))
                    else str(msg.value)
                ),
            }
            await self._producer.send_and_wait(
                settings.METROLOGY_DLQ_TOPIC, json.dumps(payload).encode("utf-8")
            )
        except Exception:
            log.exception("DLQ publish failed")


def _parse_ts(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        # Treat as epoch seconds (or ms if > year-3000).
        val = float(raw)
        if val > 1e12:
            val /= 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(raw, str):
        # Best-effort ISO-8601 parse.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    raise ValueError(f"unsupported timestamp type: {type(raw).__name__}")


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ module API

_consumer_singleton: Optional[MetrologyKafkaConsumer] = None


def get_consumer() -> MetrologyKafkaConsumer:
    global _consumer_singleton
    if _consumer_singleton is None:
        _consumer_singleton = MetrologyKafkaConsumer()
    return _consumer_singleton


async def start_consumer() -> None:
    await get_consumer().start()


async def stop_consumer() -> None:
    global _consumer_singleton
    if _consumer_singleton is not None:
        await _consumer_singleton.stop()
