"""Log-only sender used when a channel's provider flag is OFF."""
from __future__ import annotations

import logging

logger = logging.getLogger("polaris.notifications.log_only")


class LogOnlySender:
    def __init__(self, channel: str = "email") -> None:
        self.channel = channel

    def send(self, recipient: str, subject: str, body: str, **kwargs) -> dict:
        logger.info(
            "[NOTIFY %s DISABLED] to=%s subject=%s body=%s",
            self.channel.upper(),
            recipient,
            subject,
            (body or "")[:140],
        )
        return {
            "status": "sent",
            "provider": "log-only",
            "channel_disabled": True,
        }
