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
    loading = t.loading_percent
    if loading is None and t.capacity_kva and t.current_load_kw is not None:
        loading = round((t.current_load_kw / t.capacity_kva) * 100.0, 1)
    return {
        "id": t.id,
        "name": t.name,
        "feeder_id": t.feeder_id,
        "capacity_kva": t.capacity_kva,
        "current_load_kw": t.current_load_kw,
        # Frontend GISMap reads `loading_pct`; keep `loading_percent` for legacy
        # consumers (feeder dashboard widgets).
        "loading_pct": loading,
        "loading_percent": t.loading_percent,
        "voltage_pu": t.voltage_pu,
    }


def _feeder_props(f: Feeder) -> Dict[str, Any]:
    loading_pct = None
    if f.capacity_kva and f.current_load_kw is not None:
        loading_pct = round((f.current_load_kw / f.capacity_kva) * 100.0, 1)
    return {
        "id": f.id,
        "name": f.name,
        "substation": f.substation,
        "voltage_kv": f.voltage_kv,
        "capacity_kva": f.capacity_kva,
        "current_load_kw": f.current_load_kw,
        "loading_pct": loading_pct,
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

# Singular short-names accepted on the wire — both the frontend and the
# original W3.T5 tests use `meter` / `dtr` / `feeder`. Keep them working
# alongside the canonical plural keys.
LAYER_ALIASES = {
    "meter":        "meters",
    "dtr":          "transformers",
    "transformer":  "transformers",
    "feeder":       "feeders",
    "pole":         "poles",
    "alarm":        "alarms",
    "zone":         "zones",
    "outage_area":  "outage_areas",
    "service_line": "service_lines",
}


def _canonical_layer(layer: str) -> str:
    return LAYER_ALIASES.get(layer, layer)


# ── lat/lon fallback ────────────────────────────────────────────────────────
# Several core models (Meter, Transformer, Feeder, DERAsset, Alarm) carry
# latitude/longitude (or, for Feeder, a `geojson` LineString) but no PostGIS
# `geom` column — so the original ST_-based query path raises
# AttributeError. This fallback builds RFC 7946 Features from those columns
# directly, with Python-side bbox filtering. Used only when the ORM model
# lacks the configured geom_attr; layers backed by real PostGIS columns
# (zones, outage_areas, service_lines, poles) still use the fast SQL path.

def _bbox_contains(lat: Optional[float], lon: Optional[float],
                   bbox: Optional[Tuple[float, float, float, float]]) -> bool:
    if lat is None or lon is None:
        return False
    if bbox is None:
        return True
    minlon, minlat, maxlon, maxlat = bbox
    return minlon <= lon <= maxlon and minlat <= lat <= maxlat


def _latlon_layer_fallback(
    db: Session,
    layer: str,
    bbox_parsed: Optional[Tuple[float, float, float, float]],
    status: Optional[str],
    max_features: int,
) -> Dict[str, Any]:
    """Build a FeatureCollection from lat/lon (or geojson) attributes."""
    features: List[Dict[str, Any]] = []
    truncated = False

    if layer in ("meters", "transformers", "der", "alarms"):
        model_props_map = {
            "meters":       (Meter, _meter_props),
            "transformers": (Transformer, _transformer_props),
            "der":          (DERAsset, _der_props),
            "alarms":       (Alarm, _alarm_props),
        }
        model, props_fn = model_props_map[layer]
        q = db.query(model)
        if layer == "alarms":
            from app.models.alarm import AlarmStatus
            q = q.filter(model.status == (status or AlarmStatus.ACTIVE))
        rows = q.limit(max_features * 4).all()  # over-fetch then filter by bbox
        for row in rows:
            lat = getattr(row, "latitude", None)
            lon = getattr(row, "longitude", None)
            if not _bbox_contains(lat, lon, bbox_parsed):
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props_fn(row),
            })
            if len(features) >= max_features:
                truncated = True
                break

    elif layer == "feeders":
        # Feeder.geojson stores a JSON LineString { coordinates: [[lon,lat], ...] }.
        # Fall back to a synthetic line between the substation centre and the
        # average of the feeder's transformer locations when geojson is empty.
        rows = db.query(Feeder).limit(max_features * 2).all()
        for row in rows:
            line: List[List[float]] = []
            if row.geojson:
                try:
                    if isinstance(row.geojson, dict):
                        coords = row.geojson.get("coordinates") or []
                    elif isinstance(row.geojson, list):
                        coords = row.geojson
                    else:
                        coords = []
                    line = [[float(c[0]), float(c[1])] for c in coords if isinstance(c, (list, tuple)) and len(c) >= 2]
                except Exception:
                    line = []
            if not line:
                # Build line from this feeder's transformers (if any).
                tx_rows = db.query(Transformer).filter(Transformer.feeder_id == row.id).all()
                tx_pts = [[t.longitude, t.latitude] for t in tx_rows
                          if t.latitude is not None and t.longitude is not None]
                if len(tx_pts) >= 2:
                    line = tx_pts
                elif len(tx_pts) == 1:
                    line = [tx_pts[0], tx_pts[0]]
            if len(line) < 2:
                continue
            # Bbox check: include if any vertex falls within bbox.
            if bbox_parsed is not None:
                if not any(_bbox_contains(p[1], p[0], bbox_parsed) for p in line):
                    continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": line},
                "properties": _feeder_props(row),
            })
            if len(features) >= max_features:
                truncated = True
                break

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "layer": layer,
            "feature_count": len(features),
            "fallback": "latlon",
            "truncated": truncated,
        },
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
    layer = _canonical_layer(layer)
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

    # If the model has no PostGIS `geom` column, the SQL clustering path
    # below would also fail — short-circuit to the lat/lon fallback.
    if not hasattr(model, geom_attr):
        return _latlon_layer_fallback(db, layer, bbox_parsed, status, max_features)

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

    # If the model has no PostGIS geom column (lat/lon-only schema), fall
    # back to the Python-side builder so the layer renders even when the
    # PostGIS-backed query path would AttributeError.
    if not hasattr(model, geom_attr):
        return _latlon_layer_fallback(db, layer, bbox_parsed, status, max_features)

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


