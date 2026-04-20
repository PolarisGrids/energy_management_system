"""Reliability-index computation — spec 016 US3 (MVP stub).

`compute_monthly(year_month)` aggregates closed outage_incidents in the
given YYYY-MM window into feeder-level SAIDI / SAIFI / CAIDI / MAIFI rows
and upserts them into `reliability_monthly`.

Definitions (industry standard, condensed):
    SAIDI = Σ(customer·minutes interrupted) / total customers served
    SAIFI = Σ(customer interruptions)        / total customers served
    CAIDI = SAIDI / SAIFI (avg outage duration per interrupted customer)
    MAIFI = Σ(customer momentary interruptions <5 min) / total customers

Incidents with status=CANCELLED are ignored (see spec §Edge cases).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.meter import Meter, Transformer
from app.models.notifications import ReliabilityMonthly
from app.models.outage import OutageIncident, OutageStatus


def _month_bounds(year_month: str) -> Tuple[datetime, datetime]:
    year, month = year_month.split("-")
    y, m = int(year), int(month)
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return start, end


def compute_monthly(db: Session, year_month: str) -> int:
    """Compute + upsert reliability indices per feeder for `year_month`.

    Returns the number of (feeder, year_month) rows written.
    """
    start, end = _month_bounds(year_month)

    # Customers per feeder (for denominator).
    customers_per_feeder = dict(
        db.query(Transformer.feeder_id, func.count(Meter.id))
        .join(Meter, Meter.transformer_id == Transformer.id)
        .group_by(Transformer.feeder_id)
        .all()
    )

    # Outages in window, grouped per feeder.
    incidents = (
        db.query(OutageIncident)
        .filter(
            OutageIncident.started_at >= start,
            OutageIncident.started_at < end,
            OutageIncident.status != OutageStatus.CANCELLED.value,
        )
        .all()
    )

    by_feeder: dict[int, list[OutageIncident]] = {}
    for inc in incidents:
        by_feeder.setdefault(inc.feeder_id, []).append(inc)

    rows_written = 0
    for feeder_id, incs in by_feeder.items():
        total = customers_per_feeder.get(feeder_id) or 0
        if total == 0:
            continue
        customer_minutes = 0.0
        customer_interruptions = 0
        momentary = 0
        for inc in incs:
            ended = inc.restored_at or inc.closed_at
            if ended is None:
                continue
            duration_min = (ended - inc.started_at).total_seconds() / 60.0
            affected = inc.affected_customers or 0
            customer_interruptions += affected
            if duration_min < 5:
                momentary += affected
                continue
            customer_minutes += duration_min * affected

        saidi = customer_minutes / total
        saifi = customer_interruptions / total
        caidi = (saidi / saifi) if saifi > 0 else 0.0
        maifi = momentary / total

        stmt = pg_insert(ReliabilityMonthly).values(
            feeder_id=feeder_id,
            year_month=year_month,
            saidi=saidi,
            saifi=saifi,
            caidi=caidi,
            maifi=maifi,
            total_customers=total,
            computed_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["feeder_id", "year_month"],
            set_={
                "saidi": saidi,
                "saifi": saifi,
                "caidi": caidi,
                "maifi": maifi,
                "total_customers": total,
                "computed_at": datetime.now(timezone.utc),
            },
        )
        db.execute(stmt)
        rows_written += 1

    db.commit()
    return rows_written
