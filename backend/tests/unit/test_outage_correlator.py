"""Unit tests for the spec 018 W3 outage correlator.

Replays a fixture queue of OutageCorrelatorInput rows through
:func:`app.services.outage_correlator.run_once` against an in-memory
SQLite DB. Covers:

    * quorum rule (N>=3 distinct meters / same DTR / 120s window) opens an incident
    * sub-quorum cluster does NOT open an incident
    * partial restoration → INVESTIGATING + restored_meter_count increment
    * full restoration → RESTORED, closed_at set, saidi_contribution_s computed
    * idempotency: processed rows are not re-processed on a second tick
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sqlalchemy import event

from app.db.base import Base
from app.models.meter import Feeder, Meter, MeterStatus, RelayState, Transformer
from app.models.meter_event import OutageCorrelatorInput
from app.models.outage import OutageIncidentW3, OutageTimelineEvent
from app.services import outage_correlator


# Monotonic counter — SQLite doesn't auto-increment BIGINT PKs the way we need
# for this mapper-level path (the correlator creates OutageTimelineEvent rows
# without a pre-set id). Install a before-insert hook that back-fills ids.
_COUNTERS = {"OutageTimelineEvent": 0, "OutageCorrelatorInput": 0}


def _bigint_autoincrement(mapper, connection, target):
    cls = type(target).__name__
    if cls in _COUNTERS and getattr(target, "id", None) is None:
        _COUNTERS[cls] += 1
        target.id = _COUNTERS[cls]


event.listen(OutageTimelineEvent, "before_insert", _bigint_autoincrement)
event.listen(OutageCorrelatorInput, "before_insert", _bigint_autoincrement)


def _next(key: str) -> int:
    _COUNTERS[key] = _COUNTERS.get(key, 0) + 1
    return _COUNTERS[key]


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def SessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def session(SessionLocal):
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_dtr(session, name: str = "DTR-1", meters: int = 5):
    feeder = Feeder(name="FDR-1", substation="SS-1", voltage_kv=11.0, capacity_kva=500.0)
    session.add(feeder)
    session.flush()
    tx = Transformer(
        name=name, feeder_id=feeder.id, latitude=0.0, longitude=0.0, capacity_kva=100.0
    )
    session.add(tx)
    session.flush()
    created = []
    for i in range(meters):
        m = Meter(
            serial=f"M{name}-{i:03d}",
            transformer_id=tx.id,
            status=MeterStatus.ONLINE,
            relay_state=RelayState.CONNECTED,
            latitude=0.0,
            longitude=0.0,
        )
        session.add(m)
        created.append(m)
    session.commit()
    return tx, created


def _enqueue(session, meter_serial, dtr_id, event_type, ts):
    row = OutageCorrelatorInput(
        meter_serial=meter_serial,
        dtr_id=dtr_id,
        event_type=event_type,
        event_ts=ts,
        processed=False,
    )
    session.add(row)
    session.commit()
    return row


def test_quorum_opens_incident(session):
    dtr, meters = _seed_dtr(session, name="DTR-A", meters=5)
    t0 = datetime.now(timezone.utc)
    # 3 meters fail within 60s window on DTR-A
    for i in range(3):
        _enqueue(session, meters[i].serial, "DTR-A", "power_failure", t0 + timedelta(seconds=i * 20))

    stats = outage_correlator.run_once(session)
    assert stats["opened"] == 1

    incidents = session.query(OutageIncidentW3).all()
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.status == "DETECTED"
    assert inc.affected_meter_count == 3
    assert "DTR-A" in (inc.affected_dtr_ids or [])
    # confidence = 3/5 * 100 = 60.0
    assert float(inc.confidence_pct) == pytest.approx(60.0)
    # Timeline appended.
    events = session.query(OutageTimelineEvent).filter_by(incident_id=inc.id).all()
    assert any(e.event_type == "detected" for e in events)
    # Inputs marked processed.
    remaining = session.query(OutageCorrelatorInput).filter_by(processed=False).count()
    assert remaining == 0


def test_sub_quorum_does_not_open(session):
    _seed_dtr(session, name="DTR-B", meters=10)
    t0 = datetime.now(timezone.utc)
    _enqueue(session, "MDTR-B-000", "DTR-B", "power_failure", t0)
    _enqueue(session, "MDTR-B-001", "DTR-B", "power_failure", t0 + timedelta(seconds=10))

    stats = outage_correlator.run_once(session)
    assert stats["opened"] == 0
    assert session.query(OutageIncidentW3).count() == 0


def test_window_too_wide_does_not_open(session):
    _seed_dtr(session, name="DTR-C", meters=10)
    t0 = datetime.now(timezone.utc)
    # 3 failures but spread over 5 minutes — outside the 120s window.
    _enqueue(session, "MDTR-C-000", "DTR-C", "power_failure", t0)
    _enqueue(session, "MDTR-C-001", "DTR-C", "power_failure", t0 + timedelta(seconds=150))
    _enqueue(session, "MDTR-C-002", "DTR-C", "power_failure", t0 + timedelta(seconds=300))

    stats = outage_correlator.run_once(session)
    assert stats["opened"] == 0


def test_partial_then_full_restore(session):
    _seed_dtr(session, name="DTR-D", meters=3)
    t0 = datetime.now(timezone.utc)
    # Open an incident with all 3 meters failing.
    for i in range(3):
        _enqueue(session, f"MDTR-D-{i:03d}", "DTR-D", "power_failure", t0 + timedelta(seconds=i * 10))
    outage_correlator.run_once(session)
    inc = session.query(OutageIncidentW3).one()
    assert inc.status == "DETECTED"

    # One meter restores.
    _enqueue(session, "MDTR-D-000", "DTR-D", "power_restored", t0 + timedelta(minutes=2))
    stats = outage_correlator.run_once(session)
    assert stats["restored_partial"] == 1
    session.refresh(inc)
    assert inc.status == "INVESTIGATING"
    assert inc.restored_meter_count == 1

    # Last two meters restore.
    _enqueue(session, "MDTR-D-001", "DTR-D", "power_restored", t0 + timedelta(minutes=3))
    _enqueue(session, "MDTR-D-002", "DTR-D", "power_restored", t0 + timedelta(minutes=4))
    stats = outage_correlator.run_once(session)
    assert stats["restored_full"] >= 1

    session.refresh(inc)
    assert inc.status == "RESTORED"
    assert inc.closed_at is not None
    # saidi_contribution_s = duration_s * affected_meter_count
    assert inc.saidi_contribution_s is not None and inc.saidi_contribution_s > 0


def test_idempotent_across_ticks(session):
    _seed_dtr(session, name="DTR-E", meters=4)
    t0 = datetime.now(timezone.utc)
    for i in range(3):
        _enqueue(session, f"MDTR-E-{i:03d}", "DTR-E", "power_failure", t0 + timedelta(seconds=i * 5))
    outage_correlator.run_once(session)

    # Second tick with no new inputs should not open another incident.
    stats = outage_correlator.run_once(session)
    assert stats["opened"] == 0
    assert session.query(OutageIncidentW3).count() == 1


def test_confidence_when_population_unknown(session):
    """No transformer seeded → fallback confidence 50%."""
    t0 = datetime.now(timezone.utc)
    for i in range(3):
        _enqueue(session, f"UNK-{i:03d}", "DTR-UNKNOWN", "power_failure", t0 + timedelta(seconds=i))
    outage_correlator.run_once(session)
    inc = session.query(OutageIncidentW3).one()
    assert float(inc.confidence_pct) == pytest.approx(50.0)
