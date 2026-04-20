"""`hesv2.meter.events` consumer — spec 018 W2.T2.

Persists every event in `meter_event_log`; on power_failure / power_restored
additionally enqueues into `outage_correlator_input` for the Wave-3 correlator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.base import SessionLocal
from app.models.meter_event import MeterEventLog, OutageCorrelatorInput
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


_OUTAGE_EVENT_TYPES = {"power_failure", "power_restored"}


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # fromisoformat accepts +HH:MM offsets (Python 3.11+)
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise BadPayload(f"bad timestamp {value!r}: {exc}") from exc
    raise BadPayload(f"missing/invalid timestamp: {value!r}")


class MeterEventsConsumer(BaseKafkaConsumer):
    topic = "hesv2.meter.events"
    group_id = "polaris-ems-events"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        event_id = payload.get("event_id")
        meter_serial = payload.get("meter_serial")
        event_type = payload.get("event_type")
        if not (event_id and meter_serial and event_type):
            raise BadPayload("event_id / meter_serial / event_type required")

        ts = _parse_ts(payload.get("timestamp") or datetime.now(timezone.utc))

        trace_id = None
        if ctx.traceparent:
            try:
                trace_id = ctx.traceparent.split("-")[1]  # W3C: version-traceid-spanid-flags
            except Exception:
                trace_id = None

        db = SessionLocal()
        try:
            # Idempotent insert — event_id is unique; on retry we just skip.
            existing = (
                db.query(MeterEventLog).filter(MeterEventLog.event_id == event_id).first()
            )
            if existing is None:
                row = MeterEventLog(
                    event_id=event_id,
                    meter_serial=meter_serial,
                    event_type=event_type,
                    dlms_event_code=payload.get("dlms_event_code"),
                    dcu_id=payload.get("dcu_id"),
                    event_ts=ts,
                    source_trace_id=trace_id,
                    raw_payload=json.dumps(payload)[:4096],
                )
                db.add(row)

            if event_type in _OUTAGE_EVENT_TYPES:
                db.add(
                    OutageCorrelatorInput(
                        meter_serial=meter_serial,
                        dtr_id=payload.get("dtr_id"),
                        event_type=event_type,
                        event_ts=ts,
                        source_trace_id=trace_id,
                    )
                )

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
