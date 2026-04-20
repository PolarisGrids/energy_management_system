"""Firebase Cloud Messaging push sender — spec 016 US1."""
from __future__ import annotations

import logging

logger = logging.getLogger("polaris.notifications.fcm")


class FCMSender:
    def __init__(self) -> None:
        self._messaging = None
        try:
            import firebase_admin  # type: ignore
            from firebase_admin import messaging  # type: ignore

            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            self._messaging = messaging
        except Exception as exc:  # pragma: no cover
            logger.warning("firebase-admin unavailable: %s", exc)

    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        if self._messaging is None:
            logger.info("[FCM FALLBACK] token=%s subject=%s", recipient[:16], subject)
            return {"status": "dlq", "provider": "fcm", "error": "firebase-admin unavailable"}
        try:
            msg = self._messaging.Message(
                token=recipient,
                notification=self._messaging.Notification(title=subject, body=body),
            )
            resp = self._messaging.send(msg)
            return {"status": "sent", "provider": "fcm", "provider_message_id": resp}
        except Exception as exc:
            logger.error("FCM push failed token=%s err=%s", recipient[:16], exc)
            return {"status": "failed", "provider": "fcm", "error": str(exc)}
