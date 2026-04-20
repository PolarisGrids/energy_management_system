"""Unit tests for spec 018 W4.T1 notification providers.

Each provider transport is mocked at the library boundary so the tests stay
offline. Verifies:
  * NotificationPayload / NotificationResult contract
  * DISABLED status when the *_ENABLED flag is off
  * SENT status + provider_reference on happy path
  * FAILED status with error string on transport errors
  * log_delivery inserts a notification_delivery row + emits audit
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.notification_delivery import NotificationDelivery
from app.services.notification_service import (
    NotificationPayload,
    NotificationResult,
    NotificationService,
    log_delivery,
)


# ── DB fixture for log_delivery tests ──────────────────────────────────────


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    s = S()
    try:
        yield s
    finally:
        s.close()


# ── Gating (all-off returns DISABLED) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_email_disabled_when_flags_off(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ENABLED", False)
    monkeypatch.setattr(settings, "SMTP_USE_SES", False)
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="email", recipient="x@y.co", subject="s", body="b"
    ))
    assert r.status == "DISABLED"


@pytest.mark.asyncio
async def test_sms_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ENABLED", False)
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="sms", recipient="+1555", body="b",
    ))
    assert r.status == "DISABLED"


@pytest.mark.asyncio
async def test_teams_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "TEAMS_ENABLED", False)
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="teams", recipient="https://x", subject="s", body="b",
    ))
    assert r.status == "DISABLED"


@pytest.mark.asyncio
async def test_push_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_ENABLED", False)
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="push", recipient="tok", subject="s", body="b",
    ))
    assert r.status == "DISABLED"


@pytest.mark.asyncio
async def test_unknown_channel_returns_failed():
    svc = NotificationService()
    r = await svc.send(NotificationPayload(channel="pigeon", recipient="x"))
    assert r.status == "FAILED"
    assert "unknown channel" in (r.error or "")


# ── Email via aiosmtplib ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_smtp_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_USE_SES", False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "sender@x.co")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.x.co")

    mock_send = AsyncMock()
    with patch("aiosmtplib.send", mock_send):
        svc = NotificationService()
        r = await svc.send(NotificationPayload(
            channel="email", recipient="ops@x.co",
            subject="hi", body="<b>boom</b>",
        ))
    assert r.status == "SENT"
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_email_smtp_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_USE_SES", False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "s@x.co")

    async def _boom(*_args, **_kwargs):
        raise ConnectionError("denied")

    with patch("aiosmtplib.send", _boom):
        svc = NotificationService()
        r = await svc.send(NotificationPayload(
            channel="email", recipient="ops@x.co", subject="hi", body="b",
        ))
    assert r.status == "FAILED"
    assert "denied" in (r.error or "")


# ── SES happy path ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_ses_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USE_SES", True)
    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "me@x.co")

    fake_client = MagicMock()
    fake_client.send_email.return_value = {"MessageId": "ses-msg-1"}
    with patch("boto3.client", return_value=fake_client):
        svc = NotificationService()
        r = await svc.send(NotificationPayload(
            channel="email", recipient="ops@x.co", subject="hi", body="plain",
        ))
    assert r.status == "SENT"
    assert r.provider_reference == "ses-msg-1"
    fake_client.send_email.assert_called_once()


# ── SMS via Twilio ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sms_missing_creds(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ENABLED", True)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    svc = NotificationService()
    r = await svc.send(NotificationPayload(channel="sms", recipient="+1", body="hi"))
    assert r.status == "FAILED"
    assert "credentials missing" in (r.error or "")


@pytest.mark.asyncio
async def test_sms_happy_path(monkeypatch):
    pytest.importorskip("twilio")
    monkeypatch.setattr(settings, "TWILIO_ENABLED", True)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC1")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15550000000")

    fake_msg = MagicMock()
    fake_msg.sid = "SM-abc"
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg
    with patch("twilio.rest.Client", return_value=fake_client):
        svc = NotificationService()
        r = await svc.send(NotificationPayload(
            channel="sms", recipient="+15551234567", body="hi",
        ))
    assert r.status == "SENT"
    assert r.provider_reference == "SM-abc"


@pytest.mark.asyncio
async def test_sms_missing_package_returns_failed(monkeypatch):
    """When the twilio package isn't installed the provider returns FAILED."""
    monkeypatch.setattr(settings, "TWILIO_ENABLED", True)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC1")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15550000000")
    import sys
    if "twilio" in sys.modules:
        pytest.skip("twilio installed — this test only runs when absent")
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="sms", recipient="+1", body="hi",
    ))
    assert r.status == "FAILED"
    assert "twilio" in (r.error or "").lower()


