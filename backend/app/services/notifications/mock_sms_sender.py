"""Mock SMS sender for dev/demo environments (TWILIO_ENABLED=False)."""
from __future__ import annotations

import logging

logger = logging.getLogger("polaris.notifications.mock_sms")


class MockSMSSender:
    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        payload = body or subject
        logger.info(
            "[MOCK SMS] to=%s | body=%s",
            recipient,
            payload[:200],
        )
        return {
            "status": "sent",
            "provider": "mock-sms",
        }
