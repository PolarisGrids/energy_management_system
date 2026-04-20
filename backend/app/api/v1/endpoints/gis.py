"""GIS endpoints — /api/v1/gis/layers/* serving RFC 7946 GeoJSON from PostGIS.

Spec 014-gis-postgis (MVP: US1 layers — meters, transformers, feeders, der,
alarms, outage_areas, zones, service_lines, poles).

All geometries are stored in EPSG:4326 with GIST indexes; bbox filtering is
performed server-side via ST_MakeEnvelope + the `&&` operator, with LOD rules
to avoid shipping excessive features at low zoom levels.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.alarm import Alarm
from app.models.der import DERAsset
from app.models.gis import OutageArea, Pole, ServiceLine, Zone
from app.models.meter import Feeder, Meter, Transformer
from app.models.network import NetworkEvent
from app.models.user import User
from app.services.geojson_serializer import (
    DEFAULT_MAX_FEATURES,
    raw_features,
    rows_to_featurecollection,
)

router = APIRouter()


def parse_bbox(bbox: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minlon,minlat,maxlon,maxlat")
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numeric")
    return vals  # type: ignore[return-value]


def bbox_filter(query, geom_col, bbox: Optional[Tuple[float, float, float, float]]):
    if bbox is None:
        return query
    minlon, minlat, maxlon, maxlat = bbox
    envelope = text("ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)").bindparams(
        minlon=minlon, minlat=minlat, maxlon=maxlon, maxlat=maxlat,
    )
    return query.filter(geom_col.ST_Intersects(envelope))


# ---------------------------------------------------------------------------
# Property builders
# ---------------------------------------------------------------------------

def _meter_props(m: Meter) -> Dict[str, Any]:
    return {
        "id": m.id,
        "serial": m.serial,
        "status": getattr(m.status, "value", m.status),
        "meter_type": getattr(m.meter_type, "value", m.meter_type),
        "customer_name": m.customer_name,
        "transformer_id": m.transformer_id,
    }


def _transformer_props(t: Transformer) -> Dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "feeder_id": t.feeder_id,
        "capacity_kva": t.capacity_kva,
        "loading_percent": t.loading_percent,
        "voltage_pu": t.voltage_pu,
    }


def _feeder_props(f: Feeder) -> Dict[str, Any]:
    return {
        "id": f.id,
        "name": f.name,
        "substation": f.substation,
        "voltage_kv": f.voltage_kv,
        "capacity_kva": f.capacity_kva,
        "current_load_kw": f.current_load_kw,
    }


def _der_props(d: DERAsset) -> Dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "asset_type": getattr(d.asset_type, "value", d.asset_type),
        "status": getattr(d.status, "value", d.status),
        "rated_capacity_kw": d.rated_capacity_kw,
        "current_output_kw": d.current_output_kw,
    }


def _alarm_props(a: Alarm) -> Dict[str, Any]:
    return {
        "id": a.id,
        "alarm_type": getattr(a.alarm_type, "value", a.alarm_type),
        "severity": getattr(a.severity, "value", a.severity),
        "status": getattr(a.status, "value", a.status),
        "title": a.title,
        "meter_serial": a.meter_serial,
        "alarm_flag": True,
    }


def _outage_props(o: OutageArea) -> Dict[str, Any]:
    return {
        "id": o.id,
        "network_event_id": o.network_event_id,
        "affected_customers": o.affected_customers,
        "started_at": o.started_at.isoformat() if o.started_at else None,
        "etr": o.etr.isoformat() if o.etr else None,
        "resolved_at": o.resolved_at.isoformat() if o.resolved_at else None,
    }


def _zone_props(z: Zone) -> Dict[str, Any]:
    return {
        "id": z.id,
        "name": z.name,
        "zone_type": z.zone_type,
        "rules": z.rules,
        "created_by": z.created_by,
        "orphan": z.orphan,
    }


def _service_line_props(s: ServiceLine) -> Dict[str, Any]:
    return {
        "id": s.id,
        "meter_serial": s.meter_serial,
        "transformer_id": s.transformer_id,
        "length_m": s.length_m,
        "cable_type": s.cable_type,
    }


def _pole_props(p: Pole) -> Dict[str, Any]:
    return {
        "id": p.id,
        "feeder_id": p.feeder_id,
        "material": p.material,
        "height_m": p.height_m,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

LAYER_CONFIG = {
    # layer_name: (model, geom_attr, properties_fn, min_zoom or None)
    "meters":        (Meter, "geom", _meter_props, 12),
    "transformers":  (Transformer, "geom", _transformer_props, None),
    "feeders":       (Feeder, "geom", _feeder_props, None),
    "der":           (DERAsset, "geom", _der_props, 8),
    "alarms":        (Alarm, "geom", _alarm_props, None),
    "outage_areas":  (OutageArea, "polygon_geom", _outage_props, None),
    "zones":         (Zone, "geom", _zone_props, None),
    "service_lines": (ServiceLine, "geom", _service_line_props, 13),
    "poles":         (Pole, "geom", _pole_props, 15),
}


@router.get("/layers/{layer}")
def get_layer(
    layer: str,
    bbox: Optional[str] = Query(default=None, description="minlon,minlat,maxlon,maxlat"),
    zoom: int = Query(default=12, ge=0, le=22),
    status: Optional[str] = Query(default=None, description="optional status filter (alarms)"),
    max_features: int = Query(default=DEFAULT_MAX_FEATURES, gt=0, le=DEFAULT_MAX_FEATURES),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return a RFC 7946 FeatureCollection for ``layer`` filtered by ``bbox`` + LOD."""
    if layer not in LAYER_CONFIG:
        raise HTTPException(status_code=404, detail=f"Unknown layer '{layer}'")

    model, geom_attr, props_fn, min_zoom = LAYER_CONFIG[layer]
    bbox_parsed = parse_bbox(bbox)

    # LOD gating — skip densely-packed layers at low zoom.
    if min_zoom is not None and zoom < min_zoom:
        # For meters at 10-11 we could cluster instead; TODO(014-mvp-phase2) server-side clustering.
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"skipped": "zoom too low", "min_zoom": min_zoom, "zoom": zoom},
        }

    # Optional clustering for meters at mid zoom (12-13): return grid centroids via ST_SnapToGrid.
    if layer == "meters" and zoom < 14:
        minlon, minlat, maxlon, maxlat = bbox_parsed or (-180.0, -85.0, 180.0, 85.0)
        # Grid size in degrees — coarser at lower zoom.
        grid = 0.02 if zoom == 13 else 0.05
        rows = db.execute(
            text(
                """
                SELECT ST_AsGeoJSON(ST_Centroid(ST_Collect(geom)))::json AS geom,
                       COUNT(*)  AS point_count,
                       SUM(CASE WHEN status::text = 'ONLINE' THEN 1 ELSE 0 END) AS online_count
                FROM meters
                WHERE geom IS NOT NULL
                  AND geom && ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)
                GROUP BY ST_SnapToGrid(geom, :grid, :grid)
                LIMIT :lim
                """
            ),
            {
                "minlon": minlon, "minlat": minlat,
                "maxlon": maxlon, "maxlat": maxlat,
                "grid": grid, "lim": max_features,
            },
        ).mappings().all()
        features = [
            {
                "type": "Feature",
                "geometry": r["geom"],
                "properties": {
                    "cluster": True,
                    "point_count": r["point_count"],
                    "online_count": r["online_count"],
                },
            }
            for r in rows if r["geom"] is not None
        ]
        return raw_features(features, meta={"clustered": True, "grid_deg": grid, "zoom": zoom})

    # Raw (non-cluster) query path.
    geom_col = getattr(model, geom_attr)
    q = db.query(model).filter(geom_col.isnot(None))

    # Per-layer extra filters
    if layer == "alarms" and status:
        q = q.filter(Alarm.status == status)
    elif layer == "alarms" and status is None:
        # Default: show active alarms only (matches existing UX).
        from app.models.alarm import AlarmStatus
        q = q.filter(Alarm.status == AlarmStatus.ACTIVE)

    q = bbox_filter(q, geom_col, bbox_parsed)
    # Limit query (max_features + 1 so we can detect truncation).
    rows = q.limit(max_features + 1).all()

    fc = rows_to_featurecollection(
        rows,
        geom_attr=geom_attr,
        properties_fn=props_fn,
        max_features=max_features,
    )
    fc.setdefault("meta", {})["feature_count"] = len(fc["features"])
    fc["meta"]["layer"] = layer
    fc["meta"]["zoom"] = zoom
    # TODO(014-mvp-phase2): OTel span attributes gis.layer, gis.bbox, gis.feature_count.
    return fc


