"""End-to-end Kafka consumer integration test — spec 018 Wave 2.

Spins up a Kafka broker via testcontainers, publishes a synthetic
`hesv2.meter.events` message, and asserts that a subclass-defined
`on_message` receives the payload within the poll budget.

Marked `requires_kafka`; skipped automatically in environments where
testcontainers / docker aren't available (CI without privileged runners).
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

pytestmark = [pytest.mark.requires_kafka]

testcontainers = pytest.importorskip("testcontainers.kafka")
aiokafka = pytest.importorskip("aiokafka")


@pytest.fixture(scope="module")
def kafka_container():  # pragma: no cover — infra-bound
    from testcontainers.kafka import KafkaContainer

    with KafkaContainer("confluentinc/cp-kafka:7.6.1") as kafka:
        yield kafka


@pytest.mark.asyncio
async def test_meter_events_consumer_receives_message(kafka_container, monkeypatch):  # pragma: no cover
    """Publish one event, let the consumer drain it, and assert on_message ran."""
    from app.services.kafka_consumer import BaseKafkaConsumer

    bootstrap = kafka_container.get_bootstrap_server()

    # Drive a minimal subclass so we stay decoupled from DB infra.
    received: list[dict] = []

    class _TestConsumer(BaseKafkaConsumer):
        topic = "hesv2.meter.events"
        group_id = "test-group"

        async def on_message(self, ctx, payload):
            received.append(payload)

    # Patch settings so the consumer uses the container's bootstrap.
    from app.core import config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "KAFKA_BOOTSTRAP_SERVERS", bootstrap)
    monkeypatch.setattr(cfg_mod.settings, "KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setattr(cfg_mod.settings, "KAFKA_SASL_MECHANISM", None)

    consumer = _TestConsumer()
    await consumer.start()

    # Publisher
    producer = aiokafka.AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    try:
        payload = {
            "event_id": "evt-1",
            "meter_serial": "S-001",
            "event_type": "power_failure",
            "timestamp": "2026-04-18T12:00:00+05:30",
        }
        await producer.send_and_wait("hesv2.meter.events", json.dumps(payload).encode())
    finally:
        await producer.stop()

    # Drain — poll for up to 10 s.
    for _ in range(20):
        if received:
            break
        await asyncio.sleep(0.5)
    await consumer.stop()

    assert received, "consumer did not receive the published message"
    assert received[0]["event_id"] == "evt-1"
