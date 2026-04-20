"""Per-topic Kafka consumers — spec 018 Wave 2.

Each submodule defines one subclass of `BaseKafkaConsumer`. The `build_all()`
factory returns the full consumer list for registration in main.lifespan.
"""
from __future__ import annotations

from typing import List

from app.services.kafka_consumer import BaseKafkaConsumer


def build_all() -> List[BaseKafkaConsumer]:
    from .meter_events import MeterEventsConsumer
    from .meter_alarms import MeterAlarmsConsumer
    from .command_status import CommandStatusConsumer
    from .sensor_readings import SensorReadingsConsumer
    from .network_health import NetworkHealthConsumer
    from .der_telemetry import DerTelemetryConsumer
    return [
        MeterEventsConsumer(),
        MeterAlarmsConsumer(),
        CommandStatusConsumer(),
        SensorReadingsConsumer(),
        NetworkHealthConsumer(),
        DerTelemetryConsumer(),
    ]


__all__ = ["build_all"]
