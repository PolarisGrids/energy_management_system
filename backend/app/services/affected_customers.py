"""Affected-customer derivation for outage incidents — spec 016 US2.

MVP walk: meters are reached via their transformer's feeder_id. For v1
affected_customers equals the number of meter records on the feeder. A
richer walk (service_lines / consumer accounts) is deferred.
    TODO(016-mvp-phase2): use outage_incident_customers snapshot table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.meter import Meter, Transformer


def derive_affected(
    db: Session,
    feeder_id: int,
    at: Optional[datetime] = None,
) -> Tuple[int, list[str]]:
    """Return (count, meter_serials) of meters served by `feeder_id`.

    `at` is accepted for API symmetry but unused in v1 (no historical
    topology). The list is returned alongside the count so callers that want
    to snapshot the affected set can do so without a second query.
    """
    q = (
        db.query(Meter.serial)
        .join(Transformer, Meter.transformer_id == Transformer.id)
        .filter(Transformer.feeder_id == feeder_id)
    )
    serials = [row[0] for row in q.all()]
    return len(serials), serials