@router.get("/layers")
def list_layers(_: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "layers": [
            {"name": name, "min_zoom": cfg[3]}
            for name, cfg in LAYER_CONFIG.items()
        ]
    }


# ── Admin hierarchy drill-down (zone → consumer) ────────────────────────────
# See app.services.hierarchy for the static demo mapping.
from app.services import hierarchy as hierarchy_svc  # noqa: E402


@router.get("/hierarchy/tree")
def hierarchy_tree(
    parent_id: Optional[str] = Query(None, description="Parent node id (None = root zone)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return children of a hierarchy node, with aggregate stats.

    Hierarchy: zone → circle → division → subdivision → substation → feeder → dtr → consumer.
    """
    result = hierarchy_svc.get_tree_children(db, parent_id)
    level = result.get("node", {}).get("level") if isinstance(result, dict) else None
    if level:
        result["commands"] = hierarchy_svc.get_commands_for_level(level)
    return result


@router.get("/hierarchy/boundaries")
def hierarchy_boundaries(_: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Bounding polygons for zone/circle/division/subdivision levels (GeoJSON)."""
    return hierarchy_svc.get_boundaries_geojson()


@router.post("/hierarchy/command")
def hierarchy_command(
    payload: Dict[str, Any],
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Dispatch a hierarchy-level command. For the demo, commands are logged
    and acknowledged. Real-world wiring (switching, SMS, crew dispatch) would
    fan out to the respective microservices here."""
    cmd = payload.get("cmd")
    node_id = payload.get("node_id")
    if not cmd or not node_id:
        raise HTTPException(status_code=400, detail="cmd and node_id required")
    node = hierarchy_svc.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")
    return {
        "ok": True,
        "action": cmd,
        "node": {"id": node["id"], "name": node["name"], "level": node["level"]},
        "message": f"{cmd} dispatched for {node['name']}",
    }
