"""Alarm-rule evaluation engine — spec 018 W4.T4 + W4.T5.

Polls the ``alarm_event`` and ``der_telemetry`` tables each
``ALARM_RULE_TICK_SECONDS`` seconds. For every active rule whose
``condition`` AST matches recent rows (within ``dedup_window_seconds``),
creates a ``alarm_rule_firing`` row and dispatches notifications per
``rule.action.channels``.

Condition AST (stored as JSONB on ``alarm_rule.condition``)::

    {"source":             "alarm_event|der_telemetry",
     "field":              "severity|alarm_type|load_pct|active_power_kw|...",
     "op":                 ">|>=|<|<=|==|in|contains",
     "value":              <scalar|list>,
     "duration_seconds":   0,   # sustained window — 0 = instantaneous
     "match_count":        1,   # minimum rows within the dedup window}

Action shape::

    {"channels": [{"type": "email|sms|teams|push",
                   "recipients": ["ops@x.co"],
                   "template": {"subject": "...", "body": "..."}}],
     "webhook_url": "https://...",
     "priority": 1..5}

Schedule shape (optional — spec W4.T5)::

    {"quiet_hours": {"start": "22:00", "end": "06:00", "tz": "Asia/Kolkata"},
     "tiers": [{"after_seconds": 300,
                "channels": [{"type": "sms",
                              "recipients": ["supervisor@x.co"]}]}]}

Dedup: each rule computes a ``dedup_key`` per tick that is the triple
``(rule_id, meter_serial_or_dtr, match_time_bucket)``. If a firing row with
the same ``(rule_id, dedup_key)`` exists within ``dedup_window_seconds``,
the rule is skipped. Keeps a sustained outlier from firing every tick.

Quiet hours + escalation (W4.T5):

* During quiet hours, channels listed in
  ``ALARM_QUIET_SUPPRESS_CHANNELS`` (default ``sms`` + ``push``) are
  dropped for priority 3–5 rules and the send is recorded as
  ``status=QUEUED`` for ``send_after=<quiet_end>``. Email remains
  enabled so the operator gets an inbox record.
* Priority 1–2 (critical) bypass quiet hours.
* Escalation tiers fire as follow-ups when a prior firing has not been
  acknowledged after ``after_seconds``; implemented by a second scan
  inside the same tick.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, List, Optional, Tuple

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from app.api.v1._trace import current_trace_id
from app.core.config import settings
from app.db.base import SessionLocal
from app.models.alarm import Alarm, AlarmSeverity
from app.models.alarm_rule import AlarmRule, AlarmRuleFiring
from app.models.der_ems import DERCommandEMS  # noqa: F401 (forces model import)
from app.models.virtual_object_group import VirtualObjectGroup
from app.services.group_resolver import resolve_group_members
from app.services.notification_service import (
    NotificationPayload,
    NotificationResult,
    log_delivery,
    notification_service,
)

log = logging.getLogger(__name__)


# ── Condition evaluator ────────────────────────────────────────────────────


_OPERATORS = {
    ">":  lambda a, b: a is not None and a >  b,
    ">=": lambda a, b: a is not None and a >= b,
    "<":  lambda a, b: a is not None and a <  b,
    "<=": lambda a, b: a is not None and a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in (b or []),
    "contains": lambda a, b: (a is not None) and (str(b) in str(a)),
}


def _eval_scalar(lhs: Any, op: str, rhs: Any) -> bool:
    fn = _OPERATORS.get(op)
    if fn is None:
        return False
    try:
        return bool(fn(lhs, rhs))
    except Exception:
        return False


# ── DER telemetry abstraction ───────────────────────────────────────────────


def _get_der_telemetry_cls():
    """Imported lazily — the DER telemetry table is maintained by W2.T7."""
    try:
        from app.models.der_ems import DERTelemetry  # type: ignore
        return DERTelemetry
    except Exception:
        return None


# ── Rule evaluation ────────────────────────────────────────────────────────


@dataclass
class RuleMatch:
    """One matching observation for a rule."""
    meter_serial: Optional[str]
    dtr_id: Optional[str]
    observed_value: Any
    event_id: Optional[str] = None
    ts: Optional[datetime] = None


def _evaluate_rule(
    db: Session, rule: AlarmRule, since: datetime
) -> List[RuleMatch]:
    """Return rows from the rule's source table that satisfy the condition.

    ``since`` bounds the lookback window (dedup_window * 2 as a safety net).
    Scoping to the rule's group is applied by intersecting meter_serial with
    the resolved member list (if the group is populated).
    """
    cond = dict(rule.condition or {})
    source = (cond.get("source") or "alarm_event").lower()
    field = cond.get("field")
    op = cond.get("op", "==")
    value = cond.get("value")
    if not field:
        return []

    group = db.query(VirtualObjectGroup).filter(
        VirtualObjectGroup.id == rule.group_id
    ).first()
    members = resolve_group_members(db, group) if group else []
    members_set = set(members)

    matches: List[RuleMatch] = []

    if source == "alarm_event":
        q = (
            db.query(Alarm)
            .filter(Alarm.triggered_at >= since)
            .order_by(desc(Alarm.triggered_at))
            .limit(500)
        )
        for row in q.all():
            # Resolve the attribute in a forgiving way (supports enums).
            raw = getattr(row, field, None)
            lhs = getattr(raw, "value", raw)
            rhs = value
            if not _eval_scalar(lhs, op, rhs):
                continue
            if members_set and row.meter_serial and row.meter_serial not in members_set:
                # Fall through — allow match when meter_serial is None OR
                # when the group is empty (unscoped rule).
                continue
            matches.append(
                RuleMatch(
                    meter_serial=row.meter_serial,
                    dtr_id=None,
                    observed_value=lhs,
                    event_id=str(row.id),
                    ts=row.triggered_at,
                )
            )
        return matches

    if source == "der_telemetry":
        DERTelemetry = _get_der_telemetry_cls()
        if DERTelemetry is None:
            return []
        q = (
            db.query(DERTelemetry)
            .filter(DERTelemetry.ts >= since)
            .order_by(desc(DERTelemetry.ts))
            .limit(1000)
        )
        for row in q.all():
            lhs = getattr(row, field, None)
            if lhs is None:
                continue
            if not _eval_scalar(float(lhs), op, float(value)
                                if isinstance(value, (int, float, str)) else value):
                continue
            # The DER telemetry rows don't carry a meter_serial directly; the
            # rule engine treats asset_id as the grouping dimension.
            matches.append(
                RuleMatch(
                    meter_serial=None,
                    dtr_id=getattr(row, "asset_id", None),
                    observed_value=float(lhs),
                    event_id=str(getattr(row, "id", "")),
                    ts=getattr(row, "ts", None),
                )
            )
        return matches

    log.debug("rule_engine: unknown source %s for rule %s", source, rule.id)
    return []


# ── Quiet-hours / escalation helpers ───────────────────────────────────────


def _parse_hhmm(s: str) -> Optional[time]:
    try:
        hh, mm = s.split(":", 1)
        return time(int(hh), int(mm))
    except Exception:
        return None


def _in_quiet_hours(schedule: Optional[dict], now: Optional[datetime] = None) -> bool:
    if not schedule:
        return False
    qh = schedule.get("quiet_hours") or {}
    start = _parse_hhmm(qh.get("start", ""))
    end = _parse_hhmm(qh.get("end", ""))
    if not start or not end:
        return False
    now = now or datetime.now(timezone.utc)
    now_t = now.time()
    if start == end:
        return False
    if start < end:
        return start <= now_t < end
    # wraps over midnight (e.g. 22:00 → 06:00)
    return now_t >= start or now_t < end


def _quiet_end_dt(schedule: dict, now: Optional[datetime] = None) -> datetime:
    end = _parse_hhmm(schedule["quiet_hours"]["end"]) or time(6, 0)
    now = now or datetime.now(timezone.utc)
    candidate = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


# ── Firing + dispatch ──────────────────────────────────────────────────────


def _recent_firing(
    db: Session, rule: AlarmRule, dedup_key: str, now: datetime
) -> Optional[AlarmRuleFiring]:
    window_start = now - timedelta(seconds=rule.dedup_window_seconds or
                                   settings.ALARM_RULE_DEFAULT_DEDUP_SECONDS)
    return (
        db.query(AlarmRuleFiring)
        .filter(
            AlarmRuleFiring.rule_id == rule.id,
            AlarmRuleFiring.dedup_key == dedup_key,
            AlarmRuleFiring.fired_at >= window_start,
        )
        .order_by(desc(AlarmRuleFiring.fired_at))
        .first()
    )


def _make_dedup_key(rule: AlarmRule, match: RuleMatch) -> str:
    scope = match.meter_serial or match.dtr_id or "ALL"
    return f"{rule.id}:{scope}"


def _render_channel_payload(
    rule: AlarmRule, firing: AlarmRuleFiring, channel: dict, escalation_tier: int
) -> Tuple[NotificationPayload, str]:
    """Build a NotificationPayload for one channel config entry.

    Returns (payload, recipient_str) — recipient is already joined for log
    readability (the payload carries the single recipient used).
    """
    tpl = channel.get("template") or {}
    default_subject = f"[SMOC P{rule.priority}] {rule.name}"
    default_body = (
        f"Rule '{rule.name}' fired.\n"
        f"Condition: {rule.condition}\n"
        f"Match: meter={firing.sample_meter_serial} dtr={firing.sample_dtr_id} "
        f"value={firing.context.get('observed_value') if firing.context else '?'}\n"
        f"Fired at: {firing.fired_at.isoformat()}\n"
        f"Tier: {escalation_tier}"
    )
    recipients = channel.get("recipients") or []
    return (
        NotificationPayload(
            channel=channel.get("type", "").lower(),
            recipient=recipients[0] if recipients else "",
            subject=tpl.get("subject") or default_subject,
            body=tpl.get("body") or default_body,
            metadata={
                "rule_id": rule.id,
                "firing_id": firing.id,
                "severity": {1: "critical", 2: "high", 3: "warning", 4: "info", 5: "info"}.get(
                    rule.priority, "info"
                ),
                "escalation_tier": escalation_tier,
            },
        ),
        ", ".join(recipients),
    )


async def _dispatch_channels(
    db: Session,
    rule: AlarmRule,
    firing: AlarmRuleFiring,
    channels: List[dict],
    escalation_tier: int,
    now: Optional[datetime] = None,
) -> int:
    """Send one payload per (channel, recipient). Return count of rows logged."""
    now = now or datetime.now(timezone.utc)
    quiet = _in_quiet_hours(rule.schedule, now)
    suppress = set(settings.ALARM_QUIET_SUPPRESS_CHANNELS or [])
    count = 0

    for channel in channels:
        ctype = (channel.get("type") or "").lower()
        for recipient in channel.get("recipients") or []:
            payload = NotificationPayload(
                channel=ctype,
                recipient=recipient,
                subject=(channel.get("template") or {}).get("subject")
                        or f"[SMOC P{rule.priority}] {rule.name}",
                body=(channel.get("template") or {}).get("body")
                     or _default_body(rule, firing, escalation_tier),
                metadata={
                    "rule_id": rule.id,
                    "firing_id": firing.id,
                    "severity": _priority_to_severity(rule.priority),
                    "escalation_tier": escalation_tier,
                },
            )

            # Quiet hours policy (spec W4.T5). Priority 1–2 ignores it.
            #  - SMS + push (channels in ALARM_QUIET_SUPPRESS_CHANNELS) → dropped
            #  - email → queued with send_after = quiet_end_dt
            #  - other channels (teams, webhook) → send as usual
            if quiet and rule.priority >= 3:
                if ctype == "email":
                    queued_result = NotificationResult(status="QUEUED")
                    await log_delivery(
                        db,
                        rule_id=rule.id,
                        firing_id=firing.id,
                        payload=payload,
                        result=queued_result,
                        escalation_tier=escalation_tier,
                        send_after=_quiet_end_dt(rule.schedule, now),
                    )
                    count += 1
                    continue
                if ctype in suppress:
                    dropped_result = NotificationResult(
                        status="DISABLED", error="quiet_hours suppressed"
                    )
                    await log_delivery(
                        db,
                        rule_id=rule.id,
                        firing_id=firing.id,
                        payload=payload,
                        result=dropped_result,
                        escalation_tier=escalation_tier,
                    )
                    count += 1
                    continue

            result = await notification_service.send(payload)
            await log_delivery(
                db,
                rule_id=rule.id,
                firing_id=firing.id,
                payload=payload,
                result=result,
                escalation_tier=escalation_tier,
            )
            count += 1

    # Webhook is best-effort fire-and-forget, logged in the same table.
    webhook_url = (rule.action or {}).get("webhook_url")
    if webhook_url:
        await _fire_webhook(db, rule, firing, webhook_url, escalation_tier)
        count += 1

    return count


def _default_body(rule: AlarmRule, firing: AlarmRuleFiring, tier: int) -> str:
    ctx = firing.context or {}
    return (
        f"Rule '{rule.name}' fired (priority {rule.priority}, tier {tier}).\n"
        f"Scope: meter={firing.sample_meter_serial} dtr={firing.sample_dtr_id}\n"
        f"Observed value: {ctx.get('observed_value')}\n"
        f"Matched {firing.match_count} event(s) at {firing.fired_at.isoformat()}.\n"
        f"Condition: {rule.condition}"
    )


def _priority_to_severity(priority: int) -> str:
    return {1: "critical", 2: "high", 3: "warning", 4: "info", 5: "info"}.get(
        priority or 3, "info"
    )


async def _fire_webhook(
    db: Session, rule: AlarmRule, firing: AlarmRuleFiring, url: str, tier: int
) -> None:
    try:
        import httpx
        payload = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "firing_id": firing.id,
            "priority": rule.priority,
            "escalation_tier": tier,
            "fired_at": firing.fired_at.isoformat(),
            "context": firing.context,
        }
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(url, json=payload)
            r.raise_for_status()
        result = NotificationResult(status="SENT", provider_reference=str(r.status_code))
    except Exception as exc:
        log.warning("rule_engine webhook failed: %s", exc)
        result = NotificationResult(status="FAILED", error=str(exc)[:500])
    await log_delivery(
        db,
        rule_id=rule.id,
        firing_id=firing.id,
        payload=NotificationPayload(channel="webhook", recipient=url, body=""),
        result=result,
        escalation_tier=tier,
    )


# ── Firing creation ────────────────────────────────────────────────────────


async def evaluate_rule_once(
    db: Session, rule: AlarmRule, now: Optional[datetime] = None
) -> List[AlarmRuleFiring]:
    """Evaluate one rule against recent rows. Returns list of firings created.

    Respects dedup: a second invocation within the dedup window for the same
    (rule, scope) key is a no-op. Does NOT create firings for an inactive
    rule (defensive — callers should already filter).
    """
    if not rule.active:
        return []
    now = now or datetime.now(timezone.utc)
    lookback_s = max(
        rule.dedup_window_seconds or settings.ALARM_RULE_DEFAULT_DEDUP_SECONDS,
        int((rule.condition or {}).get("duration_seconds") or 0) + 60,
    )
    since = now - timedelta(seconds=lookback_s)

    matches = _evaluate_rule(db, rule, since)
    min_count = int((rule.condition or {}).get("match_count") or 1)

    # Group matches by scope key.
    groups: dict[str, List[RuleMatch]] = {}
    for m in matches:
        k = _make_dedup_key(rule, m)
        groups.setdefault(k, []).append(m)

    created: List[AlarmRuleFiring] = []
    for dedup_key, match_list in groups.items():
        if len(match_list) < min_count:
            continue
        if _recent_firing(db, rule, dedup_key, now) is not None:
            continue

        sample = match_list[0]
        firing = AlarmRuleFiring(
            id=uuid.uuid4().hex,
            rule_id=rule.id,
            fired_at=now,
            dedup_key=dedup_key,
            match_count=len(match_list),
            sample_meter_serial=sample.meter_serial,
            sample_dtr_id=sample.dtr_id,
            context={
                "observed_value": sample.observed_value,
                "event_id": sample.event_id,
                "rule_condition": rule.condition,
            },
            trace_id=current_trace_id(),
            escalation_tier=0,
        )
        db.add(firing)
        db.flush()
        created.append(firing)

        # Dispatch tier-0 (primary) channels.
        channels = ((rule.action or {}).get("channels") or [])
        await _dispatch_channels(db, rule, firing, channels, escalation_tier=0, now=now)

    db.commit()
    return created


async def escalate_once(
    db: Session, rule: AlarmRule, now: Optional[datetime] = None
) -> int:
    """Promote un-acked firings to higher tiers per rule.schedule.tiers.

    Returns the number of escalation dispatches performed.
    """
    now = now or datetime.now(timezone.utc)
    tiers = ((rule.schedule or {}).get("tiers") or [])
    if not tiers:
        return 0

    # For each open (unacked) firing of this rule, check if the next tier's
    # after_seconds has elapsed. We only escalate monotonically: tier N+1
    # requires firing.escalation_tier == N and age >= after_seconds.
    open_firings = (
        db.query(AlarmRuleFiring)
        .filter(
            AlarmRuleFiring.rule_id == rule.id,
            AlarmRuleFiring.acknowledged_at.is_(None),
        )
        .all()
    )
    dispatched = 0
    for firing in open_firings:
        next_tier_index = firing.escalation_tier
        if next_tier_index >= len(tiers):
            continue
        tier_cfg = tiers[next_tier_index]
        after_s = int(
            tier_cfg.get("after_seconds")
            or settings.ALARM_RULE_DEFAULT_ESCALATE_AFTER_SECONDS
        )
        fired = firing.fired_at
        if fired is not None and fired.tzinfo is None:
            fired = fired.replace(tzinfo=timezone.utc)
        age_s = (now - fired).total_seconds()
        if age_s < after_s:
            continue
        channels = tier_cfg.get("channels") or []
        await _dispatch_channels(
            db, rule, firing, channels, escalation_tier=next_tier_index + 1, now=now
        )
        firing.escalation_tier = next_tier_index + 1
        dispatched += 1
    db.commit()
    return dispatched


# ── Main loop ──────────────────────────────────────────────────────────────


async def run_rule_engine_loop(stop_event: asyncio.Event) -> None:  # pragma: no cover — scheduler
    """Background task: evaluate + escalate every tick until stop set."""
    interval = settings.ALARM_RULE_TICK_SECONDS
    while not stop_event.is_set():
        try:
            await _one_tick()
        except Exception:
            log.exception("rule_engine tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def _one_tick() -> None:
    """Query all active rules, evaluate + escalate each in turn."""
    db = SessionLocal()
    try:
        rules = db.query(AlarmRule).filter(AlarmRule.active.is_(True)).all()
        for rule in rules:
            try:
                await evaluate_rule_once(db, rule)
                await escalate_once(db, rule)
            except Exception:
                log.exception("rule_engine: rule %s failed", rule.id)
                db.rollback()
    finally:
        db.close()


__all__ = [
    "evaluate_rule_once",
    "escalate_once",
    "run_rule_engine_loop",
    "_in_quiet_hours",
    "_quiet_end_dt",
]
