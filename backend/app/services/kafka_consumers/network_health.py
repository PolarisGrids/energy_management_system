"""`hesv2.network.health` consumer — spec 018 W2.T6.

Upserts one row per DCU into `dcu_health_cache`. Callers read with a 5-minute
TTL filter; the upsert writes `last_reported_at` from the message timestamp
(or now() if absent) so the TTL works correctly under replay.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from app.db.base import SessionLocal
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


_UPSERT_SQL = text(
    """
    INSERT INTO dcu_health_cache
        (dcu_id, status, rssi_dbm, success_rate_pct, retry_count_last_hour,
         meters_connected, last_reported_at, updated_at)
    VALUES
        (:dcu_id, :status, :rssi, :srp, :retries, :meters, :ts, now())
    ON CONFLICT (dcu_id) DO UPDATE SET
        status = EXCLUDED.status,
        rssi_dbm = EXCLUDED.rssi_dbm,
        success_rate_pct = EXCLUDED.success_rate_pct,
        retry_count_last_hour = EXCLUDED.retry_count_last_hour,
        meters_connected = EXCLUDED.meters_connected,
        last_reported_at = EXCLUDED.last_reported_at,
        updated_at = now()
    """
)


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise BadPayload(f"bad timestamp: {exc}") from exc
    return datetime.now(timezone.utc)


def _opt_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BadPayload(f"non-numeric value {value!r}") from exc


class NetworkHealthConsumer(BaseKafkaConsumer):
    topic = "hesv2.network.health"
    group_id = "polaris-ems-comms"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        dcu_id = payload.get("dcu_id")
        status = payload.get("status")
        if not (dcu_id and status):
            raise BadPayload("dcu_id + status required")

        db = SessionLocal()
        try:
            db.execute(
                _UPSERT_SQL,
                {
                    "dcu_id": dcu_id,
                    "status": status,
                    "rssi": _opt_decimal(payload.get("rssi_dbm")),
                    "srp": _opt_decimal(payload.get("success_rate_pct")),
                    "retries": payload.get("retry_count_last_hour"),
                    "meters": payload.get("meters_connected"),
                    "ts": _parse_ts(payload.get("timestamp")),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
