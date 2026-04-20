"""AWS SES email sender — spec 016 US1.

Falls back to logging-only if boto3 is unavailable; callers will mark the
delivery as ``dlq`` in that case (see dispatcher.py).
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("polaris.notifications.ses")


class SESSender:
    def __init__(self) -> None:
        self._client = None
        try:
            import boto3  # type: ignore

            self._client = boto3.client("ses")
        except Exception as exc:  # pragma: no cover — env-dependent
            logger.warning("boto3/ses unavailable: %s — SES sender in fallback mode", exc)

    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        if self._client is None:
            logger.info("[SES FALLBACK] to=%s subject=%s", recipient, subject)
            return {"status": "dlq", "provider": "ses", "error": "boto3 unavailable"}
        try:
            resp = self._client.send_email(
                Source=settings.SMTP_USERNAME,
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Html": {"Data": body}},
                },
            )
            return {
                "status": "sent",
                "provider": "ses",
                "provider_message_id": resp.get("MessageId"),
            }
        except Exception as exc:
            logger.error("SES send failed to=%s err=%s", recipient, exc)
            return {"status": "failed", "provider": "ses", "error": str(exc)}
