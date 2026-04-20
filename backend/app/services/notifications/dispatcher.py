"""Unified notification dispatch — spec 016 US1.

Flow:
1. Look up the `NotificationTemplate` by name (if provided).
2. Render subject/body using simple `str.format(**context)`; fall back to
   raw template on KeyError so a missing context key never drops the page.
3. Call the channel sender (or `LogOnlySender` if the channel flag is OFF).
4. Persist a `NotificationDelivery` row with status / retries / meta /
   provider message id.
5. On failure: retry up to 3 times with exponential backoff (1s/4s/16s)
   then persist status='dlq' for audit.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.notifications import (
    NotificationDelivery,
    NotificationStatus,
    NotificationTemplate,
)

logger = logging.getLogger("polaris.notifications.dispatcher")

_RETRY_BACKOFF = [1, 4, 16]


def _render(tpl: Optional[str], context: dict[str, Any]) -> str:
    if not tpl:
        return ""
    # Jinja-flavoured {{ var }} placeholders are normalised to Python .format()
    # so a single render code path handles both template styles.
    normalised = tpl.replace("{{ ", "{").replace(" }}", "}").replace("{{", "{").replace("}}", "}")
    try:
        return normalised.format(**context)
    except Exception:
        return tpl


def _persist_delivery(
    db: Session,
    *,
    channel: str,
    recipient: str,
    template_id: Optional[int],
    status: str,
    retries: int,
    last_error: Optional[str],
    meta: dict[str, Any],
    sent_at: Optional[datetime],
) -> NotificationDelivery:
    row = NotificationDelivery(
        channel=channel,
        recipient=recipient,
        template_id=template_id,
        status=status,
        retries=retries,
        last_error=last_error,
        meta=meta,
        sent_at=sent_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


async def send_notification(
    channel: str,
    recipient: str,
    template_name: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    rule_id: Optional[int] = None,
    severity: Optional[str] = None,
) -> NotificationDelivery:
    """Render + dispatch + persist.

    Returns the `NotificationDelivery` row (even on failure). Callers should
    inspect `.status` — values are the members of
    :class:`NotificationStatus`.
    """
    from app.services.notifications import get_sender  # local to avoid cycle

    context = dict(context or {})
    db = SessionLocal()
    try:
        template: Optional[NotificationTemplate] = None
        if template_name:
            template = (
                db.query(NotificationTemplate)
                .filter(NotificationTemplate.name == template_name)
                .first()
            )

        subject = _render(template.subject_tpl if template else None, context) or "Notification"
        body = _render(template.body_tpl if template else None, context) or context.get("body", "")

        sender = get_sender(channel)
        last_error: Optional[str] = None
        result: dict[str, Any] = {}

        attempts = 0
        for attempt in range(len(_RETRY_BACKOFF) + 1):
            attempts = attempt
            try:
                result = sender.send(
                    recipient=recipient,
                    subject=subject,
                    body=body,
                    severity=severity,
                )
                if result.get("status") == "sent":
                    break
                last_error = result.get("error") or f"sender returned status={result.get('status')}"
            except Exception as exc:
                last_error = str(exc)
                result = {"status": "failed", "error": last_error}
            if attempt < len(_RETRY_BACKOFF):
                await asyncio.sleep(_RETRY_BACKOFF[attempt])

        final_status_str = result.get("status") or "failed"
        # Map "failed" after retries exhausted → DLQ.
        if final_status_str != "sent" and attempts >= len(_RETRY_BACKOFF):
            final_status_str = "dlq"

        meta = {
            "provider": result.get("provider"),
            "provider_message_id": result.get("provider_message_id"),
            "rule_id": rule_id,
            "severity": severity,
            "template_name": template_name,
        }
        if result.get("channel_disabled"):
            meta["channel_disabled"] = True

        return _persist_delivery(
            db,
            channel=channel,
            recipient=recipient,
            template_id=template.id if template else None,
            status=final_status_str,
            retries=attempts,
            last_error=last_error if final_status_str != "sent" else None,
            meta=meta,
            sent_at=datetime.now(timezone.utc) if final_status_str == "sent" else None,
        )
    finally:
        db.close()
