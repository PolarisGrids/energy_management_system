"""Notification façade — spec 016 replaces the log-only shim.

Preserves the public surface (``notification_service.send_email`` / ``send_sms``
/ ``send_teams_alert`` / ``send_push`` / ``notify_alarm``) so existing callers
compile untouched. All routing now goes through
``app.services.notifications.get_sender(channel)``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.services.notifications import get_sender, send_notification

logger = logging.getLogger("polaris.notifications.facade")


def _run_sync(coro):
    """Execute an async dispatch call from a sync caller safely.

    If we're already inside an event loop (e.g. inside a FastAPI route), we
    fire-and-forget via `asyncio.create_task`; otherwise we run it to
    completion.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(coro)
        return True
    return asyncio.run(coro)


class NotificationService:
    """Back-compat façade. New code should call ``send_notification`` directly."""

    # ── Email (SMTP/SES) ─────────────────────────────────────────────────
    def send_email(self, to: str, subject: str, body: str) -> bool:
        res = get_sender("email").send(recipient=to, subject=subject, body=body)
        return res.get("status") == "sent"

    # ── SMS (Twilio) ──────────────────────────────────────────────────────
    def send_sms(self, to: str, body: str) -> bool:
        res = get_sender("sms").send(recipient=to, subject="SMS", body=body)
        return res.get("status") == "sent"

    # ── Microsoft Teams ──────────────────────────────────────────────────
    def send_teams_alert(self, title: str, text: str, severity: str = "warning") -> bool:
        res = get_sender("teams").send(
            recipient="",  # TeamsSender falls back to settings.TEAMS_WEBHOOK_URL
            subject=title,
            body=text,
            severity=severity,
        )
        return res.get("status") == "sent"

    # ── Firebase Push ────────────────────────────────────────────────────
    def send_push(self, token: str, title: str, body: str) -> bool:
        res = get_sender("push").send(recipient=token, subject=title, body=body)
        return res.get("status") == "sent"

    # ── Alarm router ─────────────────────────────────────────────────────
    def notify_alarm(
        self,
        alarm_type: str,
        severity: str,
        description: str,
        email_to: Optional[str] = None,
        sms_to: Optional[str] = None,
    ) -> None:
        subject = f"SMOC ALARM [{severity.upper()}]: {alarm_type.replace('_', ' ').title()}"
        context = {
            "alarm_type": alarm_type,
            "severity": severity,
            "title": subject,
            "body": description,
            "meter_serial": "",
            "triggered_at": "",
            "trace_id": "",
        }
        if email_to:
            _run_sync(
                send_notification(
                    channel="email",
                    recipient=email_to,
                    template_name="alarm-critical",
                    context=context,
                    severity=severity,
                )
            )
        if sms_to:
            _run_sync(
                send_notification(
                    channel="sms",
                    recipient=sms_to,
                    context={"body": f"SMOC {severity.upper()}: {description[:140]}"},
                    severity=severity,
                )
            )
        if severity.lower() in ("critical", "high"):
            _run_sync(
                send_notification(
                    channel="teams",
                    recipient="",  # TeamsSender falls back to configured webhook
                    context={"body": description, "subject": subject},
                    severity=severity,
                )
            )


notification_service = NotificationService()
