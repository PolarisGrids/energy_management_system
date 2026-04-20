"""Simulator → EMS bootstrap: DER bulk import.

Spec: `repos/simulator/specs/001-ami-full-data-generation/contracts/der-bulk-import.md`
Auth: `Authorization: Bearer <SIMULATOR_API_KEY>` (from Secrets Manager).
Idempotent upsert keyed on `asset.id`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status as http_status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import get_db
from app.models.der_ems import DERAssetEMS
from app.models.meter import Transformer
from app.schemas.der_bulk import (
    DERBulkImportError,
    DERBulkImportRequest,
    DERBulkImportResponse,
)

try:
    from otel_common.audit import audit  # type: ignore
except ImportError:  # pragma: no cover
    async def audit(**_kwargs):
        return None


logger = logging.getLogger(__name__)
router = APIRouter()


def _authenticate_simulator(authorization: str | None) -> None:
    """Validate Bearer token against SIMULATOR_API_KEY.

    If SIMULATOR_API_KEY is unset (e.g. unit tests) we still require *some*
    bearer header so the endpoint isn't inadvertently open.
    """
    expected = settings.SIMULATOR_API_KEY
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Invalid simulator api key")
    if not expected:
        # Dev fallback: only allow the well-known local-dev sentinel so we
        # fail closed in staging/prod if the secret never gets wired up.
        if token != "dev-simulator-token":
            raise HTTPException(
                status_code=401,
                detail="SIMULATOR_API_KEY unconfigured; reject unless dev token",
            )


@router.post(
    "/bulk-import",
    response_model=DERBulkImportResponse,
    status_code=http_status.HTTP_200_OK,
)
async def der_bulk_import(
    payload: DERBulkImportRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Upsert DER assets from simulator preset load."""
    _authenticate_simulator(authorization)

    # Soft DTR validation — known DTR identifiers come from Transformer.name
    # (pre-spec-018 the legacy schema lacks a canonical `code` column).
    # A row is considered valid if the DTR exists OR dtr_id is absent. Missing
    # DTR is a WARNING only (recorded in errors[]), not a hard fail — per T8.5.
    known_dtr_codes: set[str] = set()
    if any(a.dtr_id for a in payload.assets):
        rows = db.query(Transformer.name).all()
        known_dtr_codes = {r[0] for r in rows if r[0]}

    now = datetime.now(timezone.utc)
    errors: list[DERBulkImportError] = []
    inserted = 0
    updated = 0

    # Use on-conflict upsert for idempotency.
    for idx, asset in enumerate(payload.assets):
        if asset.dtr_id and known_dtr_codes and asset.dtr_id not in known_dtr_codes:
            errors.append(
                DERBulkImportError(
                    index=idx,
                    asset_id=asset.id,
                    error_code="DTR_NOT_FOUND",
                    message=f"DTR {asset.dtr_id} not found (warning only)",
                )
            )
        existed = (
            db.query(DERAssetEMS.id).filter(DERAssetEMS.id == asset.id).first() is not None
        )
        stmt = pg_insert(DERAssetEMS.__table__).values(
            id=asset.id,
            type=asset.type,
            name=asset.name,
            dtr_id=asset.dtr_id,
            feeder_id=asset.feeder_id,
            lat=asset.lat,
            lon=asset.lon,
            capacity_kw=asset.capacity_kw,
            capacity_kwh=asset.capacity_kwh,
            metadata=(asset.metadata or None),
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "type": stmt.excluded.type,
                "name": stmt.excluded.name,
                "dtr_id": stmt.excluded.dtr_id,
                "feeder_id": stmt.excluded.feeder_id,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "capacity_kw": stmt.excluded.capacity_kw,
                "capacity_kwh": stmt.excluded.capacity_kwh,
                "metadata": stmt.excluded.metadata,
                "updated_at": now,
            },
        )
        db.execute(stmt)
        if existed:
            updated += 1
        else:
            inserted += 1

    db.commit()

    await audit(
        action_type="WRITE",
        action_name="der_bulk_import",
        entity_type="DERAsset",
        entity_id=f"preset:{payload.preset}",
        request_data={
            "preset": payload.preset,
            "count": len(payload.assets),
            "inserted": inserted,
            "updated": updated,
            "errors": len(errors),
        },
        status=200,
        method="POST",
        path="/api/v1/der/bulk-import",
        user_id="simulator",
    )

    return DERBulkImportResponse(
        inserted=inserted,
        updated=updated,
        errors=errors,
        preset=payload.preset,
    )
