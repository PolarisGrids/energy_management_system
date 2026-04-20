"""GIS outage overlay — spec 018 W3.T7.

    GET /api/v1/gis/outages?bbox=&status=

Returns a GeoJSON FeatureCollection, one Point feature per active outage.
Coordinates are derived from PostGIS ``suspected_fault_point`` when present,
otherwise from the centroid of the first affected transformer's lat/lon.

A separate file (not ``gis.py``) because Agent I owns ``endpoints/gis.py``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.meter import Transformer
from app.models.outage import OutageIncidentW3
from app.models.user import User

log = logging.getLogger(__name__)
router = APIRouter()


def _parse_bbox(bbox: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        return None
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def _incident_point(db: Session, incident: OutageIncidentW3) -> Optional[Tuple[float, float]]:
    """Return (lon, lat) for the incident's rendered marker."""
    # Try PostGIS geometry first.
    try:
        row = db.execute(
            text(
                "SELECT ST_X(suspected_fault_point) AS lon, "
                "ST_Y(suspected_fault_point) AS lat "
                "FROM outage_incident WHERE id = :id"
            ),
            {"id": incident.id},
        ).fetchone()
        if row and row.lon is not None and row.lat is not None:
            return float(row.lon), float(row.lat)
    except Exception:
        # SQLite tests / no PostGIS — fall through.
        pass

    dtr_ids = list(incident.affected_dtr_ids or [])
    if not dtr_ids:
        return None
    dtr_id = dtr_ids[0]
    tx: Optional[Transformer] = None
    try:
        tx = (
            db.query(Transformer)
            .filter(or_(Transformer.name == dtr_id, Transformer.id == _safe_int(dtr_id)))
            .first()
        )
    except Exception:
        tx = db.query(Transformer).filter(Transformer.name == dtr_id).first()
    if tx is None or tx.latitude is None or tx.longitude is None:
        return None
    return float(tx.longitude), float(tx.latitude)


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return -1


def _in_bbox(point: Tuple[float, float], bbox: Tuple[float, float, float, float]) -> bool:
    lon, lat = point
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)


@router.get("/outages")
def gis_outage_overlay(
    bbox: Optional[str] = Query(
        None, description="min_lon,min_lat,max_lon,max_lat (WGS84)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status (defaults to open incidents only)"
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(OutageIncidentW3)
    if status:
        q = q.filter(OutageIncidentW3.status == status.upper())
    else:
        q = q.filter(OutageIncidentW3.status.in_(("DETECTED", "INVESTIGATING", "DISPATCHED")))
    bbox_tuple = _parse_bbox(bbox)

    features: List[dict] = []
    for inc in q.all():
        point = _incident_point(db, inc)
        if point is None:
            continue
        if bbox_tuple and not _in_bbox(point, bbox_tuple):
            continue
        lon, lat = point
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": inc.id,
                    "status": inc.status,
                    "affected_meter_count": inc.affected_meter_count,
                    "restored_meter_count": inc.restored_meter_count,
                    "confidence_pct": (
                        float(inc.confidence_pct) if inc.confidence_pct is not None else None
                    ),
                    "opened_at": _iso(inc.opened_at),
                    "closed_at": _iso(inc.closed_at),
                    "affected_dtr_ids": list(inc.affected_dtr_ids or []),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None
