"""MS Teams incoming-webhook sender — spec 016 US1."""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("polaris.notifications.teams")


class TeamsSender:
    def __init__(self) -> None:
        self._httpx = None
        try:
            import httpx  # type: ignore

            self._httpx = httpx
        except Exception as exc:  # pragma: no cover
            logger.warning("httpx unavailable for Teams sender: %s", exc)

    def send(self, recipient: str, subject: str, body: str, severity: str = "info", **kwargs) -> dict:
        color_map = {
            "critical": "FF0000",
            "high": "FF8C00",
            "medium": "FFA500",
            "info": "0078D7",
            "low": "0078D7",
        }
        color = color_map.get((severity or "info").lower(), "0078D7")
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": subject,
            "sections": [{"activityTitle": subject, "activityText": body}],
        }
        webhook_url = recipient or settings.TEAMS_WEBHOOK_URL
        if self._httpx is None:
            logger.info("[TEAMS FALLBACK] to=%s subject=%s", webhook_url, subject)
            return {"status": "dlq", "provider": "teams", "error": "httpx unavailable"}
        try:
            r = self._httpx.post(webhook_url, json=card, timeout=10)
            r.raise_for_status()
            return {"status": "sent", "provider": "teams"}
        except Exception as exc:
            logger.error("Teams webhook failed url=%s err=%s", webhook_url, exc)
            return {"status": "failed", "provider": "teams", "error": str(exc)}
