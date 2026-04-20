"""Virtual-object-group member resolver — spec 018 W4.T3.

Given a :class:`VirtualObjectGroup` row, return the concrete list of
``meter_serial`` values that the group currently expands to. Used by:

* the alarm-rule engine to know which event rows the rule is scoped over,
* the group detail endpoint to show members in the UI,
* ad-hoc ops queries (e.g. bulk disconnect over a feeder group).

The selector is declarative JSON. Supported top-level keys:

``hierarchy``
    Dict of ``{substation_ids | feeder_ids | dtr_ids | meter_serials: [...]}``.
    Inclusive union across the sub-keys (any match wins), then intersected
    with ``filters`` below. When ``hierarchy`` is empty the resolver
    returns every meter in the local ``meters`` table.

``filters``
    Dict of post-filters applied to the meter row. Currently supported:

    * ``meter_status``  — exact-match against ``meters.status``.
    * ``tariff_class``  — placeholder; relies on MDMS read-through, not
                           locally filterable yet, so it's ignored with a
                           debug log.
    * ``meter_serials_exclude`` — explicit exclusion list.

The resolver is intentionally local-DB-first so the rule engine doesn't
need to call MDMS every tick. When the local meter cache is cold (no
meters seeded) callers receive an empty list — the rule engine treats
that as "no-op this tick", which is the right behaviour for dev/demo.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.meter import Feeder, Meter, Transformer
from app.models.virtual_object_group import VirtualObjectGroup

log = logging.getLogger(__name__)


def _normalize_str_list(v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if x is not None]
    return [str(v)]


def resolve_group_members(
    db: Session,
    group: VirtualObjectGroup,
    *,
    limit: Optional[int] = None,
) -> List[str]:
    """Return the ordered list of meter_serials the group matches."""
    selector = dict(group.selector or {})
    hierarchy = dict(selector.get("hierarchy") or {})
    filters = dict(selector.get("filters") or {})

    substation_ids: Set[str] = set(_normalize_str_list(hierarchy.get("substation_ids")))
    feeder_ids: Set[str] = set(_normalize_str_list(hierarchy.get("feeder_ids")))
    dtr_ids: Set[str] = set(_normalize_str_list(hierarchy.get("dtr_ids")))
    meter_serials: Set[str] = set(_normalize_str_list(hierarchy.get("meter_serials")))

    q = db.query(Meter.serial)

    # Hierarchy filters — OR across the non-empty sub-keys.
    serial_ors: List[str] = []
    if meter_serials:
        serial_ors.extend(meter_serials)
    if dtr_ids:
        # Transformer.name acts as external dtr_id in the EMS schema.
        dtr_matches = (
            db.query(Meter.serial)
            .join(Transformer, Meter.transformer_id == Transformer.id)
            .filter(Transformer.name.in_(dtr_ids))
            .all()
        )
        serial_ors.extend([r[0] for r in dtr_matches])
    if feeder_ids:
        feeder_matches = (
            db.query(Meter.serial)
            .join(Transformer, Meter.transformer_id == Transformer.id)
            .join(Feeder, Transformer.feeder_id == Feeder.id)
            .filter(Feeder.name.in_(feeder_ids))
            .all()
        )
        serial_ors.extend([r[0] for r in feeder_matches])
    if substation_ids:
        ss_matches = (
            db.query(Meter.serial)
            .join(Transformer, Meter.transformer_id == Transformer.id)
            .join(Feeder, Transformer.feeder_id == Feeder.id)
            .filter(Feeder.substation.in_(substation_ids))
            .all()
        )
        serial_ors.extend([r[0] for r in ss_matches])

    if hierarchy:
        # Caller provided at least one hierarchy constraint — apply the OR.
        result_serials: Iterable[str] = sorted(set(serial_ors))
    else:
        # Empty hierarchy → start from every meter.
        rows = q.all()
        result_serials = [r[0] for r in rows]

    # Apply post-filters.
    status_filter = filters.get("meter_status")
    if status_filter:
        # Re-query with the serials set + status.
        subset_rows = (
            db.query(Meter.serial)
            .filter(Meter.serial.in_(list(result_serials)))
            .filter(Meter.status == status_filter)
            .all()
        )
        result_serials = [r[0] for r in subset_rows]

    exclude = set(_normalize_str_list(filters.get("meter_serials_exclude")))
    if exclude:
        result_serials = [s for s in result_serials if s not in exclude]

    if filters.get("tariff_class"):
        log.debug(
            "group_resolver: tariff_class filter ignored (MDMS read-through); "
            "group=%s",
            group.id,
        )

    ordered = sorted(set(result_serials))
    if limit is not None:
        ordered = ordered[:limit]
    return ordered


__all__ = ["resolve_group_members"]
