"""Outage correlator — spec 018 W3.T1 + W3.T2.

Reads rows from `outage_correlator_input` (populated by the Wave-2A
`hesv2.meter.events` consumer) and opens/updates `outage_incident` rows.

**Detection (W3.T1)** — rule:
    N >= OUTAGE_MIN_METERS (default 3) `power_failure` events on meters
    under the same DTR, all within OUTAGE_WINDOW_SECONDS (default 120s)
    of each other → open a new `outage_incident` with status=DETECTED.

**Restoration (W3.T2)** — when `power_restored` events arrive for meters
belonging to an open incident:
    * partial → status=INVESTIGATING, restored_meter_count bumped,
      timeline event appended.
    * all → status=RESTORED, closed_at=now(), saidi_contribution_s set.

The loop is idempotent: ``processed`` is flipped on every input row it
consumes. A process crash mid-batch will reprocess unflipped rows on
restart.

Invoked from :pymod:`app.main`'s lifespan; can also be kicked manually via
:func:`run_once` for unit tests.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.meter import Meter, Transformer
from app.models.meter_event import OutageCorrelatorInput
from app.models.outage import (
    OutageFlisrAction,  # noqa: F401 (kept for side-effect registration)
    OutageIncidentW3,
    OutageTimelineEvent,
)

log = logging.getLogger(__name__)


# ── Tunables (env-overridable) ──────────────────────────────────────────────

def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


OUTAGE_MIN_METERS = _int_env("OUTAGE_MIN_METERS", 3)
OUTAGE_WINDOW_SECONDS = _int_env("OUTAGE_WINDOW_SECONDS", 120)
# How long to keep an "active" incident open looking for restores before we
# let a new failure cluster on the same DTR open a fresh incident.
OUTAGE_DEDUP_WINDOW_SECONDS = _int_env("OUTAGE_DEDUP_WINDOW_SECONDS", 1800)
CORRELATOR_TICK_SECONDS = float(os.getenv("OUTAGE_CORRELATOR_TICK_SECONDS", "5"))
CORRELATOR_BATCH = _int_env("OUTAGE_CORRELATOR_BATCH", 500)


# ── Public API ──────────────────────────────────────────────────────────────


async def run_correlator_loop(stop_event: Optional[asyncio.Event] = None) -> None:
    """Long-running loop that polls `outage_correlator_input`.

    In production the Wave-2A consumer enqueues rows; here we drain them on
    a tick and emit/update incidents. Designed to be resilient — all DB
    operations happen inside a single transaction per tick.
    """
    log.info(
        "outage_correlator starting tick=%ss min_meters=%d window_s=%d",
        CORRELATOR_TICK_SECONDS,
        OUTAGE_MIN_METERS,
        OUTAGE_WINDOW_SECONDS,
    )
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        try:
            await asyncio.get_event_loop().run_in_executor(None, run_once)
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("outage_correlator tick failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CORRELATOR_TICK_SECONDS)
        except asyncio.TimeoutError:
            continue


def run_once(db: Optional[Session] = None) -> dict:
    """Process one tick against the DB. Returns a small stats dict.

    Exposed separately so unit tests can replay fixtures without spinning
    up the async loop.
    """
    own_session = db is None
    session: Session = db or SessionLocal()
    stats = {
        "consumed": 0,
        "opened": 0,
        "restored_partial": 0,
        "restored_full": 0,
    }
    try:
        pending: List[OutageCorrelatorInput] = (
            session.query(OutageCorrelatorInput)
            .filter(OutageCorrelatorInput.processed.is_(False))
            .order_by(OutageCorrelatorInput.event_ts.asc(), OutageCorrelatorInput.id.asc())
            .limit(CORRELATOR_BATCH)
            .all()
        )
        if not pending:
            return stats

        # Resolve DTR for any rows that arrived with null dtr_id by joining
        # through the meter registry.
        _hydrate_dtrs(session, pending)

        failures = [e for e in pending if e.event_type == "power_failure"]
        restores = [e for e in pending if e.event_type == "power_restored"]

        # Group power_failure events by dtr_id.
        by_dtr: Dict[str, List[OutageCorrelatorInput]] = defaultdict(list)
        for ev in failures:
            if ev.dtr_id:
                by_dtr[ev.dtr_id].append(ev)

        for dtr_id, events in by_dtr.items():
            events.sort(key=lambda e: e.event_ts)
            cluster = _find_cluster(events, OUTAGE_WINDOW_SECONDS, OUTAGE_MIN_METERS)
            if cluster:
                incident = _open_or_extend_incident(session, dtr_id, cluster)
                if incident is not None:
                    stats["opened"] += 1

        # Apply restorations.
        for ev in restores:
            result = _apply_restoration(session, ev)
            if result == "partial":
                stats["restored_partial"] += 1
            elif result == "full":
                stats["restored_full"] += 1

        # Mark everything consumed this tick (idempotent — even if it didn't
        # reach quorum, we don't want to keep reprocessing old rows).
        for e in pending:
            e.processed = True
            stats["consumed"] += 1

        session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


# ── Implementation helpers ─────────────────────────────────────────────────


def _hydrate_dtrs(session: Session, events: Iterable[OutageCorrelatorInput]) -> None:
    missing = {e.meter_serial for e in events if not e.dtr_id}
    if not missing:
        return
    rows = (
        session.query(Meter.serial, Transformer.name, Transformer.id)
        .join(Transformer, Meter.transformer_id == Transformer.id)
        .filter(Meter.serial.in_(missing))
        .all()
    )
    lookup = {serial: str(tx_name or tx_id) for serial, tx_name, tx_id in rows}
    for e in events:
        if not e.dtr_id:
            e.dtr_id = lookup.get(e.meter_serial)


def _find_cluster(
    events: List[OutageCorrelatorInput],
    window_s: int,
    min_meters: int,
) -> Optional[List[OutageCorrelatorInput]]:
    """Sliding-window cluster detection.

    Returns the earliest qualifying window (distinct meters >= min_meters
    within ``window_s``) or None. Duplicates per meter_serial collapse.
    """
    n = len(events)
    if n < min_meters:
        return None
    left = 0
    window_td = timedelta(seconds=window_s)
    for right in range(n):
        while events[right].event_ts - events[left].event_ts > window_td:
            left += 1
        distinct = {e.meter_serial for e in events[left : right + 1]}
        if len(distinct) >= min_meters:
            return events[left : right + 1]
    return None


def _open_or_extend_incident(
    session: Session,
    dtr_id: str,
    cluster: List[OutageCorrelatorInput],
) -> Optional[OutageIncidentW3]:
    """Open a new incident or fold the cluster into an existing one."""
    earliest = cluster[0].event_ts
    # Look back for an *open* incident on the same DTR within the dedup window.
    cutoff = earliest - timedelta(seconds=OUTAGE_DEDUP_WINDOW_SECONDS)
    existing = (
        session.query(OutageIncidentW3)
        .filter(OutageIncidentW3.status.in_(("DETECTED", "INVESTIGATING", "DISPATCHED")))
        .filter(OutageIncidentW3.opened_at >= cutoff)
        .all()
    )
    target: Optional[OutageIncidentW3] = None
    for inc in existing:
        dtrs = list(inc.affected_dtr_ids or [])
        if dtr_id in dtrs:
            target = inc
            break

    distinct_meters = sorted({e.meter_serial for e in cluster})
    total_meters = _dtr_meter_population(session, dtr_id)
    confidence = _confidence_pct(len(distinct_meters), total_meters)

    if target is None:
        incident_id = str(uuid.uuid4())
        target = OutageIncidentW3(
            id=incident_id,
            opened_at=earliest,
            status="DETECTED",
            affected_dtr_ids=[dtr_id],
            affected_meter_count=len(distinct_meters),
            restored_meter_count=0,
            confidence_pct=confidence,
            timeline=[],
            trigger_trace_id=cluster[0].source_trace_id,
        )
        session.add(target)
        session.flush()
        _append_timeline(
            session,
            target,
            "detected",
            {
                "dtr_id": dtr_id,
                "meters": distinct_meters,
                "window_seconds": OUTAGE_WINDOW_SECONDS,
                "confidence_pct": float(confidence) if confidence is not None else None,
            },
        )
        return target

    # Already-open incident: fold in any new meters.
    current_count = target.affected_meter_count or 0
    if len(distinct_meters) > current_count:
        target.affected_meter_count = len(distinct_meters)
        target.confidence_pct = confidence
        _append_timeline(
            session,
            target,
            "meters_updated",
            {"meters": distinct_meters, "confidence_pct": float(confidence) if confidence else None},
        )
    return None  # did not open a new incident


def _apply_restoration(
    session: Session,
    ev: OutageCorrelatorInput,
) -> Optional[str]:
    if not ev.dtr_id:
        return None
    incident = (
        session.query(OutageIncidentW3)
        .filter(OutageIncidentW3.status.in_(("DETECTED", "INVESTIGATING", "DISPATCHED")))
        .order_by(OutageIncidentW3.opened_at.desc())
        .all()
    )
    target: Optional[OutageIncidentW3] = None
    for inc in incident:
        if ev.dtr_id in (inc.affected_dtr_ids or []):
            target = inc
            break
    if target is None:
        return None

    restored = (target.restored_meter_count or 0) + 1
    target.restored_meter_count = restored
    affected = target.affected_meter_count or 0
    if restored >= affected and affected > 0:
        target.status = "RESTORED"
        target.closed_at = ev.event_ts or datetime.now(timezone.utc)
        duration_s = int(
            max(0, (target.closed_at - target.opened_at).total_seconds())
        )
        target.saidi_contribution_s = duration_s * affected
        _append_timeline(
            session,
            target,
            "restored",
            {
                "meter_serial": ev.meter_serial,
                "all_restored": True,
                "duration_s": duration_s,
            },
        )
        return "full"
    # Partial restore → INVESTIGATING.
    target.status = "INVESTIGATING"
    _append_timeline(
        session,
        target,
        "meter_restored",
        {"meter_serial": ev.meter_serial, "restored_count": restored, "total": affected},
    )
    return "partial"


def _dtr_meter_population(session: Session, dtr_id: str) -> int:
    """Best-effort count of meters attached to the DTR in our registry.

    Accepts either Transformer.name or Transformer.id as the match key — the
    upstream HES payload is inconsistent; we accept both.
    """
    try:
        tx = (
            session.query(Transformer)
            .filter(or_(Transformer.name == dtr_id, Transformer.id == _safe_int(dtr_id)))
            .first()
        )
    except Exception:
        tx = session.query(Transformer).filter(Transformer.name == dtr_id).first()
    if tx is None:
        return 0
    return session.query(Meter).filter(Meter.transformer_id == tx.id).count()


def _safe_int(val: str) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return -1


def _confidence_pct(affected: int, total: int):
    if total <= 0:
        # Unknown population: fall back to a conservative 50%.
        return 50.0
    pct = 100.0 * affected / total
    return max(0.0, min(pct, 100.0))


def _append_timeline(
    session: Session,
    incident: OutageIncidentW3,
    event_type: str,
    details: Optional[dict],
    actor_user_id: Optional[str] = None,
) -> OutageTimelineEvent:
    now = datetime.now(timezone.utc)
    row = OutageTimelineEvent(
        incident_id=incident.id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        details=details,
        trace_id=incident.trigger_trace_id,
        at=now,
    )
    session.add(row)
    # Also stamp the denormalised JSONB column for cheap reads.
    tl = list(incident.timeline or [])
    tl.append(
        {
            "event_type": event_type,
            "details": details,
            "actor_user_id": actor_user_id,
            "at": now.isoformat(),
        }
    )
    incident.timeline = tl
    incident.updated_at = now
    return row


__all__ = [
    "run_correlator_loop",
    "run_once",
    "OUTAGE_MIN_METERS",
    "OUTAGE_WINDOW_SECONDS",
]
