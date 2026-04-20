"""Centralised audit helper — spec 018 W2.T13.

All write endpoints in `backend/app/api/v1/endpoints/` should call
`publish_audit()` after the mutation commits. The helper is a thin wrapper
over `otel_common.audit.audit` (which publishes to Kafka topic
`mdms.audit.actions` asynchronously) and falls back to a no-op when the
`otel_common` package isn't installed (local dev without Kafka).

Mandatory fields per the MDMS `action_audit_log` schema:

    service_name    — always `polaris-ems`
    action_type     — READ | WRITE | DELETE
    action_name     — verb_object, snake_case (e.g. acknowledge_alarm)
    entity_type     — model class name (e.g. Alarm, Meter)
    entity_id       — str(pk)
    method          — HTTP method
    path            — request path
    response_status — HTTP status code
    user_id         — str(current_user.id) or None
    duration_ms     — optional; caller-supplied if available
    trace_id        — auto-injected by otel-common-py from current span

`request_data` is best-effort — `pydantic.BaseModel.model_dump()` is
preferred; raw dicts are passed through. The audit writer truncates
payloads > 8 KiB.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

try:
    from otel_common.audit import audit as _otel_audit  # type: ignore
    HAS_OTEL_AUDIT = True
except ImportError:  # pragma: no cover
    HAS_OTEL_AUDIT = False

    async def _otel_audit(**_kwargs):
        return None


log = logging.getLogger(__name__)

SERVICE_NAME = "polaris-ems"


async def publish_audit(
    *,
    action_type: str,
    action_name: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    method: str,
    path: str,
    response_status: int,
    user_id: Optional[str] = None,
    request_data: Any = None,
    response_data: Any = None,
    changes: Any = None,
    duration_ms: Optional[int] = None,
    **extra: Any,
) -> None:
    """Publish one audit event. Never raises.

    Any unexpected keyword args land in ``extra`` and are forwarded so
    future MDMS schema extensions work without a shared-lib bump.
    """
    try:
        await _otel_audit(
            service_name=SERVICE_NAME,
            action_type=action_type,
            action_name=action_name,
            entity_type=entity_type,
            entity_id=entity_id,
            method=method,
            path=path,
            response_status=response_status,
            user_id=user_id,
            request_data=request_data,
            response_data=response_data,
            changes=changes,
            duration_ms=duration_ms,
            **extra,
        )
    except Exception as exc:  # pragma: no cover — must not break the response
        log.warning("audit publish failed action=%s err=%s", action_name, exc)


__all__ = ["publish_audit", "SERVICE_NAME"]
