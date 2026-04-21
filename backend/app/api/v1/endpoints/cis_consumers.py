"""CIS consumer + site-type tag endpoints — Alert Management.

    GET    /api/v1/cis/consumers              — list (MDMS CIS + local tags)
    GET    /api/v1/cis/consumers/count        — total matching count
    GET    /api/v1/cis/consumers/feeders      — distinct feeder codes
    GET    /api/v1/cis/consumers/stats        — counts by site_type
    GET    /api/v1/cis/tags                   — list all locally tagged consumers
    PUT    /api/v1/cis/tags/{meter_serial}    — create / update a tag
    DELETE /api/v1/cis/tags/{meter_serial}    — remove a tag

The list endpoint merges MDMS CIS consumer master data with any local
``consumer_tag`` row so a consumer can be shown as e.g. a hospital even
though MDMS has no such classification field.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import (
    P_ALARM_CONFIGURE,
    require_permission,
)
from app.db.base import get_db
from app.models.consumer_tag import SITE_TYPES, ConsumerTag
from app.models.user import User
from app.services import mdms_cis_client as cis

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────


class ConsumerOut(BaseModel):
    account_id: str
    consumer_name: str
    meter_serial: str
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    supply_type: Optional[str] = None
    meter_category: Optional[str] = None
    feeder_code: Optional[str] = None
    feeder_name: Optional[str] = None
    dtr_code: Optional[str] = None
    dtr_name: Optional[str] = None
    substation_code: Optional[str] = None
    substation_name: Optional[str] = None
    is_vip: bool = False
    consumer_type: Optional[str] = None
    site_type: str = "residential"  # from local consumer_tag (or default)


class ConsumerListOut(BaseModel):
    total: int
    count: int
    items: List[ConsumerOut]
    source: str  # "mdms" | "mdms+local" | "local-only"


class TagIn(BaseModel):
    site_type: str = Field(..., description="One of SITE_TYPES")
    account_id: Optional[str] = None
    consumer_name: Optional[str] = None
    notes: Optional[str] = None


class TagOut(BaseModel):
    meter_serial: str
    site_type: str
    account_id: Optional[str]
    consumer_name: Optional[str]
    notes: Optional[str]
    tagged_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    by_site_type: dict  # {site_type: count}
    total_tagged: int
    mdms_total: int


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/consumers", response_model=ConsumerListOut)
def list_cis_consumers(
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
    feeder_code: Optional[str] = Query(None),
    dtr_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    site_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ConsumerListOut:
    # Fetch CIS rows (remote)
    remote = cis.list_consumers(
        limit=limit, offset=offset, feeder_code=feeder_code, dtr_code=dtr_code, search=search
    )
    total = cis.count_consumers(feeder_code=feeder_code, dtr_code=dtr_code, search=search)
    source = "mdms" if remote else "local-only"

    # Fetch matching local tags keyed by meter_serial
    serials = [c.meter_serial for c in remote if c.meter_serial]
    tag_map: dict = {}
    if serials:
        tag_rows = db.query(ConsumerTag).filter(ConsumerTag.meter_serial.in_(serials)).all()
        tag_map = {t.meter_serial: t for t in tag_rows}
        if tag_map:
            source = "mdms+local"

    items: List[ConsumerOut] = []
    for c in remote:
        t = tag_map.get(c.meter_serial)
        item_site = (t.site_type if t else None) or "residential"
        if site_type and item_site != site_type:
            continue
        items.append(
            ConsumerOut(
                account_id=c.account_id,
                consumer_name=c.consumer_name,
                meter_serial=c.meter_serial,
                mobile_number=c.mobile_number,
                email=c.email,
                supply_type=c.supply_type,
                meter_category=c.meter_category,
                feeder_code=c.feeder_code,
                feeder_name=c.feeder_name,
                dtr_code=c.dtr_code,
                dtr_name=c.dtr_name,
                substation_code=c.substation_code,
                substation_name=c.substation_name,
                is_vip=c.is_vip,
                consumer_type=c.consumer_type,
                site_type=item_site,
            )
        )

    # If site_type filter is set and the remote didn't give us any matches,
    # fall back to local tag list so the "hospital" filter still works offline.
    if site_type and not items:
        local_rows = (
            db.query(ConsumerTag)
            .filter(ConsumerTag.site_type == site_type)
            .limit(limit)
            .offset(offset)
            .all()
        )
        items = [
            ConsumerOut(
                account_id=t.account_id or "",
                consumer_name=t.consumer_name or "",
                meter_serial=t.meter_serial,
                mobile_number=None,
                email=None,
                site_type=t.site_type,
            )
            for t in local_rows
        ]
        source = "local-only"
        total = len(items)

    return ConsumerListOut(total=total, count=len(items), items=items, source=source)


@router.get("/consumers/feeders")
def list_cis_feeders(_: User = Depends(get_current_user)):
    rows = cis.list_feeders()
    return {"items": rows, "count": len(rows)}


@router.get("/consumers/stats", response_model=StatsOut)
def consumer_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StatsOut:
    rows = db.query(ConsumerTag.site_type).all()
    counts: dict = {}
    for (st,) in rows:
        counts[st] = counts.get(st, 0) + 1
    mdms_total = cis.count_consumers()
    return StatsOut(by_site_type=counts, total_tagged=sum(counts.values()), mdms_total=mdms_total)


@router.get("/tags", response_model=List[TagOut])
def list_tags(
    site_type: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[TagOut]:
    q = db.query(ConsumerTag)
    if site_type:
        q = q.filter(ConsumerTag.site_type == site_type)
    rows = q.order_by(ConsumerTag.updated_at.desc()).limit(limit).all()
    return [TagOut.model_validate(r) for r in rows]


@router.put("/tags/{meter_serial}", response_model=TagOut)
def upsert_tag(
    meter_serial: str,
    payload: TagIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(P_ALARM_CONFIGURE)),
) -> TagOut:
    if payload.site_type not in SITE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"site_type must be one of {list(SITE_TYPES)}",
        )
    now = datetime.now(timezone.utc)
    row = db.query(ConsumerTag).filter(ConsumerTag.meter_serial == meter_serial).first()
    if row is None:
        row = ConsumerTag(
            meter_serial=meter_serial,
            site_type=payload.site_type,
            account_id=payload.account_id,
            consumer_name=payload.consumer_name,
            notes=payload.notes,
            tagged_by=str(current_user.id),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.site_type = payload.site_type
        if payload.account_id is not None:
            row.account_id = payload.account_id
        if payload.consumer_name is not None:
            row.consumer_name = payload.consumer_name
        if payload.notes is not None:
            row.notes = payload.notes
        row.tagged_by = str(current_user.id)
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return TagOut.model_validate(row)


@router.delete("/tags/{meter_serial}", status_code=204)
def delete_tag(
    meter_serial: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P_ALARM_CONFIGURE)),
):
    row = db.query(ConsumerTag).filter(ConsumerTag.meter_serial == meter_serial).first()
    if row is None:
        return None
    db.delete(row)
    db.commit()
    return None


@router.get("/site-types")
def list_site_types(_: User = Depends(get_current_user)):
    return {"items": list(SITE_TYPES)}
