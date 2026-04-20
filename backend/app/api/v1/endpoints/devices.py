"""Unified device search + hierarchy endpoints — spec 018 no-mock-data closure.

Pages like Dashboard, AlarmConsole, DERManagement, OutageManagement (and the
Reports / EnergyMonitoring filter bars) currently carry hardcoded dropdowns
for feeder / DTR / meter / consumer selection. These endpoints replace those
hardcoded arrays with live queries against MDMS CIS + the local EMS inventory
(feeders / transformers / meters table) — de-duplicated by serial / account.

Endpoints
---------
* ``GET /api/v1/devices/search?q=&type=&limit=`` — unified type-ahead search
* ``GET /api/v1/devices/hierarchy?node_id=&level=`` — tree browser
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.meter import Feeder, Meter, Transformer
from app.models.user import User
from app.services.mdms_client import CircuitBreakerError, mdms_client

logger = logging.getLogger(__name__)
router = APIRouter()


ALLOWED_TYPES = {"meter", "consumer", "dtr", "feeder"}


def _mdms_on() -> bool:
    return bool(settings.MDMS_ENABLED)


def _local_feeders(db: Session, q: str, limit: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(Feeder)
        .filter(or_(Feeder.name.ilike(f"%{q}%"), Feeder.substation.ilike(f"%{q}%")))
        .limit(limit)
        .all()
    )
    return [
        {
            "type": "feeder",
            "id": str(f.id),
            "name": f.name,
            "hierarchy_path": f"{f.substation} / {f.name}",
        }
        for f in rows
    ]


def _local_dtrs(db: Session, q: str, limit: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(Transformer, Feeder)
        .outerjoin(Feeder, Feeder.id == Transformer.feeder_id)
        .filter(Transformer.name.ilike(f"%{q}%"))
        .limit(limit)
        .all()
    )
    return [
        {
            "type": "dtr",
            "id": str(t.id),
            "name": t.name,
            "hierarchy_path": f"{(f.substation + ' / ' + f.name) if f else ''} / {t.name}".strip(" /"),
        }
        for t, f in rows
    ]


def _local_meters(db: Session, q: str, limit: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(Meter, Transformer, Feeder)
        .outerjoin(Transformer, Transformer.id == Meter.transformer_id)
        .outerjoin(Feeder, Feeder.id == Transformer.feeder_id)
        .filter(
            or_(
                Meter.serial.ilike(f"%{q}%"),
                Meter.customer_name.ilike(f"%{q}%"),
                Meter.account_number.ilike(f"%{q}%"),
            )
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "type": "meter",
            "id": str(m.id),
            "name": m.customer_name or m.serial,
            "meter_serial": m.serial,
            "account": m.account_number,
            "hierarchy_path": " / ".join(
                filter(None, [f.substation if f else None, f.name if f else None, t.name if t else None, m.serial])
            ),
        }
        for m, t, f in rows
    ]


async def _mdms_consumers(q: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await mdms_client.search_consumers(q, limit=limit)
    except (CircuitBreakerError, Exception) as exc:  # pragma: no cover — network
        logger.warning("MDMS consumer search failed: %s", exc)
        return []
    items = resp.get("items") if isinstance(resp, dict) else None
    if items is None and isinstance(resp, dict):
        items = resp.get("consumers") or resp.get("data") or []
    out: List[Dict[str, Any]] = []
    for c in items or []:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "type": "consumer",
                "id": str(c.get("account_number") or c.get("id") or c.get("consumer_id") or ""),
                "name": c.get("consumer_name") or c.get("name"),
                "meter_serial": c.get("meter_serial") or c.get("meter"),
                "account": c.get("account_number"),
                "hierarchy_path": " / ".join(
                    filter(
                        None,
                        [
                            c.get("division"),
                            c.get("subdivision") or c.get("sub_division"),
                            c.get("feeder"),
                            c.get("dtr") or c.get("transformer"),
                            c.get("meter_serial") or c.get("meter"),
                        ],
                    )
                ),
            }
        )
    return out


@router.get("/search")
async def devices_search(
    q: str = Query(..., min_length=1, description="Search term"),
    type: Optional[str] = Query(None, description="meter | consumer | dtr | feeder"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Unified search across meter / consumer / DTR / feeder.

    Always merges results from MDMS CIS (consumer) + EMS inventory (feeder,
    dtr, meter) and de-dupes by ``(type, id)``. A ``type=`` filter narrows the
    response to one bucket.
    """
    if type is not None and type not in ALLOWED_TYPES:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(ALLOWED_TYPES)}")

    results: List[Dict[str, Any]] = []
    types_to_fetch = {type} if type else ALLOWED_TYPES

    if "consumer" in types_to_fetch and _mdms_on():
        results.extend(await _mdms_consumers(q, limit))
    if "meter" in types_to_fetch:
        results.extend(_local_meters(db, q, limit))
    if "dtr" in types_to_fetch:
        results.extend(_local_dtrs(db, q, limit))
    if "feeder" in types_to_fetch:
        results.extend(_local_feeders(db, q, limit))

    # De-dupe on (type, id). Preserve first occurrence ordering (MDMS-first).
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for item in results:
        key = (item.get("type"), item.get("id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return {
        "ok": True,
        "q": q,
        "type": type,
        "count": len(deduped[:limit]),
        "items": deduped[:limit],
    }


@router.get("/hierarchy")
async def devices_hierarchy(
    node_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None, description="substation | pss | feeder | dtr | meter"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Tree browser — proxies MDMS ``/cis/hierarchy`` when enabled, else
    reconstructs a shallow hierarchy from the local inventory tables.
    """
    if _mdms_on():
        try:
            params: Dict[str, Any] = {}
            if node_id:
                params["node"] = node_id
            if level:
                params["level"] = level
            resp = await mdms_client.get_hierarchy(node=node_id)
            # MDMS returns the tree as-is; wrap with source flag.
            return {"ok": True, "source": "mdms", "tree": resp}
        except (CircuitBreakerError, Exception) as exc:  # pragma: no cover
            logger.warning("MDMS hierarchy call failed, falling back: %s", exc)

    # Local fallback — build a shallow Feeder > Transformer > Meter tree.
    feeders = db.query(Feeder).order_by(Feeder.id).all()
    tree: List[Dict[str, Any]] = []
    for f in feeders:
        node: Dict[str, Any] = {
            "id": f"feeder:{f.id}",
            "name": f.name,
            "level": "feeder",
            "children": [],
        }
        if level != "feeder":
            txs = db.query(Transformer).filter(Transformer.feeder_id == f.id).all()
            for t in txs:
                dtr_node: Dict[str, Any] = {
                    "id": f"dtr:{t.id}",
                    "name": t.name,
                    "level": "dtr",
                    "children": [],
                }
                if level == "meter" or level is None:
                    meters = db.query(Meter).filter(Meter.transformer_id == t.id).limit(500).all()
                    dtr_node["children"] = [
                        {
                            "id": f"meter:{m.id}",
                            "name": m.customer_name or m.serial,
                            "meter_serial": m.serial,
                            "level": "meter",
                        }
                        for m in meters
                    ]
                node["children"].append(dtr_node)
        tree.append(node)
    return {"ok": True, "source": "ems-local", "tree": tree}
