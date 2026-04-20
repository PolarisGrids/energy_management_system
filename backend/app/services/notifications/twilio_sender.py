"""Twilio SMS sender — spec 016 US1."""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("polaris.notifications.twilio")


class TwilioSender:
    def __init__(self) -> None:
        self._client = None
        try:
            from twilio.rest import Client  # type: ignore

            self._client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("twilio SDK unavailable: %s", exc)

    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        payload = body or subject
        if self._client is None:
            logger.info("[TWILIO FALLBACK] to=%s body=%s", recipient, payload[:140])
            return {"status": "dlq", "provider": "twilio", "error": "twilio SDK unavailable"}
        try:
            msg = self._client.messages.create(
                body=payload,
                from_=settings.TWILIO_FROM_NUMBER,
                to=recipient,
            )
            return {
                "status": "sent",
                "provider": "twilio",
                "provider_message_id": getattr(msg, "sid", None),
            }
        except Exception as exc:
            logger.error("Twilio send failed to=%s err=%s", recipient, exc)
            return {"status": "failed", "provider": "twilio", "error": str(exc)}
