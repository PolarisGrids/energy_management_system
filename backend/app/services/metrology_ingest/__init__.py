"""Metrology ingest package — Kafka consumer + VEE reader + backfill.

See specs/013-metrology-ingest for architecture.
"""
from app.services.metrology_ingest.kafka_consumer import (  # noqa: F401
    MetrologyKafkaConsumer,
    get_consumer,
    start_consumer,
    stop_consumer,
)
