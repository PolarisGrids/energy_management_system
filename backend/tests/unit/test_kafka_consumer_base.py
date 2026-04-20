"""Unit tests for the Kafka consumer base class (W2.T1).

We verify decode / DLQ / at-least-once behaviour without a real Kafka broker
by driving the `_handle` method directly with lightweight record stubs.
Integration test against a real broker is in
tests/integration/test_kafka_integration.py (marker `requires_kafka`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List

import pytest

from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


@dataclass
class FakeRecord:
    topic: str = "test.topic"
    partition: int = 0
    offset: int = 0
    key: bytes | None = None
    value: bytes | None = b"{}"
    headers: list[tuple[str, bytes]] | None = None


class _DummyConsumer(BaseKafkaConsumer):
    topic = "test.topic"
    group_id = "test-group"

    def __init__(self):
        super().__init__()
        self.handled: List[tuple[ConsumerContext, dict]] = []
        self.raises: Exception | None = None
        self.committed: int = 0
        self.dlq_calls: List[tuple[bytes, str]] = []

    async def on_message(self, ctx, payload):
        if self.raises:
            raise self.raises
        self.handled.append((ctx, payload))

    # Stub out broker-side ops
    async def _commit(self, msg):
        self.committed += 1

    async def _dlq(self, raw, reason):
        self.dlq_calls.append((raw, reason))


@pytest.mark.asyncio
async def test_handle_ok_path_invokes_on_message_and_commits():
    c = _DummyConsumer()
    rec = FakeRecord(value=json.dumps({"hello": "world"}).encode())
    await c._handle(rec)
    assert len(c.handled) == 1
    ctx, payload = c.handled[0]
    assert payload == {"hello": "world"}
    assert ctx.topic == "test.topic"
    assert c.committed == 1
    assert c.dlq_calls == []


@pytest.mark.asyncio
async def test_handle_bad_json_routes_to_dlq_and_commits():
    c = _DummyConsumer()
    rec = FakeRecord(value=b"not-valid-json{{{")
    await c._handle(rec)
    assert c.handled == []
    assert len(c.dlq_calls) == 1
    raw, reason = c.dlq_calls[0]
    assert reason == "json-decode-failed"
    # bad-payload is considered consumed (poison-pill shouldn't block)
    assert c.committed == 1


@pytest.mark.asyncio
async def test_handle_bad_payload_exception_routes_to_dlq():
    c = _DummyConsumer()
    c.raises = BadPayload("missing meter_serial")
    rec = FakeRecord(value=json.dumps({"foo": 1}).encode())
    await c._handle(rec)
    assert len(c.dlq_calls) == 1
    assert c.dlq_calls[0][1].startswith("bad-payload:")
    assert c.committed == 1


@pytest.mark.asyncio
async def test_handle_transient_error_skips_commit_for_retry():
    c = _DummyConsumer()
    c.raises = RuntimeError("db unavailable")
    rec = FakeRecord(value=json.dumps({"ok": True}).encode())
    await c._handle(rec)
    # Transient exceptions must NOT commit so the record is reprocessed.
    assert c.committed == 0
    assert c.dlq_calls == []


@pytest.mark.asyncio
async def test_traceparent_extraction_from_headers():
    c = _DummyConsumer()
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    rec = FakeRecord(
        value=json.dumps({}).encode(),
        headers=[("traceparent", tp.encode())],
    )
    await c._handle(rec)
    assert c.handled[0][0].traceparent == tp


def test_subclass_without_topic_raises():
    class Bad(BaseKafkaConsumer):
        topic = ""
        group_id = ""

    with pytest.raises(ValueError):
        Bad()
