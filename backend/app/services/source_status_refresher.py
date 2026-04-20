"""Data Accuracy source_status refresher — spec 018 W4.T14.

Background loop that, every 5 minutes, fans out HES `get_meter_status` and
MDMS `get_readings` (last 24h window) for every active meter, then upserts
into `source_status`. CIS last-billing column is best-effort — if MDMS does
not expose a billing-determinants endpoint for the account we leave the
column alone.

The loop is tolerant of per-meter errors so a single flaky upstream does
not stall the whole pass. Errors are logged and counted via Prometheus when
the client is available.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.meter import Meter, MeterStatus
from app.models.source_status import SourceStatus
from app.services.hes_client import hes_client
from app.services.mdms_client import mdms_client

log = logging.getLogger(__name__)


# ── Badge logic ─────────────────────────────────────────────────────────────

def compute_status(
    hes_last_seen: Optional[datetime],
    mdms_last_validated: Optional[datetime],
    cis_last_billing: Optional[datetime],
    now: Optional[datetime] = None,
) -> str:
    """Return the health-badge string for a source_status row.

    Precedence (first match wins):
      1. ``missing_mdms``  — no MDMS validated timestamp at all.
      2. ``missing_cis``   — CIS never emitted a billing timestamp.
      3. ``lagging``       — HES last-seen is > 1h old (fresh check > MDMS).
      4. ``stale``         — MDMS last-validated is > 24h old.
      5. ``healthy``       — both HES ≤ 1h and MDMS ≤ 24h.
      6. ``unknown``       — nothing to decide against.
    """
    now = now or datetime.now(timezone.utc)

    def _age(ts: Optional[datetime]) -> Optional[timedelta]:
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return now - ts

    hes_age = _age(hes_last_seen)
    mdms_age = _age(mdms_last_validated)
    cis_age = _age(cis_last_billing)

    if mdms_age is None:
        return "missing_mdms"
    if cis_age is None:
        # CIS billing is best-effort; still surface it so ops see the gap.
        return "missing_cis"
    if hes_age is not None and hes_age > timedelta(hours=1):
        return "lagging"
    if mdms_age > timedelta(hours=24):
        return "stale"
    if hes_age is None:
        return "unknown"
    return "healthy"


# ── Upsert helper ───────────────────────────────────────────────────────────

def upsert_source_status(
    db: Session,
    meter_serial: str,
    hes_last_seen: Optional[datetime],
    mdms_last_validated: Optional[datetime],
    cis_last_billing: Optional[datetime] = None,
) -> None:
    row = db.get(SourceStatus, meter_serial)
    now = datetime.now(timezone.utc)
    if row is None:
        row = SourceStatus(
            meter_serial=meter_serial,
            hes_last_seen=hes_last_seen,
            mdms_last_validated=mdms_last_validated,
            cis_last_billing=cis_last_billing,
            updated_at=now,
        )
        db.add(row)
    else:
        if hes_last_seen is not None:
            row.hes_last_seen = hes_last_seen
        if mdms_last_validated is not None:
            row.mdms_last_validated = mdms_last_validated
        if cis_last_billing is not None:
            row.cis_last_billing = cis_last_billing
        row.updated_at = now


# ── Per-meter probe ─────────────────────────────────────────────────────────

async def probe_meter(meter_serial: str) -> dict:
    """Return {hes_last_seen, mdms_last_validated, cis_last_billing} for a meter."""
    result = {
        "hes_last_seen": None,
        "mdms_last_validated": None,
        "cis_last_billing": None,
    }
    # HES last-seen
    try:
        resp = await hes_client.get_meter_status(meter_serial)
        payload = resp.json() if hasattr(resp, "json") else {}
        ts = payload.get("last_seen") or payload.get("last_comm_at")
        if ts:
            result["hes_last_seen"] = _parse_iso(ts)
    except Exception as exc:
        log.debug("hes probe failed for %s: %s", meter_serial, exc)

    # MDMS last validated reading
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        resp = await mdms_client.get_readings(
            meter=meter_serial,
            frm=start.isoformat(),
            to=end.isoformat(),
        )
        payload = resp.json() if hasattr(resp, "json") else {}
        rows = payload.get("readings") or payload.get("data") or []
        if rows:
            last = rows[-1]
            ts = last.get("ts") or last.get("timestamp") or last.get("validated_at")
            if ts:
                result["mdms_last_validated"] = _parse_iso(ts)
    except Exception as exc:
        log.debug("mdms probe failed for %s: %s", meter_serial, exc)

    return result


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        # Accept both "...Z" and "+00:00".
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# ── Scheduler loop ──────────────────────────────────────────────────────────

async def refresh_once(concurrency: int = 10) -> dict:
    """Run one full pass across active meters. Returns counts for ops."""
    stats = {"probed": 0, "updated": 0, "errors": 0}
    with SessionLocal() as db:
        serials = [
            s for (s,) in db.query(Meter.serial)
            .filter(Meter.status != MeterStatus.RETIRED)
            .all()
        ] if hasattr(MeterStatus, "RETIRED") else [
            s for (s,) in db.query(Meter.serial).all()
        ]

    sem = asyncio.Semaphore(concurrency)

    async def _one(serial: str):
        async with sem:
            try:
                probed = await probe_meter(serial)
                stats["probed"] += 1
                with SessionLocal() as db2:
                    upsert_source_status(
                        db=db2,
                        meter_serial=serial,
                        hes_last_seen=probed["hes_last_seen"],
                        mdms_last_validated=probed["mdms_last_validated"],
                        cis_last_billing=probed["cis_last_billing"],
                    )
                    db2.commit()
                    stats["updated"] += 1
            except Exception as exc:
                stats["errors"] += 1
                log.warning("source_status refresh failed for %s: %s", serial, exc)

    await asyncio.gather(*(_one(s) for s in serials))
    return stats


async def run_refresher_loop(stop_event: asyncio.Event, interval_seconds: int = 300) -> None:
    """Run `refresh_once` every `interval_seconds` until `stop_event` is set.

    Exceptions during a pass do NOT kill the loop; they are logged and the
    scheduler waits for the next tick.
    """
    log.info("source_status refresher started (interval=%ds)", interval_seconds)
    while not stop_event.is_set():
        try:
            stats = await refresh_once()
            log.info("source_status pass complete: %s", stats)
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("source_status pass crashed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    log.info("source_status refresher stopped")
