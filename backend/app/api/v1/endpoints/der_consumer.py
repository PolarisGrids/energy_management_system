"""DER consumer + sub-type catalog endpoints (W5).

Routes mounted under `/der`:

* `GET    /der/types`              — list seeded sub-type taxonomy
* `GET    /der/consumers`          — paginated list with search
* `POST   /der/consumers`          — create
* `GET    /der/consumers/{id}`     — read one
* `PATCH  /der/consumers/{id}`     — update
* `DELETE /der/consumers/{id}`     — soft-delete (status='terminated')
* `GET    /der/consumers/{id}/assets` — list this consumer's DER assets
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import P_DER_COMMAND, P_DER_READ, require_permission
from app.db.base import get_db
from app.models.der_consumer import DERConsumer, DERTypeCatalog
from app.models.der_ems import DERAssetEMS
from app.models.user import User
from app.schemas.der_consumer import (
    DERConsumerCreate,
    DERConsumerOut,
    DERConsumerUpdate,
    DERTypeCatalogOut,
)

router = APIRouter()


# ── Type catalog (read-only) ─────────────────────────────────────────────────


@router.get(
    "/types",
    response_model=List[DERTypeCatalogOut],
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def list_der_types(
    category: Optional[str] = Query(
        None, description="Filter by top-level category (pv/bess/ev/microgrid/wind)"
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(DERTypeCatalog)
    if category:
        q = q.filter(DERTypeCatalog.category == category)
    return q.order_by(DERTypeCatalog.category, DERTypeCatalog.code).all()


# ── Consumer CRUD ────────────────────────────────────────────────────────────


@router.get(
    "/consumers",
    response_model=List[DERConsumerOut],
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def list_consumers(
    search: Optional[str] = Query(None, min_length=1, max_length=80),
    status_: Optional[str] = Query(None, alias="status"),
    tariff_code: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(DERConsumer)
    if status_:
        q = q.filter(DERConsumer.status == status_)
    if tariff_code:
        q = q.filter(DERConsumer.tariff_code == tariff_code)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            or_(
                func.lower(DERConsumer.name).like(like),
                func.lower(DERConsumer.account_no).like(like),
                func.lower(DERConsumer.email).like(like),
            )
        )
    return q.order_by(DERConsumer.name).offset(offset).limit(limit).all()


@router.post(
    "/consumers",
    response_model=DERConsumerOut,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def create_consumer(
    payload: DERConsumerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cid = payload.id or str(uuid.uuid4())
    if db.query(DERConsumer).filter(DERConsumer.id == cid).first():
        raise HTTPException(409, detail="consumer id already exists")
    row = DERConsumer(
        id=cid,
        name=payload.name,
        account_no=payload.account_no,
        email=payload.email,
        phone=payload.phone,
        premise_address=payload.premise_address,
        lat=payload.lat,
        lon=payload.lon,
        tariff_code=payload.tariff_code,
        status=payload.status or "active",
        consumer_metadata=payload.metadata,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=f"constraint violation: {exc.orig}") from exc
    db.refresh(row)
    return row


@router.get(
    "/consumers/{consumer_id}",
    response_model=DERConsumerOut,
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def get_consumer(
    consumer_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERConsumer).filter(DERConsumer.id == consumer_id).first()
    if not row:
        raise HTTPException(404, detail="consumer not found")
    return row


@router.patch(
    "/consumers/{consumer_id}",
    response_model=DERConsumerOut,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def update_consumer(
    consumer_id: str,
    payload: DERConsumerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERConsumer).filter(DERConsumer.id == consumer_id).first()
    if not row:
        raise HTTPException(404, detail="consumer not found")
    data = payload.model_dump(exclude_unset=True)
    if "metadata" in data:
        row.consumer_metadata = data.pop("metadata")
    for k, v in data.items():
        setattr(row, k, v)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=f"constraint violation: {exc.orig}") from exc
    db.refresh(row)
    return row


@router.delete(
    "/consumers/{consumer_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(P_DER_COMMAND))],
)
def delete_consumer(
    consumer_id: str,
    hard: bool = Query(False, description="Hard delete vs soft (status=terminated)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(DERConsumer).filter(DERConsumer.id == consumer_id).first()
    if not row:
        raise HTTPException(404, detail="consumer not found")
    if hard:
        # Detach assets first so we don't violate FK ordering on legacy DBs.
        db.query(DERAssetEMS).filter(DERAssetEMS.consumer_id == consumer_id).update(
            {DERAssetEMS.consumer_id: None}, synchronize_session=False
        )
        db.delete(row)
    else:
        row.status = "terminated"
    db.commit()


@router.get(
    "/consumers/{consumer_id}/assets",
    dependencies=[Depends(require_permission(P_DER_READ))],
)
def list_consumer_assets(
    consumer_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(DERConsumer).filter(DERConsumer.id == consumer_id).first():
        raise HTTPException(404, detail="consumer not found")
    rows = (
        db.query(DERAssetEMS)
        .filter(DERAssetEMS.consumer_id == consumer_id)
        .order_by(DERAssetEMS.type, DERAssetEMS.id)
        .all()
    )
    return [
        {
            "id": a.id,
            "type": a.type,
            "type_code": a.type_code,
            "name": a.name,
            "dtr_id": a.dtr_id,
            "feeder_id": a.feeder_id,
            "capacity_kw": float(a.capacity_kw) if a.capacity_kw is not None else None,
            "capacity_kwh": float(a.capacity_kwh) if a.capacity_kwh is not None else None,
        }
        for a in rows
    ]
