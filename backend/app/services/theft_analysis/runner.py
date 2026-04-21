"""Theft-analysis runner — scores meters, persists to Polaris, loops.

Entry points:

  - :func:`run_once` — run the scorer once, upsert ``theft_score`` rows,
    and append a ``theft_run_log`` entry. Used by the background loop,
    startup back-fill, and the manual ``POST /api/v1/theft/recompute``.
  - :func:`run_refresh_loop` — async loop driven from the FastAPI
    lifespan, ticks every ``THEFT_REFRESH_INTERVAL_SECONDS``.

Persistence uses an UPSERT on Postgres and a delete+insert on SQLite
(tests). No MDMS writes — the MDMS side stays strictly read-only.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.theft import TheftRunLog, TheftScore
from app.services.theft_analysis.scorer import MeterScore, score_all_meters

log = logging.getLogger(__name__)

# Default cadence. Overridable by env THEFT_REFRESH_INTERVAL_SECONDS.
DEFAULT_INTERVAL_SECONDS = 15 * 60


# ──────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────

def _detector_result_to_dict(r: Any) -> Dict[str, Any]:
    """Dataclass → plain dict, JSON-safe."""
    if dataclasses.is_dataclass(r):
        return dataclasses.asdict(r)
    return dict(r) if hasattr(r, "items") else {"value": r}


def _score_to_row(s: MeterScore) -> Dict[str, Any]:
    return {
        "device_identifier": s.device_identifier,
        "meter_type": s.meter_type,
        "account_id": s.account_id,
        "manufacturer": s.manufacturer,
        "sanctioned_load_kw": s.sanctioned_load,
        "score": s.score,
        "risk_tier": s.risk_tier,
        "fired_detectors": list(s.fired_detectors),
        "top_evidence": list(s.top_evidence),
        "detector_results": [_detector_result_to_dict(d) for d in s.detectors],
        "computed_at": s.computed_at,
        "updated_at": datetime.now(timezone.utc),
    }


def persist_scores(session: Session, scores: List[MeterScore]) -> None:
    """Upsert every score into ``theft_score``.

    On Postgres uses ``ON CONFLICT … DO UPDATE``; on SQLite falls back to
    delete-then-insert. Either way a single commit per call.
    """
    if not scores:
        return
    rows = [_score_to_row(s) for s in scores]
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        stmt = pg_insert(TheftScore.__table__).values(rows)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in TheftScore.__table__.columns
            if c.name != "device_identifier"
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["device_identifier"],
            set_=update_cols,
        )
        session.execute(stmt)
    else:  # pragma: no cover — sqlite path for tests
        ids = [r["device_identifier"] for r in rows]
        session.execute(
            delete(TheftScore).where(TheftScore.device_identifier.in_(ids))
        )
        session.bulk_insert_mappings(TheftScore, rows)


def _tier_counts(scores: List[MeterScore]) -> Counter:
    return Counter(s.risk_tier for s in scores)


# ──────────────────────────────────────────────────────────────────────
# One-shot + loop
# ──────────────────────────────────────────────────────────────────────

def run_once(
    *,
    trigger: str = "scheduled",
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Score all meters and persist. Returns a short status dict."""
    owns_session = session is None
    sess = session or SessionLocal()
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    run = TheftRunLog(started_at=started, trigger=trigger)
    sess.add(run)
    sess.flush()  # get run.id

    try:
        scores = score_all_meters(now=started)
        persist_scores(sess, scores)
        tiers = _tier_counts(scores)
        run.meters_scored = len(scores)
        run.meters_critical = int(tiers.get("critical", 0))
        run.meters_high = int(tiers.get("high", 0))
        run.meters_medium = int(tiers.get("medium", 0))
        run.meters_low = int(tiers.get("low", 0))
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        sess.commit()
        log.info(
            "theft runner: scored %d meters in %d ms (trigger=%s) "
            "— %d critical, %d high, %d medium, %d low",
            run.meters_scored, run.duration_ms, trigger,
            run.meters_critical, run.meters_high, run.meters_medium, run.meters_low,
        )
        return {
            "run_id": run.id,
            "meters_scored": run.meters_scored,
            "duration_ms": run.duration_ms,
            "critical": run.meters_critical,
            "high": run.meters_high,
            "medium": run.meters_medium,
            "low": run.meters_low,
            "trigger": trigger,
        }
    except Exception as exc:
        log.exception("theft runner failed")
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        run.error = str(exc)[:500]
        try:
            sess.commit()
        except Exception:
            sess.rollback()
        raise
    finally:
        if owns_session:
            sess.close()


async def run_refresh_loop(
    stop_event: asyncio.Event,
    *,
    interval_seconds: Optional[int] = None,
    run_at_start: bool = True,
) -> None:
    """Background asyncio loop — calls :func:`run_once` every N seconds.

    Runs the blocking scorer on a worker thread (``asyncio.to_thread``) so
    it doesn't stall the event loop. Any exception is logged; the loop
    stays alive so a flaky MDMS pod doesn't kill theft-analysis for good.
    """
    interval = int(
        interval_seconds
        or os.getenv("THEFT_REFRESH_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    )
    trigger_first = "startup"

    if run_at_start:
        try:
            await asyncio.to_thread(run_once, trigger=trigger_first)
        except Exception:
            # logged inside run_once; swallow so loop keeps running.
            pass

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            await asyncio.to_thread(run_once, trigger="scheduled")
        except Exception:
            pass


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "persist_scores",
    "run_once",
    "run_refresh_loop",
]
