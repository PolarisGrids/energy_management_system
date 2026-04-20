"""`hesv2.command.status` consumer — spec 018 W2.T4.

Lifecycle: QUEUED → ACK → EXECUTED → CONFIRMED | FAILED | TIMEOUT.

On CONFIRMED for a DISCONNECT / CONNECT command we also flip
`meter.relay_state` and stamp `meter.last_command_id`.

`command_log` is owned by the sibling W2B stream (same spec 018, commit
pending). To keep this consumer independent of their model import we use
plain SQL `UPDATE`s — the table shape is frozen by contract in
`data-model.md` and mirrored in W2B's migration (`w2b1_cmdlog_fota_der`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from app.db.base import SessionLocal
from app.models.meter import Meter, MeterStatus, RelayState
from app.services.kafka_consumer import BadPayload, BaseKafkaConsumer, ConsumerContext


_TERMINAL = {"CONFIRMED", "FAILED", "TIMEOUT"}


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:
            raise BadPayload(f"bad timestamp: {exc}") from exc
    return datetime.now(timezone.utc)


class CommandStatusConsumer(BaseKafkaConsumer):
    topic = "hesv2.command.status"
    group_id = "polaris-ems-commands"

    async def on_message(self, ctx: ConsumerContext, payload: dict) -> None:
        command_id = payload.get("command_id")
        status = (payload.get("status") or "").upper()
        meter_serial = payload.get("meter_serial")
        if not (command_id and status):
            raise BadPayload("command_id + status required")

        now = _parse_ts(payload.get("timestamp"))
        response_payload = payload.get("response_payload") or {}

        db = SessionLocal()
        try:
            # 1) Update the command_log row (the insert happens in the
            #    outbound-command endpoint; see W2B `endpoints/meters.py`).
            params = {
                "cid": command_id,
                "status": status,
                "now": now,
                "resp": json.dumps(response_payload),
            }

            update_sql = """
                UPDATE command_log
                   SET status = :status,
                       response_payload = CAST(:resp AS JSONB),
                       acked_at = CASE
                           WHEN :status = 'ACK' AND acked_at IS NULL THEN :now
                           ELSE acked_at
                       END,
                       confirmed_at = CASE
                           WHEN :status IN ('CONFIRMED', 'FAILED', 'TIMEOUT')
                                AND confirmed_at IS NULL THEN :now
                           ELSE confirmed_at
                       END
                 WHERE id = :cid
            """
            db.execute(text(update_sql), params)

            # 2) On CONFIRMED flip relay_state for DISCONNECT / CONNECT commands.
            if status == "CONFIRMED" and meter_serial:
                meter = db.query(Meter).filter(Meter.serial == meter_serial).first()
                if meter is not None:
                    # Look up the command type from command_log so we know
                    # whether to open or close the relay.
                    row = db.execute(
                        text(
                            "SELECT command_type FROM command_log WHERE id = :cid"
                        ),
                        {"cid": command_id},
                    ).fetchone()
                    cmd_type = row[0] if row else None
                    if cmd_type:
                        if cmd_type.upper() in {"DISCONNECT", "RC_DC_DISCONNECT"}:
                            meter.relay_state = RelayState.DISCONNECTED
                            meter.status = MeterStatus.DISCONNECTED
                        elif cmd_type.upper() in {"CONNECT", "RC_DC_CONNECT"}:
                            meter.relay_state = RelayState.CONNECTED
                            meter.status = MeterStatus.ONLINE
                    meter.last_command_id = command_id

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
