"""`hesv2.der.telemetry` consumer — spec 018 W2.T7.

Inserts per-interval telemetry (active/reactive power, SoC, session energy,
achievement rate, curtailment) into the weekly-partitioned `der_telemetry`
table. Raw SQL keeps us decoupled from the sibling W2B `DERCommand` /
`DERAssetEMS` ORM models.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from app.db.base import SessionLocal
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


_INSERT_SQL = text(
    """
    INSERT INTO der_telemetry
        (asset_id, ts, state, active_power_kw, reactive_power_kvar,
         soc_pct, session_energy_kwh, achievement_rate_pct, curtailment_pct)
    VALUES
        (:asset_id, :ts, :state, :ap, :rp, :soc, :se, :ar, :cp)
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


class DerTelemetryConsumer(BaseKafkaConsumer):
    topic = "hesv2.der.telemetry"
    group_id = "polaris-ems-der"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        asset_id = payload.get("asset_id")
        if not asset_id:
            raise BadPayload("asset_id required")

        db = SessionLocal()
        try:
            db.execute(
                _INSERT_SQL,
                {
                    "asset_id": asset_id,
                    "ts": _parse_ts(payload.get("timestamp")),
                    "state": payload.get("state"),
                    "ap": _opt_decimal(payload.get("active_power_kw")),
                    "rp": _opt_decimal(payload.get("reactive_power_kvar")),
                    "soc": _opt_decimal(payload.get("soc_pct")),
                    "se": _opt_decimal(payload.get("session_energy_kwh")),
                    "ar": _opt_decimal(payload.get("achievement_rate_pct")),
                    "cp": _opt_decimal(payload.get("curtailment_pct")),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
