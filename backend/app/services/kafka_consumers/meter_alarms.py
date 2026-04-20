"""`hesv2.meter.alarms` consumer — spec 018 W2.T3.

Persists an `alarms` row for each meter-level threshold breach emitted by HES.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.base import SessionLocal
from app.models.alarm import Alarm, AlarmSeverity, AlarmStatus, AlarmType
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


# Map HES alarm category strings to our AlarmType enum (fallback to COMM_LOSS
# which is the least-specific meter-level alarm we model today).
_TYPE_MAP = {
    "tamper": AlarmType.TAMPER,
    "cover_open": AlarmType.COVER_OPEN,
    "magnet_tamper": AlarmType.TAMPER,
    "overvoltage": AlarmType.OVERVOLTAGE,
    "undervoltage": AlarmType.UNDERVOLTAGE,
    "overcurrent": AlarmType.OVERCURRENT,
    "reverse_power": AlarmType.REVERSE_POWER,
    "battery_low": AlarmType.BATTERY_LOW,
    "comm_loss": AlarmType.COMM_LOSS,
    "power_failure": AlarmType.OUTAGE,
    "power_restored": AlarmType.POWER_RESTORE,
}

_SEV_MAP = {
    "critical": AlarmSeverity.CRITICAL,
    "high": AlarmSeverity.HIGH,
    "medium": AlarmSeverity.MEDIUM,
    "low": AlarmSeverity.LOW,
    "info": AlarmSeverity.INFO,
}


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise BadPayload(f"bad timestamp: {exc}") from exc
    return datetime.now(timezone.utc)


class MeterAlarmsConsumer(BaseKafkaConsumer):
    topic = "hesv2.meter.alarms"
    group_id = "polaris-ems-alarms"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        meter_serial = payload.get("meter_serial")
        alarm_category = payload.get("alarm_type") or payload.get("event_type")
        if not (meter_serial and alarm_category):
            raise BadPayload("meter_serial + alarm_type required")

        alarm_type = _TYPE_MAP.get(alarm_category, AlarmType.COMM_LOSS)
        severity = _SEV_MAP.get(
            (payload.get("severity") or "medium").lower(), AlarmSeverity.MEDIUM
        )
        triggered_at = _parse_ts(payload.get("timestamp"))

        trace_id = None
        if ctx.traceparent:
            try:
                trace_id = ctx.traceparent.split("-")[1]
            except Exception:
                trace_id = None

        db = SessionLocal()
        try:
            alarm = Alarm(
                alarm_type=alarm_type,
                severity=severity,
                status=AlarmStatus.ACTIVE,
                meter_serial=meter_serial,
                title=payload.get("title") or f"{alarm_category} on {meter_serial}",
                description=payload.get("description"),
                value=payload.get("value"),
                threshold=payload.get("threshold"),
                unit=payload.get("unit"),
                triggered_at=triggered_at,
                source_trace_id=trace_id,
                correlation_group_id=payload.get("correlation_group_id"),
            )
            db.add(alarm)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
