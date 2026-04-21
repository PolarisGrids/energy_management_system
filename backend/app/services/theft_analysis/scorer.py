"""Theft scorer — orchestrates detectors across the full meter roster.

Public entrypoint :func:`score_all_meters` performs a single pass:

  1. Pull the consumer roster from MDMS.
  2. Pull one 14-day block-load + 30-day daily window (batched, not per-meter).
  3. Pull tamper events for the same window.
  4. Build peer baselines per ``meter_type``.
  5. Run every detector against every meter → ``MeterScore``.

The return value is a list of :class:`MeterScore` objects; persistence is
the caller's responsibility (see :mod:`app.services.theft_analysis.runner`).
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.services.theft_analysis.detectors import (
    DetectorResult,
    MeterSignals,
    PeerBaseline,
    run_all,
)
from app.services.theft_analysis.mdms_client import (
    DailyReading,
    HHReading,
    MeterRoster,
    TamperEvent,
    fetch_daily_window,
    fetch_hh_window,
    fetch_meter_roster,
    fetch_tamper_events,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────

@dataclass
class MeterScore:
    device_identifier: str
    meter_type: Optional[str]
    score: float                        # 0..100
    risk_tier: str                      # critical / high / medium / low
    fired_detectors: List[str]          # detector_ids
    top_evidence: List[Dict]            # compact summary per fired detector
    detectors: List[DetectorResult]     # full results (for persistence)
    computed_at: datetime
    # Context for UI chips
    account_id: Optional[str] = None
    sanctioned_load: Optional[float] = None
    manufacturer: Optional[str] = None


def _risk_tier(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


# ──────────────────────────────────────────────────────────────────────
# Peer-baseline builder
# ──────────────────────────────────────────────────────────────────────

def _build_peer_baseline(
    roster: List[MeterRoster],
    daily: List[DailyReading],
    now: datetime,
) -> PeerBaseline:
    # For each meter, compute 7-day mean daily kWh, then group by meter_type.
    cutoff = now - timedelta(days=7)
    per_meter_mean: Dict[str, List[float]] = defaultdict(list)
    by_meter: Dict[str, List[float]] = defaultdict(list)
    for r in daily:
        if r.ts is None or r.ts < cutoff:
            continue
        by_meter[r.device_identifier].append((r.import_wh or 0) / 1000.0)

    type_by_meter = {m.device_identifier: (m.meter_type or "_unknown") for m in roster}

    for mid, vals in by_meter.items():
        if len(vals) < 3:
            continue
        mtype = type_by_meter.get(mid, "_unknown")
        per_meter_mean[mtype].append(statistics.fmean(vals))

    baseline = PeerBaseline()
    for mtype, means in per_meter_mean.items():
        if len(means) < 3:
            continue
        baseline.daily_kwh_mean[mtype] = statistics.fmean(means)
        baseline.daily_kwh_stdev[mtype] = (
            statistics.pstdev(means) if len(means) > 1 else 0.0
        )
        baseline.sample_size[mtype] = len(means)
    return baseline


# ──────────────────────────────────────────────────────────────────────
# Core scoring
# ──────────────────────────────────────────────────────────────────────

def _compact_evidence(r: DetectorResult) -> Dict:
    """Compact one-line summary stored in `top_evidence` — the UI uses this
    to render evidence chips without having to unpack the full detector
    payload. The full payload lives in the persisted `detectors` column."""
    return {
        "id": r.detector_id,
        "label": r.label,
        "severity": r.severity,
        "score": round(r.weight * r.score, 1),
    }


def score_meter(signals: MeterSignals) -> MeterScore:
    results = run_all(signals)
    fired = [r for r in results if r.fired]
    total = sum(r.weight * r.score for r in fired)
    final = min(100.0, round(total, 1))
    tier = _risk_tier(final)
    # Sort fired by contribution desc — top evidence first.
    fired_sorted = sorted(
        fired, key=lambda r: r.weight * r.score, reverse=True,
    )
    return MeterScore(
        device_identifier=signals.meter.device_identifier,
        meter_type=signals.meter.meter_type,
        score=final,
        risk_tier=tier,
        fired_detectors=[r.detector_id for r in fired_sorted],
        top_evidence=[_compact_evidence(r) for r in fired_sorted[:5]],
        detectors=results,
        computed_at=signals.now,
        account_id=signals.meter.account_id,
        sanctioned_load=signals.meter.sanctioned_load,
        manufacturer=signals.meter.manufacturer,
    )


def score_all_meters(
    *,
    now: Optional[datetime] = None,
    hh_days: int = 14,
    daily_days: int = 30,
    events_days: int = 30,
) -> List[MeterScore]:
    """Full-roster scoring pass. Safe to call from a background task."""
    now = now or datetime.now(timezone.utc)
    roster = fetch_meter_roster()
    if not roster:
        log.info("theft scorer: empty roster (MDMS unreachable?) — skipping")
        return []

    log.info("theft scorer: scoring %d meters", len(roster))
    ids = [m.device_identifier for m in roster]

    hh = fetch_hh_window(
        period_start=now - timedelta(days=hh_days),
        period_end=now,
        device_identifiers=ids,
    )
    daily = fetch_daily_window(
        period_start=now - timedelta(days=daily_days),
        period_end=now,
        device_identifiers=ids,
    )
    events = fetch_tamper_events(
        period_start=now - timedelta(days=events_days),
        period_end=now,
        device_identifiers=ids,
    )
    log.info(
        "theft scorer: fetched %d hh, %d daily, %d events",
        len(hh), len(daily), len(events),
    )

    # Index once.
    hh_by_meter: Dict[str, List[HHReading]] = defaultdict(list)
    for r in hh:
        hh_by_meter[r.device_identifier].append(r)
    daily_by_meter: Dict[str, List[DailyReading]] = defaultdict(list)
    for r in daily:
        daily_by_meter[r.device_identifier].append(r)
    events_by_meter: Dict[str, List[TamperEvent]] = defaultdict(list)
    for e in events:
        events_by_meter[e.device_identifier].append(e)

    peer = _build_peer_baseline(roster, daily, now)
    log.info("theft scorer: peer baseline %s", peer.sample_size)

    scores: List[MeterScore] = []
    for meter in roster:
        sig = MeterSignals(
            meter=meter,
            hh=hh_by_meter.get(meter.device_identifier, []),
            daily=daily_by_meter.get(meter.device_identifier, []),
            events=events_by_meter.get(meter.device_identifier, []),
            peer=peer,
            now=now,
        )
        scores.append(score_meter(sig))

    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


__all__ = [
    "MeterScore",
    "score_meter",
    "score_all_meters",
]
