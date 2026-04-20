"""Reverse-flow detector — spec 018 W3.T13.

Background task (started from the FastAPI lifespan) that periodically
computes per-feeder net flow from `der_telemetry` + meter readings and
opens/closes `reverse_flow_event` rows when sustained reverse flow is
observed.

Algorithm:
1. Every `tick_seconds` (default 30 s) compute per-feeder net flow.
   - import_kw: sum of consumer meter active power import for the window
     (best-effort; when meter readings aren't available we treat import
     as 0 so pure DER-export scenarios still trip the detector).
   - export_kw: sum of DER active_power_kw on that feeder for the window.
   - net_flow = import_kw - export_kw  (negative ⇒ reverse flow)
2. Maintain an in-memory "first-observed" timestamp per feeder. When
   net_flow < 0 for >= `sustain_seconds` (default 300 s) with no OPEN row,
   insert a new row.
3. When net_flow >= 0 on a subsequent tick, clear the timestamp and close
   any OPEN rows (set `closed_at`, `duration_s`, `status=CLOSED`).

The detector is intentionally polling-based (not event-driven) so it can
run alongside the existing Kafka consumers without changing their contract.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import text

from app.db.base import SessionLocal
from app.models.reverse_flow import ReverseFlowEvent

logger = logging.getLogger(__name__)


class ReverseFlowDetector:
    """Polls der_telemetry on a fixed cadence and tracks sustained reverse flow."""

    def __init__(self, *, tick_seconds: int = 30, sustain_seconds: int = 300):
        self.tick_seconds = tick_seconds
        self.sustain_seconds = sustain_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        # feeder_id -> timestamp of first observed negative-flow tick
        self._observed: Dict[str, datetime] = {}

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="reverse-flow-detector")
        logger.info(
            "reverse-flow detector started tick=%ds sustain=%ds",
            self.tick_seconds, self.sustain_seconds,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._tick)
            except Exception as exc:  # pragma: no cover
                logger.exception("reverse-flow tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass

    def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(seconds=60)
        db = SessionLocal()
        try:
            # Per-feeder DER export total (active_power_kw sum, last 60 s)
            # Meter import isn't modelled in a single table in this repo yet;
            # the detector treats any feeder with DER export > import_est as
            # candidate-reverse-flow. import_est defaults to 0 when unavailable.
            rows = db.execute(
                text(
                    """
                    SELECT a.feeder_id AS feeder_id,
                           COALESCE(SUM(t.active_power_kw), 0) AS export_kw
                    FROM der_telemetry t
                    JOIN der_asset a ON a.id = t.asset_id
                    WHERE t.ts >= :cutoff AND a.feeder_id IS NOT NULL
                    GROUP BY a.feeder_id
                    """
                ),
                {"cutoff": window_cutoff},
            ).fetchall()

            # For this spec, net_flow = import_est - export_kw. import_est=0
            # for the dev simulation (no meter-ingest endpoint wired). This
            # keeps the logic working and simulator-observable; production
            # will plug the MDMS reading totals here.
            flows: Dict[str, float] = {r[0]: -float(r[1] or 0.0) for r in rows}

            for feeder_id, net in flows.items():
                if net < 0:
                    first_seen = self._observed.get(feeder_id)
                    if first_seen is None:
                        self._observed[feeder_id] = now
                        continue
                    sustained = (now - first_seen).total_seconds()
                    if sustained >= self.sustain_seconds:
                        open_row = (
                            db.query(ReverseFlowEvent)
                            .filter(
                                ReverseFlowEvent.feeder_id == feeder_id,
                                ReverseFlowEvent.status == "OPEN",
                            )
                            .first()
                        )
                        if open_row is None:
                            db.add(
                                ReverseFlowEvent(
                                    feeder_id=feeder_id,
                                    detected_at=first_seen,
                                    net_flow_kw=round(net, 4),
                                    status="OPEN",
                                    details={"sustained_s": int(sustained)},
                                )
                            )
                            db.commit()
                            logger.info(
                                "reverse-flow OPEN feeder=%s net=%.2f kW sustained=%ds",
                                feeder_id, net, int(sustained),
                            )
                else:
                    # Net flow recovered — close any OPEN rows.
                    self._observed.pop(feeder_id, None)
                    open_rows = (
                        db.query(ReverseFlowEvent)
                        .filter(
                            ReverseFlowEvent.feeder_id == feeder_id,
                            ReverseFlowEvent.status == "OPEN",
                        )
                        .all()
                    )
                    for r in open_rows:
                        r.closed_at = now
                        det = r.detected_at
                        if det and det.tzinfo is None:
                            det = det.replace(tzinfo=timezone.utc)
                        r.duration_s = int((now - det).total_seconds()) if det else None
                        r.status = "CLOSED"
                    if open_rows:
                        db.commit()
                        logger.info("reverse-flow CLOSED feeder=%s", feeder_id)
        finally:
            db.close()


# Module-level singleton used by the FastAPI lifespan hook.
detector = ReverseFlowDetector()
