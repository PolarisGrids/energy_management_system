"""Mock email sender for dev/demo environments (SMTP_ENABLED=False)."""
from __future__ import annotations

import logging

logger = logging.getLogger("polaris.notifications.mock_email")


class MockEmailSender:
    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        logger.info(
            "[MOCK EMAIL] to=%s | subject=%s | body=%s",
            recipient,
            subject,
            (body or "")[:200],
        )
        return {
            "status": "sent",
            "provider": "mock-email",
        }
