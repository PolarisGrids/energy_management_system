"""GeoJSON (RFC 7946) serializer helpers for spec 014-gis-postgis.

Converts SQLAlchemy rows with a geoalchemy2 geometry attribute into
FeatureCollection dictionaries suitable for direct JSON response.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping


DEFAULT_MAX_FEATURES = 10000


def row_to_feature(row: Any, geom_attr: str, properties_fn: Callable[[Any], Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert a single row to a GeoJSON Feature dict; return None if no geometry."""
    geom = getattr(row, geom_attr, None)
    if geom is None:
        return None
    try:
        shape = to_shape(geom)
    except Exception:
        return None
    return {
        "type": "Feature",
        "geometry": mapping(shape),
        "properties": properties_fn(row),
    }


def rows_to_featurecollection(
    rows: Iterable[Any],
    geom_attr: str,
    properties_fn: Callable[[Any], Dict[str, Any]],
    max_features: int = DEFAULT_MAX_FEATURES,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert an iterable of ORM rows into a FeatureCollection dict.

    Enforces a hard cap of ``max_features`` and attaches ``truncated: true``
    when the cap is hit. Additional metadata (e.g. cluster markers, LOD
    notes) can be attached via the ``meta`` dict.
    """
    features: List[Dict[str, Any]] = []
    truncated = False
    for i, row in enumerate(rows):
        if i >= max_features:
            truncated = True
            break
        feat = row_to_feature(row, geom_attr, properties_fn)
        if feat is not None:
            features.append(feat)

    fc: Dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
    }
    if truncated:
        fc["truncated"] = True
    if meta:
        fc["meta"] = meta
    return fc


def raw_features(geojson_rows: Iterable[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a FeatureCollection from rows that already contain GeoJSON fragments."""
    fc: Dict[str, Any] = {"type": "FeatureCollection", "features": list(geojson_rows)}
    if meta:
        fc["meta"] = meta
    return fc
