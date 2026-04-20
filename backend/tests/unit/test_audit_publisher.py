"""Unit tests for publish_audit — spec 018 W2.T13."""
from __future__ import annotations

import pytest

from app.services import audit_publisher


@pytest.mark.asyncio
async def test_publish_audit_calls_otel_audit(monkeypatch):
    calls = []

    async def _fake(**kw):
        calls.append(kw)

    monkeypatch.setattr(audit_publisher, "_otel_audit", _fake)

    await audit_publisher.publish_audit(
        action_type="WRITE",
        action_name="acknowledge_alarm",
        entity_type="Alarm",
        entity_id="1",
        method="POST",
        path="/api/v1/alarms/1/acknowledge",
        response_status=200,
        user_id="42",
        request_data={"note": "ack"},
        duration_ms=12,
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["service_name"] == "polaris-ems"
    assert kw["action_type"] == "WRITE"
    assert kw["action_name"] == "acknowledge_alarm"
    assert kw["entity_type"] == "Alarm"
    assert kw["entity_id"] == "1"
    assert kw["method"] == "POST"
    assert kw["path"] == "/api/v1/alarms/1/acknowledge"
    assert kw["response_status"] == 200
    assert kw["user_id"] == "42"
    assert kw["request_data"] == {"note": "ack"}
    assert kw["duration_ms"] == 12


@pytest.mark.asyncio
async def test_publish_audit_never_raises(monkeypatch):
    async def _boom(**_kw):
        raise RuntimeError("kafka down")

    monkeypatch.setattr(audit_publisher, "_otel_audit", _boom)

    # Must not propagate — audit failures cannot break the response path.
    await audit_publisher.publish_audit(
        action_type="WRITE",
        action_name="x",
        entity_type="Y",
        method="POST",
        path="/",
        response_status=500,
    )


@pytest.mark.asyncio
async def test_publish_audit_forwards_extra_kwargs(monkeypatch):
    calls = []

    async def _fake(**kw):
        calls.append(kw)

    monkeypatch.setattr(audit_publisher, "_otel_audit", _fake)

    await audit_publisher.publish_audit(
        action_type="READ",
        action_name="list_meters",
        entity_type="Meter",
        method="GET",
        path="/api/v1/meters",
        response_status=200,
        ip_address="10.0.0.1",  # extra
    )
    assert calls[0]["ip_address"] == "10.0.0.1"