@router.get("/meter-consumption")
def meter_consumption(
    hours: int = Query(default=24, ge=1, le=168),
    bbox: Optional[str] = Query(default=None, description="minlon,minlat,maxlon,maxlat"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-meter consumption aggregate for the GIS consumption-quartile overlay.

    Required by SMOC-FUNC-026-FR-03: colour meters by consumption quartile
    (deep red for highest consumers, blue for lowest) at feeder zoom.

    Returns a flat map + precomputed quartile breakpoints so the frontend can
    colour meters without loading the full readings table.
    """
    bbox_parsed = parse_bbox(bbox)
    sql = text(
        """
        SELECT m.serial                   AS serial,
               COALESCE(SUM(r.energy_import_kwh), 0) AS kwh
          FROM meters m
     LEFT JOIN meter_readings r
            ON r.meter_serial = m.serial
           AND r.timestamp >= now() - (:hours || ' hours')::interval
         WHERE (:use_bbox = FALSE OR (
                    m.longitude BETWEEN :minlon AND :maxlon
                AND m.latitude  BETWEEN :minlat AND :maxlat
             ))
         GROUP BY m.serial
        """
    )
    params = {
        "hours": hours,
        "use_bbox": bbox_parsed is not None,
        "minlon": bbox_parsed[0] if bbox_parsed else 0.0,
        "minlat": bbox_parsed[1] if bbox_parsed else 0.0,
        "maxlon": bbox_parsed[2] if bbox_parsed else 0.0,
        "maxlat": bbox_parsed[3] if bbox_parsed else 0.0,
    }
    rows = db.execute(sql, params).mappings().all()
    series = [(r["serial"], float(r["kwh"] or 0.0)) for r in rows]

    # Quartile breakpoints (Q1/Q2/Q3) over non-zero consumers so inactive /
    # offline meters don't drag the lower thresholds to zero.
    non_zero = sorted(v for _, v in series if v > 0.0)
    def _pct(p: float) -> float:
        if not non_zero:
            return 0.0
        idx = min(len(non_zero) - 1, max(0, int(round(p * (len(non_zero) - 1)))))
        return non_zero[idx]

    return {
        "hours": hours,
        "quartiles": {
            "q1": round(_pct(0.25), 2),
            "q2": round(_pct(0.50), 2),
            "q3": round(_pct(0.75), 2),
            "max": round(non_zero[-1], 2) if non_zero else 0.0,
        },
        "meters": {serial: round(kwh, 2) for serial, kwh in series},
        "meter_count": len(series),
    }


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
