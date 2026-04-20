"""Outage state-machine unit tests — spec 016 US2."""
from __future__ import annotations

import pytest

from app.models.outage import OutageIncident, OutageStatus
from app.services.outage_state_machine import (
    ALLOWED,
    InvalidTransition,
    can_transition,
    transition,
)


def _make_incident(status: OutageStatus = OutageStatus.DETECTED) -> OutageIncident:
    inc = OutageIncident()
    inc.id = 1
    inc.status = status.value
    inc.confirmed_at = None
    inc.dispatched_at = None
    inc.restored_at = None
    inc.closed_at = None
    return inc


# ── can_transition matrix ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "src,dst,expected",
    [
        (OutageStatus.DETECTED, OutageStatus.CONFIRMED, True),
        (OutageStatus.DETECTED, OutageStatus.CANCELLED, True),
        (OutageStatus.DETECTED, OutageStatus.DISPATCHED, False),
        (OutageStatus.CONFIRMED, OutageStatus.DISPATCHED, True),
        (OutageStatus.CONFIRMED, OutageStatus.RESTORED, False),
        (OutageStatus.DISPATCHED, OutageStatus.RESTORING, True),
        (OutageStatus.RESTORING, OutageStatus.RESTORED, True),
        (OutageStatus.RESTORING, OutageStatus.CANCELLED, False),
        (OutageStatus.RESTORED, OutageStatus.CLOSED, True),
        (OutageStatus.RESTORED, OutageStatus.DETECTED, False),
        (OutageStatus.CLOSED, OutageStatus.RESTORED, False),
        (OutageStatus.CANCELLED, OutageStatus.DETECTED, False),
    ],
)
def test_can_transition_matrix(src, dst, expected):
    assert can_transition(src, dst) is expected


def test_allowed_map_covers_all_statuses():
    for status in OutageStatus:
        assert status in ALLOWED


# ── transition() behaviour ────────────────────────────────────────────


def test_transition_stamps_confirmed_at():
    inc = _make_incident(OutageStatus.DETECTED)
    transition(inc, OutageStatus.CONFIRMED)
    assert inc.status == OutageStatus.CONFIRMED.value
    assert inc.confirmed_at is not None


def test_transition_stamps_restored_then_closed():
    inc = _make_incident(OutageStatus.RESTORING)
    transition(inc, OutageStatus.RESTORED)
    assert inc.restored_at is not None
    assert inc.closed_at is None
    transition(inc, OutageStatus.CLOSED)
    assert inc.closed_at is not None


def test_cancelled_sets_closed_at_as_off_ramp():
    inc = _make_incident(OutageStatus.DETECTED)
    transition(inc, OutageStatus.CANCELLED)
    assert inc.status == OutageStatus.CANCELLED.value
    assert inc.closed_at is not None


def test_illegal_transition_raises():
    inc = _make_incident(OutageStatus.DETECTED)
    with pytest.raises(InvalidTransition):
        transition(inc, OutageStatus.CLOSED)


def test_terminal_states_reject_further_transitions():
    for terminal in (OutageStatus.CLOSED, OutageStatus.CANCELLED):
        inc = _make_incident(terminal)
        for tgt in OutageStatus:
            if tgt == terminal:
                continue
            with pytest.raises(InvalidTransition):
                transition(inc, tgt)
