"""Notification senders package — spec 016 US1.

Public surface:

* `get_sender(channel)` — factory returning a per-channel singleton sender.
  When all provider flags are disabled the factory returns a `LogOnlySender`
  so existing dev behaviour is unchanged, and the caller records a
  ``meta.channel_disabled=true`` field on the delivery row.
* `send_notification(...)` — async façade used by outage + alarm hooks
  (see `dispatcher.py`).

The senders themselves degrade gracefully if their SDK is not installed
(boto3 / twilio / firebase-admin) — they log the attempt and mark the
delivery as `dlq` so audit stays clear.
"""
from __future__ import annotations

from typing import Dict

from app.core.config import settings
from app.models.notifications import NotificationChannel

from .log_only_sender import LogOnlySender
from .mock_email_sender import MockEmailSender
from .mock_sms_sender import MockSMSSender
from .ses_sender import SESSender
from .twilio_sender import TwilioSender
from .teams_sender import TeamsSender
from .fcm_sender import FCMSender

_senders: Dict[str, object] = {}


def get_sender(channel: str | NotificationChannel):
    """Return a process-singleton sender for the requested channel.

    If the channel is not enabled (flag OFF in settings), returns
    `MockEmailSender` / `MockSMSSender` for email/sms, or `LogOnlySender`
    for other channels. Delivery rows record ``provider=mock-email`` /
    ``provider=mock-sms`` so the audit log stays meaningful in dev/demo.
    """
    if isinstance(channel, NotificationChannel):
        channel = channel.value
    channel = channel.lower()
    if channel in _senders:
        return _senders[channel]

    enabled = {
        "email": settings.SMTP_ENABLED,
        "sms": settings.TWILIO_ENABLED,
        "teams": settings.TEAMS_ENABLED,
        "push": settings.FIREBASE_ENABLED,
    }.get(channel, False)

    if not enabled:
        if channel == "email":
            sender = MockEmailSender()
        elif channel == "sms":
            sender = MockSMSSender()
        else:
            sender = LogOnlySender(channel=channel)
    elif channel == "email":
        sender = SESSender()
    elif channel == "sms":
        sender = TwilioSender()
    elif channel == "teams":
        sender = TeamsSender()
    elif channel == "push":
        sender = FCMSender()
    else:
        sender = LogOnlySender(channel=channel)

    _senders[channel] = sender
    return sender


# Re-export for ergonomic imports
from .dispatcher import send_notification  # noqa: E402,F401
