"""Theft-analysis evaluation harness against simulator ground truth.

Reads the simulator's ``{serial, type, reduction}`` truth list (either from
``GET $SIMULATOR_BASE_URL/theft/active`` or from a JSON file) and compares
it against the persisted ``theft_score`` rows in Polaris EMS. Produces:

  • overall binary confusion matrix at a configurable score threshold
  • precision / recall / F1
  • per-theft-type recall (grouped: was this pattern caught?)
  • per-detector precision (when this detector fires, how often is it a
    true positive?)

Usage (inside the backend container):

    python scripts/theft_eval.py \\
        --truth /tmp/theft_truth.json  \\   # or omit and set SIMULATOR_BASE_URL
        --threshold 20                 \\   # medium+ counts as "flagged"

Truth file format (matches simulator /theft/active):
    {"success": true, "data": [{"serial": "...", "type": "...", "reduction": 0.x}, ...]}
or just the list part:
    [{"serial": "...", "type": "...", "reduction": 0.x}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set

# Make the app importable when run as `python scripts/theft_eval.py`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import SessionLocal  # noqa: E402
from app.models.theft import TheftScore  # noqa: E402


# Map simulator theft_type → set of detector_ids we expect to fire. A
# detector outside this set still counts as a positive signal for the
# binary metric, it just won't count towards per-pattern recall.
EXPECTED_DETECTORS: Dict[str, Set[str]] = {
    "magnetic_tamper":          {"tamper_event"},
    "ct_bypass":                {"tamper_event", "sudden_drop", "load_factor_collapse"},
    "meter_bypass":             {"tamper_event", "sudden_drop", "flat_line"},
    "meter_bypass_full":        {"tamper_event", "sudden_drop", "flat_line"},
    "meter_bypass_partial":     {"tamper_event", "peer_zscore"},
    "phase_bypass":             {"phase_imbalance", "tamper_event"},
    "reverse_polarity":         {"tamper_event"},
    "neutral_disturbance":      {"tamper_event"},
    "meter_factor_manipulation": {"peer_zscore", "flat_line"},
    "load_hooking":             set(),   # ghost load on DTR, untestable meter-side
    "reverse_energy":           {"reverse_energy", "tamper_event"},
    "flat_line":                {"flat_line"},
    "sudden_drop":              {"sudden_drop"},
    "ct_ratio_manipulation":    {"peer_zscore", "md_collapse"},
    "tod_manipulation":         {"peer_zscore"},
    "time_tampering":           {"time_tampering"},
    "md_tamper":                {"md_collapse"},
    "night_shift":              {"peer_zscore"},
    "day_shift":                {"peer_zscore"},
    "cover_opening":            {"tamper_event"},
}


def load_truth(
    path: Optional[str],
    url: Optional[str],
    db_url: Optional[str],
) -> List[Dict]:
    """Return a list of {serial, type, reduction} dicts.

    Priority: --truth file > --url simulator API > --db-url simulator DB.
    """
    if path:
        with open(path, "r") as f:
            data = json.load(f)
    elif url:
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    elif db_url:
        from sqlalchemy import create_engine, text
        eng = create_engine(db_url)
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT serial, theft_type, theft_reduction_factor "
                "FROM meters WHERE theft_active = true"
            )).fetchall()
        data = [
            {"serial": r[0], "type": r[1], "reduction": float(r[2] or 1.0)}
            for r in rows
        ]
    else:
        raise SystemExit(
            "need --truth <file>, --url <simulator-http>, or --db-url <simulator-db>"
        )
    # Accept either the wrapped {success, data: [...]} or the bare list.
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        raise SystemExit(f"unexpected truth format: {type(data).__name__}")
    return data


def fmt_pct(num: float, den: float) -> str:
    return f"{(100.0 * num / den):5.1f}%" if den else "  —  "


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", help="JSON file with simulator truth")
    ap.add_argument("--url", default=os.getenv("SIMULATOR_BASE_URL"),
                    help="override: fetch from <URL>/theft/active")
    ap.add_argument("--db-url", default=os.getenv("SIMULATOR_DB_URL"),
                    help="SQLAlchemy URL for the simulator's own DB "
                         "(e.g. postgresql://simulator:sim@host:5433/simulator) — "
                         "reads 'meters WHERE theft_active = true'")
    ap.add_argument("--threshold", type=float, default=20.0,
                    help="score ≥ threshold counts as flagged")
    args = ap.parse_args()

    url = args.url + "/theft/active" if args.url and not args.url.endswith("/theft/active") else args.url
    truth = load_truth(args.truth, url, args.db_url)

    # {serial: type} for all theft-active meters in simulator.
    truth_map: Dict[str, str] = {
        row["serial"]: row.get("type") or row.get("theft_type") or "unknown"
        for row in truth
    }
    true_pos_meters = set(truth_map.keys())

    # Load current Polaris scores.
    with SessionLocal() as s:
        rows = s.query(TheftScore).all()
        scored = {
            r.device_identifier: {
                "score": r.score,
                "tier": r.risk_tier,
                "fired": set(r.fired_detectors or []),
            }
            for r in rows
        }

    all_meters = set(scored.keys())
    truth_in_scope = true_pos_meters & all_meters

    # Binary confusion matrix.
    tp = fp = tn = fn = 0
    for mid, info in scored.items():
        predicted_positive = info["score"] >= args.threshold
        actual_positive = mid in true_pos_meters
        if predicted_positive and actual_positive: tp += 1
        elif predicted_positive and not actual_positive: fp += 1
        elif not predicted_positive and actual_positive: fn += 1
        else: tn += 1
    # Truth meters NOT in scope (simulator has a serial we don't score).
    unmatched_truth = true_pos_meters - all_meters

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    print(f"\n══ Theft-analysis evaluation @ score ≥ {args.threshold} ══")
    print(f"  simulator-positive meters: {len(true_pos_meters)} "
          f"({len(truth_in_scope)} in scope, {len(unmatched_truth)} unmatched)")
    print(f"  polaris-scored meters:     {len(all_meters)}")
    print()
    print(f"  ┌───────────────┬──────────┬──────────┐")
    print(f"  │               │ actual + │ actual - │")
    print(f"  ├───────────────┼──────────┼──────────┤")
    print(f"  │ predicted  +  │  TP {tp:4d} │  FP {fp:4d} │")
    print(f"  │ predicted  -  │  FN {fn:4d} │  TN {tn:4d} │")
    print(f"  └───────────────┴──────────┴──────────┘")
    print(f"  precision = {precision:.3f}")
    print(f"  recall    = {recall:.3f}")
    print(f"  F1        = {f1:.3f}")

    # Per-theft-type recall.
    print("\n── per-theft-type recall ──")
    by_type_total: Counter = Counter()
    by_type_caught: Counter = Counter()
    by_type_detector_hits: Dict[str, Counter] = defaultdict(Counter)
    for mid, t in truth_map.items():
        if mid not in scored:
            continue
        by_type_total[t] += 1
        info = scored[mid]
        if info["score"] >= args.threshold:
            by_type_caught[t] += 1
        for d in info["fired"]:
            by_type_detector_hits[t][d] += 1

    print(f"  {'theft_type':28} {'caught':>10} {'total':>6}  top detectors")
    for t in sorted(by_type_total, key=lambda x: -by_type_total[x]):
        total = by_type_total[t]
        caught = by_type_caught[t]
        dets = by_type_detector_hits[t].most_common(3)
        dets_s = ", ".join(f"{k}×{v}" for k, v in dets) or "—"
        print(f"  {t:28} {caught:>3} / {total:<3} {fmt_pct(caught, total)}  {dets_s}")

    # Per-detector precision — among all meters where a detector fired,
    # what fraction were true positives?
    print("\n── per-detector precision ──")
    det_fp: Counter = Counter()
    det_tp: Counter = Counter()
    for mid, info in scored.items():
        is_actual = mid in true_pos_meters
        for d in info["fired"]:
            if is_actual: det_tp[d] += 1
            else:         det_fp[d] += 1
    all_dets = sorted(set(det_tp) | set(det_fp))
    print(f"  {'detector':26} {'tp':>4} {'fp':>4}  precision")
    for d in all_dets:
        tp_ = det_tp[d]; fp_ = det_fp[d]; tot = tp_ + fp_
        print(f"  {d:26} {tp_:>4} {fp_:>4}  {fmt_pct(tp_, tot)}")

    # Misses worth investigating.
    if fn:
        print("\n── missed positives (score < threshold but simulator says theft) ──")
        for mid in list(truth_in_scope)[:20]:
            s = scored[mid]
            if s["score"] < args.threshold:
                print(f"  {mid:18} score={s['score']:5.1f} type={truth_map[mid]:24} "
                      f"fired={sorted(s['fired'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