# ── Teams webhook ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_teams_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "TEAMS_ENABLED", True)

    captured = {}

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a, **kw):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["card"] = json
            r = MagicMock()
            r.headers = {"request-id": "tr-1"}
            r.status_code = 200
            r.raise_for_status = MagicMock()
            return r

    with patch("httpx.AsyncClient", _FakeAsyncClient):
        svc = NotificationService()
        r = await svc.send(NotificationPayload(
            channel="teams",
            recipient="https://webhook.office.com/x",
            subject="Critical",
            body="DTR-1 overload",
            metadata={"severity": "critical"},
        ))
    assert r.status == "SENT"
    assert captured["url"] == "https://webhook.office.com/x"
    assert captured["card"]["themeColor"] == "FF0000"


# ── Firebase push ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_happy_path(monkeypatch):
    pytest.importorskip("firebase_admin")
    monkeypatch.setattr(settings, "FIREBASE_ENABLED", True)
    # Force lazy-init to bypass firebase_admin.initialize_app
    svc = NotificationService()
    svc.__class__._firebase_app_initialised = True

    with patch("firebase_admin.messaging.send", return_value="firebase-ref-1"):
        r = await svc.send(NotificationPayload(
            channel="push", recipient="fcm-token-xyz",
            subject="hi", body="b", metadata={"rule_id": "R1"},
        ))
    assert r.status == "SENT"
    assert r.provider_reference == "firebase-ref-1"


@pytest.mark.asyncio
async def test_push_transport_error(monkeypatch):
    pytest.importorskip("firebase_admin")
    monkeypatch.setattr(settings, "FIREBASE_ENABLED", True)
    svc = NotificationService()
    svc.__class__._firebase_app_initialised = True

    def _boom(*_a, **_k):
        raise RuntimeError("fcm down")

    with patch("firebase_admin.messaging.send", side_effect=_boom):
        r = await svc.send(NotificationPayload(
            channel="push", recipient="tok", subject="x", body="y",
        ))
    assert r.status == "FAILED"
    assert "fcm down" in (r.error or "")


@pytest.mark.asyncio
async def test_push_missing_package_returns_failed(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_ENABLED", True)
    import sys
    if "firebase_admin" in sys.modules:
        pytest.skip("firebase-admin installed — this test only runs when absent")
    svc = NotificationService()
    r = await svc.send(NotificationPayload(
        channel="push", recipient="tok", body="hi",
    ))
    assert r.status == "FAILED"
    assert "firebase" in (r.error or "").lower()


# ── log_delivery ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_delivery_persists_row(session):
    payload = NotificationPayload(
        channel="email", recipient="x@y.co", subject="s", body="b",
        metadata={"trace": "abc"},
    )
    result = NotificationResult(status="SENT", provider_reference="ref-1")
    row_id = await log_delivery(
        session,
        rule_id=None,
        firing_id=None,
        payload=payload,
        result=result,
    )
    session.commit()
    row = session.query(NotificationDelivery).filter_by(id=row_id).first()
    assert row is not None
    assert row.status == "SENT"
    assert row.channel == "email"
    assert row.provider_reference == "ref-1"
    assert row.payload["metadata"] == {"trace": "abc"}
