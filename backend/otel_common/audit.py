"""No-op audit publisher for local dev.

Production wires this up to Kafka topic `mdms.audit.actions`; in dev we just log.
Signature intentionally matches `repos/mdms/otel-common-py/otel_common/audit.py`.
"""
import logging
from typing import Any

_log = logging.getLogger("audit")


async def init_audit(service_name: str, **kwargs) -> None:
    _log.info("audit: init_audit(service=%s) [noop shim]", service_name)


async def shutdown_audit() -> None:
    _log.info("audit: shutdown_audit [noop shim]")


async def audit(
    action_type: str,
    action_name: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    request_data: Any = None,
    status: int | None = None,
    method: str | None = None,
    path: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    ip_address: str | None = None,
    changes: Any = None,
    duration_ms: int | None = None,
    service_name: str | None = None,
    **extra: Any,
) -> None:
    _log.info(
        "audit: %s %s on %s/%s by user=%s status=%s [noop shim]",
        action_type, action_name, entity_type, entity_id, user_id, status,
    )
