"""Per-meter theft detectors.

Each detector is a pure function:

    detect_xxx(ctx, signals) -> DetectorResult

``signals`` bundles together everything a detector might look at (HH
readings, daily readings, tamper events, peer baseline). Detectors that
don't need a particular channel just ignore it.

Output is a :class:`DetectorResult` with a boolean ``fired`` flag and a
``score`` in [0, 1] representing *intensity* — scorer multiplies by the
detector's static weight to produce the contribution to the meter's
overall theft score.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.services.theft_analysis.mdms_client import (
    DailyReading,
    HHReading,
    MeterRoster,
    TamperEvent,
)


# ──────────────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class PeerBaseline:
    """Population baselines, bucketed by meter_type.

    ``daily_kwh_mean[meter_type]`` = mean over all peers of each peer's
    own 7-day average daily kWh. Stdev likewise.
    """
    daily_kwh_mean: Dict[str, float] = field(default_factory=dict)
    daily_kwh_stdev: Dict[str, float] = field(default_factory=dict)
    sample_size: Dict[str, int] = field(default_factory=dict)


@dataclass
class MeterSignals:
    meter: MeterRoster
    hh: List[HHReading]
    daily: List[DailyReading]
    events: List[TamperEvent]
    peer: PeerBaseline
    now: datetime


@dataclass
class DetectorResult:
    detector_id: str
    label: str
    fired: bool
    score: float                 # 0..1 intensity, 0 when not fired
    weight: float                # static base weight (see DETECTOR_WEIGHTS)
    evidence: Dict[str, Any] = field(default_factory=dict)
    severity: str = "low"        # low / medium / high / critical


# ──────────────────────────────────────────────────────────────────────
# Weights (plan §detectors)
# ──────────────────────────────────────────────────────────────────────

DETECTOR_WEIGHTS: Dict[str, float] = {
    "tamper_event":           25.0,
    "time_tampering":         15.0,
    "flat_line":              15.0,
    "sudden_drop":            15.0,
    "reverse_energy":         20.0,
    "peer_zscore":            10.0,
    "week_over_week":         10.0,
    "phase_imbalance":        15.0,
    "md_collapse":            10.0,
    "load_factor_collapse":   10.0,
    # Explicit bypass pattern detectors (SMOC theft enhancement):
    #   partial_bypass — 30–60% sustained kWh drop with continued activity
    #   full_bypass    — ≥70% drop while meter remains online/ping-alive
    "partial_bypass":         20.0,
    "full_bypass":            25.0,
}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _clean(xs: Sequence[Optional[float]]) -> List[float]:
    return [float(x) for x in xs if x is not None]


def _slice_hh(
    hh: Sequence[HHReading],
    *,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
) -> List[HHReading]:
    out: List[HHReading] = []
    for r in hh:
        if r.ts is None:
            continue
        if after and r.ts < after:
            continue
        if before and r.ts >= before:
            continue
        out.append(r)
    return out


def _slice_daily(
    d: Sequence[DailyReading],
    *,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
) -> List[DailyReading]:
    out: List[DailyReading] = []
    for r in d:
        if r.ts is None:
            continue
        if after and r.ts < after:
            continue
        if before and r.ts >= before:
            continue
        out.append(r)
    return out


def _mean(xs: Sequence[float]) -> Optional[float]:
    return statistics.fmean(xs) if xs else None


def _stdev(xs: Sequence[float]) -> Optional[float]:
    return statistics.pstdev(xs) if len(xs) > 1 else None


# ──────────────────────────────────────────────────────────────────────
# Detectors
# ──────────────────────────────────────────────────────────────────────

# 1. DLMS tamper events — any of 201, 203, 205, 251 in lookback window.
TAMPER_OCCURRED_CODES = {201, 203, 205, 251}


def detect_tamper_event(s: MeterSignals) -> DetectorResult:
    window_start = s.now - timedelta(days=7)
    hits = [
        e for e in s.events
        if e.event_code in TAMPER_OCCURRED_CODES
           and e.event_ts is not None
           and e.event_ts >= window_start
    ]
    fired = bool(hits)
    # Intensity: 1.0 if ≥3 distinct codes, else scaled.
    distinct_codes = len({e.event_code for e in hits})
    score = min(1.0, 0.4 + 0.2 * distinct_codes) if fired else 0.0
    severity = "critical" if distinct_codes >= 2 else ("high" if fired else "low")
    return DetectorResult(
        detector_id="tamper_event",
        label="DLMS tamper event (magnetic / neutral / low-PF / cover)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["tamper_event"],
        severity=severity,
        evidence={
            "window_days": 7,
            "event_count": len(hits),
            "distinct_codes": sorted({e.event_code for e in hits}),
            "latest": [
                {
                    "ts": e.event_ts.isoformat() if e.event_ts else None,
                    "code": e.event_code,
                    "label": e.event_label,
                    "source": e.event_source,
                }
                for e in sorted(
                    hits, key=lambda x: x.event_ts or datetime.min, reverse=True,
                )[:5]
            ],
        },
    )


# 2. Time tampering — DLMS code 2018.
def detect_time_tampering(s: MeterSignals) -> DetectorResult:
    window_start = s.now - timedelta(days=30)
    hits = [
        e for e in s.events
        if e.event_code == 2018
           and e.event_ts is not None
           and e.event_ts >= window_start
    ]
    fired = bool(hits)
    return DetectorResult(
        detector_id="time_tampering",
        label="Meter clock tampering",
        fired=fired,
        score=1.0 if fired else 0.0,
        weight=DETECTOR_WEIGHTS["time_tampering"],
        severity="high" if fired else "low",
        evidence={
            "event_count": len(hits),
            "latest_ts": (
                max(h.event_ts for h in hits if h.event_ts).isoformat()
                if hits and any(h.event_ts for h in hits)
                else None
            ),
        },
    )


# 3. Flat-line — HH import_Wh has near-zero coefficient of variation.
FLAT_LINE_CV_MAX = 0.10    # σ/μ threshold
FLAT_LINE_MIN_SLOTS = 40   # need at least 20h of HH data


def detect_flat_line(s: MeterSignals) -> DetectorResult:
    window = _slice_hh(s.hh, after=s.now - timedelta(days=2))
    imports = _clean([r.import_wh for r in window])
    if len(imports) < FLAT_LINE_MIN_SLOTS:
        return DetectorResult(
            "flat_line", "Flat-line kWh (possible meter override)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["flat_line"],
            evidence={"reason": "insufficient_samples", "slots": len(imports)},
        )
    mu = _mean(imports) or 0.0
    sd = _stdev(imports) or 0.0
    cv = (sd / mu) if mu > 0 else 0.0
    fired = mu > 0 and cv < FLAT_LINE_CV_MAX
    # Intensity: lower CV = higher score.
    score = max(0.0, 1.0 - cv / FLAT_LINE_CV_MAX) if fired else 0.0
    return DetectorResult(
        detector_id="flat_line",
        label="Flat-line kWh (possible meter override)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["flat_line"],
        severity="high" if fired else "low",
        evidence={
            "window_hours": 48,
            "slots": len(imports),
            "mean_wh_per_slot": round(mu, 3),
            "stdev_wh_per_slot": round(sd, 3),
            "coeff_of_variation": round(cv, 4),
            "cv_threshold": FLAT_LINE_CV_MAX,
        },
    )


# 4. Sudden drop — recent 3-day mean << prior 7-day mean.
SUDDEN_DROP_RATIO = 0.25   # recent < 25% of prior


def detect_sudden_drop(s: MeterSignals) -> DetectorResult:
    recent_start = s.now - timedelta(days=3)
    prior_start = s.now - timedelta(days=10)
    recent = _clean([
        r.import_wh for r in _slice_hh(s.hh, after=recent_start)
    ])
    prior = _clean([
        r.import_wh for r in _slice_hh(s.hh, after=prior_start, before=recent_start)
    ])
    if len(recent) < 20 or len(prior) < 40:
        return DetectorResult(
            "sudden_drop", "Sudden consumption drop (> 75%)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["sudden_drop"],
            evidence={"reason": "insufficient_history"},
        )
    recent_mu = _mean(recent) or 0.0
    prior_mu = _mean(prior) or 0.0
    if prior_mu <= 0:
        return DetectorResult(
            "sudden_drop", "Sudden consumption drop (> 75%)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["sudden_drop"],
            evidence={"reason": "prior_window_zero"},
        )
    ratio = recent_mu / prior_mu
    fired = ratio < SUDDEN_DROP_RATIO
    score = max(0.0, 1.0 - ratio / SUDDEN_DROP_RATIO) if fired else 0.0
    return DetectorResult(
        detector_id="sudden_drop",
        label="Sudden consumption drop (> 75%)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["sudden_drop"],
        severity="high" if fired else "low",
        evidence={
            "recent_window_days": 3,
            "prior_window_days": 7,
            "recent_mean_wh_per_slot": round(recent_mu, 3),
            "prior_mean_wh_per_slot": round(prior_mu, 3),
            "ratio": round(ratio, 4),
            "ratio_threshold": SUDDEN_DROP_RATIO,
        },
    )


# 5. Reverse energy on a non-prosumer meter.
# All current meters have net_meter_flag NULL and supply_type 62T (residential
# LT non-prosumer), so we treat any export > threshold as suspicious. A
# future prosumer allow-list should be plumbed through meter.net_meter_flag.
REVERSE_ENERGY_WH_THRESHOLD = 50.0  # total over 7d


def _is_prosumer(m: MeterRoster) -> bool:
    flag = (m.net_meter_flag or "").strip().upper()
    return flag in {"Y", "YES", "1", "T", "TRUE"}


def detect_reverse_energy(s: MeterSignals) -> DetectorResult:
    if _is_prosumer(s.meter):
        return DetectorResult(
            "reverse_energy", "Reverse energy on non-prosumer meter",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["reverse_energy"],
            evidence={"reason": "meter_is_prosumer"},
        )
    window = _slice_hh(s.hh, after=s.now - timedelta(days=7))
    total_export = sum(r.export_wh or 0.0 for r in window)
    fired = total_export > REVERSE_ENERGY_WH_THRESHOLD
    # Intensity: 0.5 floor for any fire, +0.5 once total_export ≥ 1 kWh.
    score = min(1.0, 0.5 + total_export / 1000.0) if fired else 0.0
    return DetectorResult(
        detector_id="reverse_energy",
        label="Reverse energy on non-prosumer meter",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["reverse_energy"],
        severity="critical" if fired else "low",
        evidence={
            "total_export_wh_7d": round(total_export, 2),
            "threshold_wh": REVERSE_ENERGY_WH_THRESHOLD,
            "slots_with_export": sum(1 for r in window if (r.export_wh or 0) > 0),
        },
    )


# 6. Peer z-score — daily kWh much lower than same-meter_type peers.
PEER_Z_THRESHOLD = -2.0


def detect_peer_zscore(s: MeterSignals) -> DetectorResult:
    # Own 7-day daily-kWh mean.
    own = _clean([
        (r.import_wh or 0) / 1000.0
        for r in _slice_daily(s.daily, after=s.now - timedelta(days=7))
    ])
    if len(own) < 3:
        return DetectorResult(
            "peer_zscore", "Far below peer-group consumption",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["peer_zscore"],
            evidence={"reason": "insufficient_own_history"},
        )
    own_mean = _mean(own) or 0.0
    mtype = s.meter.meter_type or "_unknown"
    peer_mu = s.peer.daily_kwh_mean.get(mtype)
    peer_sd = s.peer.daily_kwh_stdev.get(mtype)
    peer_n = s.peer.sample_size.get(mtype, 0)
    if peer_mu is None or peer_sd in (None, 0.0) or peer_n < 5:
        return DetectorResult(
            "peer_zscore", "Far below peer-group consumption",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["peer_zscore"],
            evidence={"reason": "peer_baseline_missing", "meter_type": mtype},
        )
    z = (own_mean - peer_mu) / peer_sd
    fired = z < PEER_Z_THRESHOLD
    score = min(1.0, abs(z) / abs(PEER_Z_THRESHOLD) - 1.0) if fired else 0.0
    return DetectorResult(
        detector_id="peer_zscore",
        label="Far below peer-group consumption",
        fired=fired,
        score=max(0.0, score),
        weight=DETECTOR_WEIGHTS["peer_zscore"],
        severity="medium" if fired else "low",
        evidence={
            "meter_type": mtype,
            "own_mean_kwh": round(own_mean, 3),
            "peer_mean_kwh": round(peer_mu, 3),
            "peer_stdev_kwh": round(peer_sd, 3),
            "peer_sample_size": peer_n,
            "z_score": round(z, 3),
            "z_threshold": PEER_Z_THRESHOLD,
        },
    )


# 7. Week-over-week drop > 50%.
WOW_DROP_THRESHOLD = 0.50


def detect_week_over_week(s: MeterSignals) -> DetectorResult:
    this_week = _clean([
        r.import_wh for r in _slice_daily(s.daily, after=s.now - timedelta(days=7))
    ])
    prior_week = _clean([
        r.import_wh for r in _slice_daily(
            s.daily, after=s.now - timedelta(days=14), before=s.now - timedelta(days=7),
        )
    ])
    if len(this_week) < 4 or len(prior_week) < 4:
        return DetectorResult(
            "week_over_week", "Week-over-week consumption drop",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["week_over_week"],
            evidence={"reason": "insufficient_weekly_history"},
        )
    this_sum = sum(this_week)
    prior_sum = sum(prior_week)
    if prior_sum <= 0:
        return DetectorResult(
            "week_over_week", "Week-over-week consumption drop",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["week_over_week"],
            evidence={"reason": "prior_week_zero"},
        )
    drop = 1.0 - (this_sum / prior_sum)
    fired = drop > WOW_DROP_THRESHOLD
    score = min(1.0, drop) if fired else 0.0
    return DetectorResult(
        detector_id="week_over_week",
        label="Week-over-week consumption drop",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["week_over_week"],
        severity="medium" if fired else "low",
        evidence={
            "this_week_kwh": round(this_sum / 1000.0, 3),
            "prior_week_kwh": round(prior_sum / 1000.0, 3),
            "drop_fraction": round(drop, 4),
            "drop_threshold": WOW_DROP_THRESHOLD,
        },
    )


# 8. Per-phase current imbalance (3P / LTCT / HTCT).
PHASE_IMBALANCE_RATIO = 3.0   # max(I)/min(I) > 3 for > 20% of slots


def detect_phase_imbalance(s: MeterSignals) -> DetectorResult:
    window = _slice_hh(s.hh, after=s.now - timedelta(days=1))
    ir = [(r.i_r, r.i_y, r.i_b) for r in window if r.i_r is not None and r.i_y is not None and r.i_b is not None]
    if len(ir) < 20:
        return DetectorResult(
            "phase_imbalance", "Phase current imbalance (CT/phase bypass)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["phase_imbalance"],
            evidence={"reason": "no_per_phase_data", "slots": len(ir)},
        )
    breaches = 0
    worst_ratio = 0.0
    for a, b, c in ir:
        hi = max(a, b, c)
        lo = min(a, b, c)
        # Treat lo=0 with hi>0 as a full phase zeroed — maximum ratio.
        if hi > 0 and lo == 0:
            breaches += 1
            worst_ratio = max(worst_ratio, float("inf"))
            continue
        if lo > 0:
            ratio = hi / lo
            worst_ratio = max(worst_ratio, ratio)
            if ratio > PHASE_IMBALANCE_RATIO:
                breaches += 1
    breach_frac = breaches / len(ir)
    fired = breach_frac > 0.20
    score = min(1.0, breach_frac * 2.0) if fired else 0.0
    # Don't serialise infinities into JSONB.
    worst_display = worst_ratio if worst_ratio != float("inf") else 9999.0
    return DetectorResult(
        detector_id="phase_imbalance",
        label="Phase current imbalance (CT / phase bypass)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["phase_imbalance"],
        severity="high" if fired else "low",
        evidence={
            "window_hours": 24,
            "slots": len(ir),
            "breach_slots": breaches,
            "breach_fraction": round(breach_frac, 3),
            "worst_ratio": round(worst_display, 2),
            "ratio_threshold": PHASE_IMBALANCE_RATIO,
        },
    )


# 9. MD collapse — historical MD was high, recent MD is tiny.
MD_COLLAPSE_RATIO = 0.30   # recent max MD < 30% of 30-day max


def detect_md_collapse(s: MeterSignals) -> DetectorResult:
    thirty = _slice_daily(s.daily, after=s.now - timedelta(days=30))
    recent = _slice_daily(s.daily, after=s.now - timedelta(days=3))
    all_md = [r.md_w for r in thirty if r.md_w is not None and r.md_w > 0]
    rec_md = [r.md_w for r in recent if r.md_w is not None and r.md_w > 0]
    if len(all_md) < 10:
        return DetectorResult(
            "md_collapse", "Maximum-demand collapse (MD tamper)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["md_collapse"],
            evidence={"reason": "insufficient_md_history"},
        )
    hist_max = max(all_md)
    rec_max = max(rec_md) if rec_md else 0.0
    ratio = (rec_max / hist_max) if hist_max > 0 else 1.0
    fired = ratio < MD_COLLAPSE_RATIO and hist_max > 500.0  # > 0.5 kW baseline
    score = max(0.0, 1.0 - ratio / MD_COLLAPSE_RATIO) if fired else 0.0
    return DetectorResult(
        detector_id="md_collapse",
        label="Maximum-demand collapse (MD tamper)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["md_collapse"],
        severity="medium" if fired else "low",
        evidence={
            "historical_max_md_w": round(hist_max, 2),
            "recent_max_md_w": round(rec_max, 2),
            "ratio": round(ratio, 4),
            "ratio_threshold": MD_COLLAPSE_RATIO,
        },
    )


# 10. Load-factor collapse — MD still high but average consumption tiny.
#     Indicative of partial-bypass where MD register continues to read while
#     kWh register is diverted.
LOAD_FACTOR_THRESHOLD = 0.05


def detect_load_factor_collapse(s: MeterSignals) -> DetectorResult:
    recent = _slice_daily(s.daily, after=s.now - timedelta(days=7))
    if len(recent) < 4:
        return DetectorResult(
            "load_factor_collapse", "Load-factor collapse",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["load_factor_collapse"],
            evidence={"reason": "insufficient_history"},
        )
    md_vals = [r.md_w for r in recent if r.md_w is not None and r.md_w > 0]
    kwh_vals = [(r.import_wh or 0) / 1000.0 for r in recent]
    if not md_vals or not kwh_vals:
        return DetectorResult(
            "load_factor_collapse", "Load-factor collapse",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["load_factor_collapse"],
            evidence={"reason": "no_md_or_kwh"},
        )
    avg_md_kw = _mean(md_vals) / 1000.0  # Watts → kW
    avg_daily_kwh = _mean(kwh_vals) or 0.0
    # Load factor = avg_kw / peak_kw = (daily_kwh/24) / MD_kw
    avg_kw = avg_daily_kwh / 24.0
    if avg_md_kw <= 0:
        lf = 1.0
    else:
        lf = avg_kw / avg_md_kw
    # Require a non-trivial MD to avoid flagging idle residential meters.
    fired = lf < LOAD_FACTOR_THRESHOLD and avg_md_kw > 0.5
    score = max(0.0, 1.0 - lf / LOAD_FACTOR_THRESHOLD) if fired else 0.0
    return DetectorResult(
        detector_id="load_factor_collapse",
        label="Load-factor collapse (MD high, kWh low)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["load_factor_collapse"],
        severity="medium" if fired else "low",
        evidence={
            "avg_md_kw": round(avg_md_kw, 3),
            "avg_daily_kwh": round(avg_daily_kwh, 3),
            "load_factor": round(lf, 4),
            "lf_threshold": LOAD_FACTOR_THRESHOLD,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# 11. Partial bypass — sustained 30–60% kWh drop vs 14-day baseline with
#     the meter still reporting activity. Distinguishes from `sudden_drop`
#     (which requires >75% drop) by catching the subtler "shunt around part
#     of the load" pattern that's invisible to single-threshold detectors.
# ──────────────────────────────────────────────────────────────────────
PARTIAL_BYPASS_DROP_MIN = 0.30
PARTIAL_BYPASS_DROP_MAX = 0.60


def detect_partial_bypass(s: MeterSignals) -> DetectorResult:
    recent_start = s.now - timedelta(days=3)
    prior_start = s.now - timedelta(days=14)
    recent = _clean([r.import_wh for r in _slice_hh(s.hh, after=recent_start)])
    prior = _clean([r.import_wh for r in _slice_hh(s.hh, after=prior_start, before=recent_start)])
    if len(recent) < 20 or len(prior) < 60:
        return DetectorResult(
            "partial_bypass", "Partial bypass (sustained 30–60% kWh drop)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["partial_bypass"],
            evidence={"reason": "insufficient_history"},
        )
    recent_mu = _mean(recent) or 0.0
    prior_mu = _mean(prior) or 0.0
    if prior_mu <= 0:
        return DetectorResult(
            "partial_bypass", "Partial bypass (sustained 30–60% kWh drop)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["partial_bypass"],
            evidence={"reason": "prior_window_zero"},
        )
    drop = 1.0 - (recent_mu / prior_mu)
    # Still-active guard: the meter must be reporting a non-trivial stream
    # (recent mean > 10% of prior) — otherwise this is a full-bypass / vacancy
    # pattern, not a partial shunt.
    still_active = recent_mu > prior_mu * 0.10
    fired = PARTIAL_BYPASS_DROP_MIN <= drop <= PARTIAL_BYPASS_DROP_MAX and still_active
    # Intensity peaks mid-band (45% drop) and fades toward the edges.
    mid = (PARTIAL_BYPASS_DROP_MIN + PARTIAL_BYPASS_DROP_MAX) / 2.0
    half = (PARTIAL_BYPASS_DROP_MAX - PARTIAL_BYPASS_DROP_MIN) / 2.0
    score = max(0.0, 1.0 - abs(drop - mid) / half) if fired else 0.0
    return DetectorResult(
        detector_id="partial_bypass",
        label="Partial bypass (sustained 30–60% kWh drop)",
        fired=fired,
        score=score,
        weight=DETECTOR_WEIGHTS["partial_bypass"],
        severity="high" if fired else "low",
        evidence={
            "recent_window_days": 3,
            "prior_window_days": 11,
            "recent_mean_wh_per_slot": round(recent_mu, 3),
            "prior_mean_wh_per_slot": round(prior_mu, 3),
            "drop_fraction": round(drop, 4),
            "drop_band": [PARTIAL_BYPASS_DROP_MIN, PARTIAL_BYPASS_DROP_MAX],
            "still_active": still_active,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# 12. Full bypass — ≥70% kWh drop while the meter is still online (last_seen
#     within 48h). Distinct from `flat_line` which looks at intra-window
#     variance; this one compares recent to prior. Critical severity.
# ──────────────────────────────────────────────────────────────────────
FULL_BYPASS_DROP_THRESHOLD = 0.70
FULL_BYPASS_MIN_PRIOR_WH_PER_SLOT = 50.0  # was a live consumer, not dormant


def detect_full_bypass(s: MeterSignals) -> DetectorResult:
    recent_start = s.now - timedelta(days=3)
    prior_start = s.now - timedelta(days=14)
    recent = _clean([r.import_wh for r in _slice_hh(s.hh, after=recent_start)])
    prior = _clean([r.import_wh for r in _slice_hh(s.hh, after=prior_start, before=recent_start)])
    if len(recent) < 20 or len(prior) < 60:
        return DetectorResult(
            "full_bypass", "Full bypass (>70% kWh drop, meter still online)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["full_bypass"],
            evidence={"reason": "insufficient_history"},
        )
    recent_mu = _mean(recent) or 0.0
    prior_mu = _mean(prior) or 0.0
    if prior_mu < FULL_BYPASS_MIN_PRIOR_WH_PER_SLOT:
        return DetectorResult(
            "full_bypass", "Full bypass (>70% kWh drop, meter still online)",
            fired=False, score=0.0, weight=DETECTOR_WEIGHTS["full_bypass"],
            evidence={"reason": "prior_too_low", "prior_mean_wh": round(prior_mu, 3)},
        )
    drop = 1.0 - (recent_mu / prior_mu)
    # The "still online" guard leans on the fact that HH readings are arriving
    # at all — if the HH stream dried up, flat_line / comm_health handle it.
    # We require at least one reading in the last 24h.
    last_ts = max((r.ts for r in s.hh if r.ts is not None), default=None)
    meter_online = last_ts is not None and (s.now - last_ts) < timedelta(hours=24)
    fired = drop >= FULL_BYPASS_DROP_THRESHOLD and meter_online
    score = max(0.0, (drop - FULL_BYPASS_DROP_THRESHOLD) / (1.0 - FULL_BYPASS_DROP_THRESHOLD)) if fired else 0.0
    return DetectorResult(
        detector_id="full_bypass",
        label="Full bypass (>70% kWh drop, meter still online)",
        fired=fired,
        score=min(1.0, score),
        weight=DETECTOR_WEIGHTS["full_bypass"],
        severity="critical" if fired else "low",
        evidence={
            "recent_window_days": 3,
            "prior_window_days": 11,
            "recent_mean_wh_per_slot": round(recent_mu, 3),
            "prior_mean_wh_per_slot": round(prior_mu, 3),
            "drop_fraction": round(drop, 4),
            "drop_threshold": FULL_BYPASS_DROP_THRESHOLD,
            "meter_online": meter_online,
            "last_reading_ts": last_ts.isoformat() if last_ts else None,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────

Detector = Callable[[MeterSignals], DetectorResult]

ALL_DETECTORS: List[Detector] = [
    detect_tamper_event,
    detect_time_tampering,
    detect_flat_line,
    detect_sudden_drop,
    detect_reverse_energy,
    detect_peer_zscore,
    detect_week_over_week,
    detect_phase_imbalance,
    detect_md_collapse,
    detect_load_factor_collapse,
    detect_partial_bypass,
    detect_full_bypass,
]


def run_all(signals: MeterSignals) -> List[DetectorResult]:
    return [d(signals) for d in ALL_DETECTORS]


__all__ = [
    "DETECTOR_WEIGHTS",
    "ALL_DETECTORS",
    "PeerBaseline",
    "MeterSignals",
    "DetectorResult",
    "run_all",
]
