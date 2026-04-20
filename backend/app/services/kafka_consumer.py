"""
Kafka consumer base class — spec 018 Wave 2 T1.

Wraps aiokafka.AIOKafkaConsumer with:
* SASL/SCRAM (or PLAINTEXT) auth sourced from settings
* W3C TraceContext header extraction (per otel-common-py `extract_context`)
* At-least-once delivery — commit only after on_message succeeds
* DLQ publish on JSON decode / schema validation failure
* Prometheus counter ems_kafka_messages_consumed_total{topic,status}

Subclasses override `topic`, `group_id`, `on_message(ctx, payload)`. Register
them at startup via `register_consumers(loop)` which is invoked from
`backend/app/main.py` lifespan when KAFKA_ENABLED is true.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

try:  # pragma: no cover — aiokafka present in requirements.txt
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.errors import KafkaError
    HAS_AIOKAFKA = True
except ImportError:  # pragma: no cover
    AIOKafkaConsumer = None  # type: ignore[assignment]
    AIOKafkaProducer = None  # type: ignore[assignment]
    HAS_AIOKAFKA = False

    class KafkaError(Exception):  # type: ignore[no-redef]
        pass

try:  # pragma: no cover
    from prometheus_client import Counter
    CONSUMED = Counter(
        "ems_kafka_messages_consumed_total",
        "Kafka messages consumed by the EMS backend",
        ["topic", "status"],
    )
    DLQ = Counter(
        "ems_kafka_dlq_messages_total",
        "Kafka messages routed to DLQ",
        ["topic"],
    )
    HAS_PROM = True
except ImportError:  # pragma: no cover

    class _N:
        def labels(self, **_):
            return self

        def inc(self, *_a, **_k):
            pass

    CONSUMED = _N()  # type: ignore[assignment]
    DLQ = _N()  # type: ignore[assignment]
    HAS_PROM = False


try:  # propagation
    from opentelemetry.propagate import extract as otel_extract
    from opentelemetry import trace as otel_trace

    def _ctx_from_headers(headers: Iterable) -> Any:
        carrier: Dict[str, str] = {}
        for k, v in headers or []:
            try:
                carrier[k] = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
            except Exception:
                continue
        return otel_extract(carrier)

    def _start_span(name: str, ctx):
        tracer = otel_trace.get_tracer("polaris-ems.kafka")
        return tracer.start_as_current_span(name, context=ctx)

except ImportError:  # pragma: no cover

    def _ctx_from_headers(_headers):  # type: ignore[return-value]
        return None

    class _NoopSpanCM:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _start_span(_name, _ctx):  # type: ignore[return-value]
        return _NoopSpanCM()


from app.core.config import settings

log = logging.getLogger(__name__)


class BadPayload(Exception):
    """Raised by subclasses when the deserialised message fails validation."""


@dataclass
class ConsumerContext:
    """Passed to on_message; carries metadata about the delivered record."""
    topic: str
    partition: int
    offset: int
    key: Optional[str]
    headers: Dict[str, str]
    traceparent: Optional[str]


class BaseKafkaConsumer:
    """Subclass and set `topic` + `group_id`; override `on_message()`.

    One instance = one consumer task.  Call `start()` to begin, `stop()` to
    drain + close.  At-least-once semantics: the offset is committed only
    after on_message returns without raising.
    """

    topic: str = ""
    group_id: str = ""
    # When True, a malformed JSON payload is sent to `{topic}.dlq`; when False
    # it is simply counted and skipped.
    dlq_enabled: bool = True

    def __init__(self) -> None:
        if not self.topic or not self.group_id:
            raise ValueError("Subclass must set topic and group_id")
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._producer: Optional[AIOKafkaProducer] = None  # DLQ + trace propagation
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    # ─── aiokafka plumbing ────────────────────────────────────────────────

    def _build_client_kwargs(self) -> dict:
        kw: dict = dict(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            security_protocol=settings.KAFKA_SECURITY_PROTOCOL,
        )
        if settings.KAFKA_SASL_MECHANISM:
            kw["sasl_mechanism"] = settings.KAFKA_SASL_MECHANISM
            kw["sasl_plain_username"] = settings.KAFKA_SASL_USERNAME
            kw["sasl_plain_password"] = settings.KAFKA_SASL_PASSWORD
            # SASL_SSL implies TLS — provide a default context so aiokafka
            # doesn't force users to configure one manually in dev/prod.
            if "SSL" in (settings.KAFKA_SECURITY_PROTOCOL or ""):
                kw["ssl_context"] = ssl.create_default_context()
        return kw

    async def _ensure_producer(self) -> AIOKafkaProducer:
        if self._producer is None and HAS_AIOKAFKA:
            self._producer = AIOKafkaProducer(**self._build_client_kwargs())
            await self._producer.start()
        return self._producer  # type: ignore[return-value]

    async def _dlq(self, raw: bytes, reason: str) -> None:
        if not self.dlq_enabled:
            return
        DLQ.labels(topic=self.topic).inc()
        if not HAS_AIOKAFKA:
            log.warning("DLQ skipped (aiokafka missing): topic=%s reason=%s", self.topic, reason)
            return
        try:
            prod = await self._ensure_producer()
            await prod.send_and_wait(
                f"{self.topic}.dlq",
                raw,
                headers=[("reason", reason.encode())],
            )
        except Exception as exc:  # pragma: no cover — DLQ failure must not crash consumer
            log.error("DLQ publish failed topic=%s reason=%s err=%s", self.topic, reason, exc)

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not HAS_AIOKAFKA:
            log.warning("aiokafka missing — consumer %s not started", self.topic)
            return
        self._consumer = AIOKafkaConsumer(
            self.topic,
            group_id=self.group_id,
            enable_auto_commit=False,           # at-least-once
            auto_offset_reset="latest",
            **self._build_client_kwargs(),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._run(), name=f"kafka-{self.topic}")
        log.info("kafka consumer started topic=%s group=%s", self.topic, self.group_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._consumer:
            try:
                await self._consumer.stop()
            except Exception:
                pass
        if self._producer:
            try:
                await self._producer.stop()
            except Exception:
                pass
        log.info("kafka consumer stopped topic=%s", self.topic)

    async def _run(self) -> None:
        assert self._consumer is not None
        async for msg in self._consumer:
            if self._stop.is_set():
                break
            await self._handle(msg)

    async def _handle(self, msg) -> None:
        # 1) Decode
        try:
            payload = json.loads(msg.value.decode()) if msg.value else {}
        except Exception:
            log.warning("bad JSON topic=%s offset=%s", self.topic, msg.offset)
            CONSUMED.labels(topic=self.topic, status="bad_payload").inc()
            await self._dlq(msg.value or b"", "json-decode-failed")
            await self._commit(msg)
            return

        # 2) Propagate W3C trace context
        headers = {
            k: (v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
            for k, v in (msg.headers or [])
        }
        ctx = _ctx_from_headers(msg.headers or [])
        traceparent = headers.get("traceparent") or payload.get("traceparent")

        consumer_ctx = ConsumerContext(
            topic=msg.topic,
            partition=msg.partition,
            offset=msg.offset,
            key=msg.key.decode() if msg.key else None,
            headers=headers,
            traceparent=traceparent,
        )

        # 3) Dispatch inside a span tied to the producer's trace
        with _start_span(f"kafka.consume.{self.topic}", ctx):
            try:
                await self.on_message(consumer_ctx, payload)
                CONSUMED.labels(topic=self.topic, status="ok").inc()
            except BadPayload as exc:
                log.warning("bad payload topic=%s reason=%s", self.topic, exc)
                CONSUMED.labels(topic=self.topic, status="bad_payload").inc()
                await self._dlq(msg.value or b"", f"bad-payload:{exc}")
            except Exception as exc:
                # Transient failures: do NOT commit — consumer will retry on next poll.
                CONSUMED.labels(topic=self.topic, status="error").inc()
                log.exception("consumer error topic=%s err=%s", self.topic, exc)
                return  # skip commit
        await self._commit(msg)

    async def _commit(self, msg) -> None:
        try:
            assert self._consumer is not None
            await self._consumer.commit()
        except Exception:  # pragma: no cover
            log.debug("commit failed topic=%s offset=%s", msg.topic, msg.offset)

    # ─── subclass hook ────────────────────────────────────────────────────

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        raise NotImplementedError


# ─── registry ────────────────────────────────────────────────────────────

_RUNNING: List[BaseKafkaConsumer] = []


async def start_all_consumers(consumers: Iterable[BaseKafkaConsumer]) -> None:
    """Start every consumer in parallel; idempotent (skips if already running)."""
    if _RUNNING:
        return
    tasks = []
    for c in consumers:
        _RUNNING.append(c)
        tasks.append(asyncio.create_task(c.start()))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def stop_all_consumers() -> None:
    if not _RUNNING:
        return
    await asyncio.gather(*(c.stop() for c in _RUNNING), return_exceptions=True)
    _RUNNING.clear()


__all__ = [
    "BaseKafkaConsumer",
    "BadPayload",
    "ConsumerContext",
    "start_all_consumers",
    "stop_all_consumers",
]
