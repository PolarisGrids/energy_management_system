"""Tests for spec 018 W4.T4 / W4.T5 alarm-rule CRUD + engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.alarm import Alarm, AlarmSeverity, AlarmStatus, AlarmType
from app.models.alarm_rule import AlarmRule, AlarmRuleFiring
from app.models.notification_delivery import NotificationDelivery
from app.models.virtual_object_group import VirtualObjectGroup
from app.services import notification_service as ns_mod
from app.services import rule_engine


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_group(db, *, group_id=None, hierarchy=None, filters=None) -> VirtualObjectGroup:
    g = VirtualObjectGroup(
        id=group_id or uuid.uuid4().hex,
        name=f"g-{uuid.uuid4().hex[:6]}",
        selector={
            "hierarchy": hierarchy or {},
            "filters": filters or {},
        },
        owner_user_id="42",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_rule(
    db,
    group_id,
    *,
    condition=None,
    action=None,
    priority=3,
    schedule=None,
    dedup=60,
    active=True,
) -> AlarmRule:
    r = AlarmRule(
        id=uuid.uuid4().hex,
        group_id=group_id,
        name=f"r-{uuid.uuid4().hex[:6]}",
        condition=condition or {
            "source": "alarm_event", "field": "severity", "op": "==",
            "value": "critical",
        },
        action=action or {
            "channels": [{"type": "email", "recipients": ["ops@x.co"]}]
        },
        priority=priority,
        active=active,
        schedule=schedule,
        dedup_window_seconds=dedup,
        owner_user_id="42",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


class _RecordingService:
    """Substitute for notification_service.send() that records calls."""

    def __init__(self, status="SENT"):
        self.calls = []
        self.status = status

    async def send(self, payload):
        self.calls.append(payload)
        return ns_mod.NotificationResult(
            status=self.status,
            provider_reference=f"ref-{len(self.calls)}",
        )


@pytest.fixture
def recording_service(monkeypatch):
    svc = _RecordingService()
    monkeypatch.setattr(rule_engine, "notification_service", svc)
    return svc


# ── CRUD endpoint tests ────────────────────────────────────────────────────


def test_create_alarm_rule(client, db):
    g = _make_group(db)
    resp = client.post(
        "/api/v1/alarm-rules",
        json={
            "group_id": g.id,
            "name": "critical alarm",
            "condition": {"source": "alarm_event", "field": "severity",
                          "op": "==", "value": "critical"},
            "action": {"channels": [{"type": "email", "recipients": ["ops@x.co"]}]},
            "priority": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["priority"] == 1


def test_create_rule_invalid_group(client):
    resp = client.post(
        "/api/v1/alarm-rules",
        json={
            "group_id": uuid.uuid4().hex,
            "name": "x",
            "condition": {}, "action": {},
        },
    )
    assert resp.status_code == 400


def test_list_filter_active(client, db):
    g = _make_group(db)
    _make_rule(db, g.id, active=True)
    _make_rule(db, g.id, active=False)
    resp = client.get("/api/v1/alarm-rules", params={"active": "true"})
    assert resp.status_code == 200
    assert all(r["active"] for r in resp.json())


def test_patch_rule_toggle_active(client, db):
    g = _make_group(db)
    r = _make_rule(db, g.id, active=True)
    resp = client.patch(f"/api/v1/alarm-rules/{r.id}", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_delete_rule(client, db):
    g = _make_group(db)
    r = _make_rule(db, g.id)
    assert client.delete(f"/api/v1/alarm-rules/{r.id}").status_code == 204
    assert client.get(f"/api/v1/alarm-rules/{r.id}").status_code == 404


# ── Rule engine tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_fires_on_matching_alarm(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        condition={"source": "alarm_event", "field": "severity",
                   "op": "==", "value": "critical"},
    )
    # Seed a matching alarm.
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.CRITICAL,
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="crit tamper",
    ))
    db.commit()

    firings = await rule_engine.evaluate_rule_once(db, rule)
    assert len(firings) == 1
    assert firings[0].match_count == 1
    # Notification recorded
    assert len(recording_service.calls) == 1
    assert recording_service.calls[0].channel == "email"
    # Delivery row persisted
    deliveries = db.query(NotificationDelivery).filter_by(rule_id=rule.id).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "SENT"


@pytest.mark.asyncio
async def test_engine_no_match_no_firing(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        condition={"source": "alarm_event", "field": "severity",
                   "op": "==", "value": "critical"},
    )
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.LOW,  # below threshold
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="low",
    ))
    db.commit()

    firings = await rule_engine.evaluate_rule_once(db, rule)
    assert firings == []
    assert recording_service.calls == []


@pytest.mark.asyncio
async def test_engine_dedup_prevents_double_fire(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        condition={"source": "alarm_event", "field": "severity",
                   "op": "==", "value": "critical"},
        dedup=600,
    )
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.CRITICAL,
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="crit",
    ))
    db.commit()

    firings_1 = await rule_engine.evaluate_rule_once(db, rule)
    firings_2 = await rule_engine.evaluate_rule_once(db, rule)
    assert len(firings_1) == 1
    assert firings_2 == []  # deduped within window


@pytest.mark.asyncio
async def test_engine_dispatches_to_multiple_channels(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        action={"channels": [
            {"type": "email", "recipients": ["a@x.co", "b@x.co"]},
            {"type": "teams", "recipients": ["https://webhook.office.com/x"]},
        ]},
    )
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.CRITICAL,
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="crit",
    ))
    db.commit()

    await rule_engine.evaluate_rule_once(db, rule)
    # 2 email + 1 teams = 3 send calls
    assert len(recording_service.calls) == 3
    assert {p.channel for p in recording_service.calls} == {"email", "teams"}


@pytest.mark.asyncio
async def test_quiet_hours_suppress_sms_queue_email(db, recording_service,
                                                    monkeypatch):
    # Freeze "now" inside quiet window (00:30 UTC, quiet 22:00->06:00).
    now = datetime.now(timezone.utc).replace(hour=0, minute=30)
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        priority=3,  # non-critical — subject to quiet rules
        schedule={"quiet_hours": {"start": "22:00", "end": "06:00"}},
        action={"channels": [
            {"type": "sms", "recipients": ["+15550000000"]},
            {"type": "email", "recipients": ["ops@x.co"]},
        ]},
    )
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.CRITICAL,
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="crit",
        triggered_at=now,
    ))
    db.commit()

    firings = await rule_engine.evaluate_rule_once(db, rule, now=now)
    assert len(firings) == 1

    # No real sends because both were suppressed or queued.
    # SMS should land as DISABLED (dropped), email as QUEUED.
    deliveries = db.query(NotificationDelivery).filter_by(rule_id=rule.id).all()
    by_channel = {d.channel: d for d in deliveries}
    assert by_channel["sms"].status == "DISABLED"
    assert by_channel["email"].status == "QUEUED"
    assert by_channel["email"].send_after is not None


@pytest.mark.asyncio
async def test_priority_1_bypasses_quiet_hours(db, recording_service):
    now = datetime.now(timezone.utc).replace(hour=2, minute=0)
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        priority=1,
        schedule={"quiet_hours": {"start": "22:00", "end": "06:00"}},
        action={"channels": [{"type": "sms", "recipients": ["+15551112222"]}]},
    )
    db.add(Alarm(
        alarm_type=AlarmType.TAMPER,
        severity=AlarmSeverity.CRITICAL,
        status=AlarmStatus.ACTIVE,
        meter_serial="M1",
        title="p1",
        triggered_at=now,
    ))
    db.commit()

    await rule_engine.evaluate_rule_once(db, rule, now=now)
    # Priority 1 must bypass — send recorded
    assert len(recording_service.calls) == 1
    assert recording_service.calls[0].channel == "sms"


@pytest.mark.asyncio
async def test_escalation_tier_fires_after_delay(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        schedule={
            "tiers": [
                {"after_seconds": 30,
                 "channels": [{"type": "sms", "recipients": ["+1555"]}]},
            ]
        },
    )
    # Pre-seed a firing that's already 60s old and un-acked.
    old = datetime.now(timezone.utc) - timedelta(seconds=60)
    firing = AlarmRuleFiring(
        id=uuid.uuid4().hex,
        rule_id=rule.id,
        fired_at=old,
        dedup_key=f"{rule.id}:M1",
        match_count=1,
        sample_meter_serial="M1",
        context={"observed_value": "critical"},
        escalation_tier=0,
    )
    db.add(firing)
    db.commit()

    dispatched = await rule_engine.escalate_once(db, rule)
    assert dispatched == 1
    db.refresh(firing)
    assert firing.escalation_tier == 1
    # Notification was sent to tier-1 recipient
    assert len(recording_service.calls) == 1
    assert recording_service.calls[0].channel == "sms"
    assert recording_service.calls[0].recipient == "+1555"


@pytest.mark.asyncio
async def test_escalation_skipped_when_acknowledged(db, recording_service):
    g = _make_group(db)
    rule = _make_rule(
        db, g.id,
        schedule={
            "tiers": [
                {"after_seconds": 30,
                 "channels": [{"type": "email", "recipients": ["boss@x.co"]}]},
            ]
        },
    )
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    firing = AlarmRuleFiring(
        id=uuid.uuid4().hex,
        rule_id=rule.id,
        fired_at=old,
        dedup_key=f"{rule.id}:M1",
        match_count=1,
        sample_meter_serial="M1",
        context={},
        escalation_tier=0,
        acknowledged_at=datetime.now(timezone.utc),
        acknowledged_by="99",
    )
    db.add(firing)
    db.commit()

    dispatched = await rule_engine.escalate_once(db, rule)
    assert dispatched == 0
    assert recording_service.calls == []


# ── Quiet-hours helper tests ───────────────────────────────────────────────


def test_in_quiet_hours_wraps_midnight():
    schedule = {"quiet_hours": {"start": "22:00", "end": "06:00"}}
    assert rule_engine._in_quiet_hours(schedule,
                                       datetime(2026, 4, 18, 23, 30, tzinfo=timezone.utc))
    assert rule_engine._in_quiet_hours(schedule,
                                       datetime(2026, 4, 18, 2, 0, tzinfo=timezone.utc))
    assert not rule_engine._in_quiet_hours(schedule,
                                            datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc))


def test_in_quiet_hours_normal_range():
    schedule = {"quiet_hours": {"start": "12:00", "end": "13:00"}}
    assert rule_engine._in_quiet_hours(schedule,
                                       datetime(2026, 4, 18, 12, 30, tzinfo=timezone.utc))
    assert not rule_engine._in_quiet_hours(schedule,
                                            datetime(2026, 4, 18, 11, 59, tzinfo=timezone.utc))


# ── Acknowledge endpoint ───────────────────────────────────────────────────


def test_acknowledge_firing(client, db):
    g = _make_group(db)
    r = _make_rule(db, g.id)
    firing = AlarmRuleFiring(
        id=uuid.uuid4().hex, rule_id=r.id,
        fired_at=datetime.now(timezone.utc),
        dedup_key=f"{r.id}:M1",
        match_count=1, sample_meter_serial="M1", context={},
    )
    db.add(firing)
    db.commit()
    resp = client.post(
        f"/api/v1/alarm-rules/{r.id}/acknowledge",
        json={"firing_id": firing.id, "note": "on it"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["acknowledged_at"] is not None
    # second ack conflicts
    resp2 = client.post(
        f"/api/v1/alarm-rules/{r.id}/acknowledge",
        json={"firing_id": firing.id},
    )
    assert resp2.status_code == 409


def test_list_firings_and_deliveries(client, db):
    g = _make_group(db)
    r = _make_rule(db, g.id)
    firing = AlarmRuleFiring(
        id=uuid.uuid4().hex, rule_id=r.id,
        fired_at=datetime.now(timezone.utc),
        dedup_key=f"{r.id}:M1",
        match_count=1, sample_meter_serial="M1", context={},
    )
    db.add(firing)
    db.add(NotificationDelivery(
        id=uuid.uuid4().hex, rule_id=r.id, firing_id=firing.id,
        channel="email", recipient="x@y.co", status="SENT",
    ))
    db.commit()
    assert len(client.get(f"/api/v1/alarm-rules/{r.id}/firings").json()) == 1
    assert len(client.get(f"/api/v1/alarm-rules/{r.id}/deliveries").json()) == 1
