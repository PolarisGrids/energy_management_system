"""`hesv2.sensor.readings` consumer — spec 018 W2.T5.

Persists one row per transformer / distribution-room sensor tick into the
monthly-partitioned `transformer_sensor_reading` table via raw SQL (keeps this
module independent of the parallel W2B `TransformerSensorReading` ORM model).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from app.db.base import SessionLocal
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise BadPayload(f"bad timestamp: {exc}") from exc
    return datetime.now(timezone.utc)


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BadPayload(f"value not numeric: {value!r}") from exc


_INSERT_SQL = text(
    """
    INSERT INTO transformer_sensor_reading
        (sensor_id, dtr_id, type, value, unit, breach_flag, threshold_max, ts)
    VALUES
        (:sensor_id, :dtr_id, :type, :value, :unit, :breach_flag, :threshold_max, :ts)
    """
)


class SensorReadingsConsumer(BaseKafkaConsumer):
    topic = "hesv2.sensor.readings"
    group_id = "polaris-ems-sensors"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        sensor_id = payload.get("sensor_id")
        sensor_type = payload.get("type")
        if not (sensor_id and sensor_type):
            raise BadPayload("sensor_id + type required")
        if "value" not in payload:
            raise BadPayload("value required")

        value = _decimal(payload["value"])
        threshold_max = (
            _decimal(payload["threshold_max"])
            if payload.get("threshold_max") is not None
            else None
        )

        db = SessionLocal()
        try:
            db.execute(
                _INSERT_SQL,
                {
                    "sensor_id": sensor_id,
                    "dtr_id": payload.get("dtr_id"),
                    "type": sensor_type,
                    "value": value,
                    "unit": payload.get("unit"),
                    "breach_flag": bool(payload.get("breach_flag", False)),
                    "threshold_max": threshold_max,
                    "ts": _parse_ts(payload.get("timestamp")),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
