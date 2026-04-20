"""
Admin hierarchy service for GIS drill-down.

Hierarchy (8 levels): zone -> circle -> division -> subdivision -> substation
                     -> feeder -> dtr (transformer) -> consumer (meter)

The top 5 levels (zone..substation) are a static demo mapping keyed to the
existing SA_AREAS / feeder substation strings from seed_data.py. The bottom
3 levels (feeder..consumer) come from the live Feeder/Transformer/Meter
tables. Aggregates (alarms, kWh, loading) are computed on demand.

This deliberately avoids adding new tables so the dev CodePipeline can ship
without a follow-up Alembic migration step. If / when the demo graduates to
a full admin-boundary schema, the endpoints keep the same shape — only the
data source changes.
"""
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alarm import Alarm, AlarmSeverity, AlarmStatus
from app.models.meter import Feeder, Meter, MeterStatus, Transformer

# ── Static demo hierarchy ────────────────────────────────────────────────────
# Maps every seeded substation (5 in SA_AREAS) to a 5-level admin path.
# A single zone ("ZA") holds 2 circles, each with 1–2 divisions, each with
# 1–2 subdivisions, each with 1 substation that parents 5 feeders.
HIERARCHY: List[Dict[str, Any]] = [
    {
        "id": "zone:za", "name": "Republic of South Africa", "level": "zone",
        "center": [-29.0, 25.0], "bbox": [16.0, -35.0, 33.0, -22.0],
        "children": [
            {
                "id": "circle:gauteng", "name": "Gauteng Circle", "level": "circle",
                "center": [-26.0, 28.0], "bbox": [27.6, -26.5, 28.3, -25.6],
                "children": [
                    {
                        "id": "division:johannesburg", "name": "Johannesburg Division",
                        "level": "division",
                        "center": [-26.18, 27.98], "bbox": [27.80, -26.30, 28.15, -26.05],
                        "children": [
                            {
                                "id": "subdivision:soweto-n", "name": "Soweto North Subdivision",
                                "level": "subdivision",
                                "center": [-26.25, 27.85], "bbox": [27.80, -26.30, 27.92, -26.20],
                                "substations": ["Orlando SS"],
                            },
                            {
                                "id": "subdivision:sandton", "name": "Sandton CBD Subdivision",
                                "level": "subdivision",
                                "center": [-26.11, 28.06], "bbox": [28.00, -26.18, 28.15, -26.05],
                                "substations": ["Sandton SS"],
                            },
                        ],
                    },
                    {
                        "id": "division:tshwane", "name": "Tshwane Division",
                        "level": "division",
                        "center": [-25.75, 28.23], "bbox": [28.10, -25.90, 28.35, -25.65],
                        "children": [
                            {
                                "id": "subdivision:pretoria-e", "name": "Pretoria East Subdivision",
                                "level": "subdivision",
                                "center": [-25.75, 28.23], "bbox": [28.10, -25.90, 28.35, -25.65],
                                "substations": ["Pretoria SS"],
                            },
                        ],
                    },
                ],
            },
            {
                "id": "circle:coastal", "name": "Coastal Circle", "level": "circle",
                "center": [-31.5, 25.0], "bbox": [18.0, -35.0, 32.0, -29.0],
                "children": [
                    {
                        "id": "division:western-cape", "name": "Western Cape Division",
                        "level": "division",
                        "center": [-34.05, 18.62], "bbox": [18.40, -34.25, 18.90, -33.85],
                        "children": [
                            {
                                "id": "subdivision:mitchells-plain", "name": "Mitchells Plain Subdivision",
                                "level": "subdivision",
                                "center": [-34.05, 18.62], "bbox": [18.40, -34.25, 18.90, -33.85],
                                "substations": ["Mitchells SS"],
                            },
                        ],
                    },
                    {
                        "id": "division:kzn", "name": "KwaZulu-Natal Division",
                        "level": "division",
                        "center": [-29.86, 31.02], "bbox": [30.80, -30.00, 31.20, -29.65],
                        "children": [
                            {
                                "id": "subdivision:durban-c", "name": "Durban Central Subdivision",
                                "level": "subdivision",
                                "center": [-29.86, 31.02], "bbox": [30.80, -30.00, 31.20, -29.65],
                                "substations": ["Durban North SS"],
                            },
                        ],
                    },
                ],
            },
        ],
    },
]


def _flatten(node: Dict[str, Any], path: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Flatten tree to list with cached ancestry paths."""
    path = (path or []) + [node["id"]]
    out = [{**node, "path": path}]
    for child in node.get("children", []):
        out.extend(_flatten(child, path))
    return out


# Pre-computed flat index for lookups
_FLAT = {n["id"]: n for n in _flatten(HIERARCHY[0])}


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    return _FLAT.get(node_id)


def _substations_under(node: Dict[str, Any]) -> List[str]:
    """Collect all substation names in the subtree rooted at `node`."""
    if node["level"] == "subdivision":
        return list(node.get("substations", []))
    subs: List[str] = []
    for child in node.get("children", []):
        subs.extend(_substations_under(child))
    return subs


def _compute_aggregates(db: Session, substations: List[str]) -> Dict[str, Any]:
    """Compute alarm counts, meter counts, and loading for a set of substations."""
    if not substations:
        return {
            "feeder_count": 0, "transformer_count": 0, "meter_count": 0,
            "meters_online": 0, "meters_offline": 0,
            "active_alarms": 0, "critical_alarms": 0,
            "avg_loading_pct": 0.0, "total_load_kw": 0.0,
        }

    feeders = db.query(Feeder).filter(Feeder.substation.in_(substations)).all()
    feeder_ids = [f.id for f in feeders]

    if not feeder_ids:
        return {
            "feeder_count": 0, "transformer_count": 0, "meter_count": 0,
            "meters_online": 0, "meters_offline": 0,
            "active_alarms": 0, "critical_alarms": 0,
            "avg_loading_pct": 0.0, "total_load_kw": 0.0,
        }

    transformers = db.query(Transformer).filter(Transformer.feeder_id.in_(feeder_ids)).all()
    tx_ids = [t.id for t in transformers]

    meters_total = (
        db.query(func.count(Meter.id))
        .filter(Meter.transformer_id.in_(tx_ids))
        .scalar() or 0
    )
    meters_online = (
        db.query(func.count(Meter.id))
        .filter(Meter.transformer_id.in_(tx_ids), Meter.status == MeterStatus.ONLINE)
        .scalar() or 0
    )
    meters_offline = meters_total - meters_online

    active_alarms = (
        db.query(func.count(Alarm.id))
        .filter(Alarm.transformer_id.in_(tx_ids), Alarm.status == AlarmStatus.ACTIVE)
        .scalar() or 0
    ) if tx_ids else 0
    critical_alarms = (
        db.query(func.count(Alarm.id))
        .filter(
            Alarm.transformer_id.in_(tx_ids),
            Alarm.status == AlarmStatus.ACTIVE,
            Alarm.severity == AlarmSeverity.CRITICAL,
        )
        .scalar() or 0
    ) if tx_ids else 0

    avg_loading = (
        sum(t.loading_percent or 0 for t in transformers) / len(transformers)
        if transformers else 0.0
    )
    total_load = sum(t.current_load_kw or 0 for t in transformers)

    return {
        "feeder_count": len(feeders),
        "transformer_count": len(transformers),
        "meter_count": meters_total,
        "meters_online": meters_online,
        "meters_offline": meters_offline,
        "active_alarms": active_alarms,
        "critical_alarms": critical_alarms,
        "avg_loading_pct": round(avg_loading, 1),
        "total_load_kw": round(total_load, 1),
    }


def get_tree_children(db: Session, parent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the children of a hierarchy node, with aggregate stats per child.
    If parent_id is None, return the root zone.
    """
    if parent_id is None:
        root = HIERARCHY[0]
        return {
            "node": {
                "id": root["id"], "name": root["name"], "level": root["level"],
                "center": root["center"], "bbox": root["bbox"],
            },
            "stats": _compute_aggregates(db, _substations_under(root)),
            "children": [
                _child_summary(db, c) for c in root.get("children", [])
            ],
        }

    node = get_node(parent_id)
    if node is None:
        return {"error": "node not found"}

    # At subdivision level, children are substations (derived from substation strings)
    if node["level"] == "subdivision":
        children = [
            _substation_summary(db, substation_name, node)
            for substation_name in node.get("substations", [])
        ]
    # At substation level, children are feeders
    elif node["level"] == "substation":
        feeders = db.query(Feeder).filter(Feeder.substation == node["substation_name"]).all()
        children = [_feeder_summary(db, f, node) for f in feeders]
    # At feeder level, children are transformers
    elif node["level"] == "feeder":
        transformers = db.query(Transformer).filter(Transformer.feeder_id == node["feeder_id"]).all()
        children = [_transformer_summary(db, t, node) for t in transformers]
    # At DTR (transformer) level, children are meters
    elif node["level"] == "dtr":
        meters = (
            db.query(Meter).filter(Meter.transformer_id == node["transformer_id"]).all()
        )
        children = [_meter_summary(m, node) for m in meters]
    elif node["level"] == "consumer":
        children = []
    else:
        children = [_child_summary(db, c) for c in node.get("children", [])]

    return {
        "node": {
            "id": node["id"], "name": node["name"], "level": node["level"],
            "path": node.get("path", []),
            "center": node.get("center"), "bbox": node.get("bbox"),
        },
        "stats": _compute_aggregates(db, _substations_under(node))
                 if node["level"] in ("zone", "circle", "division", "subdivision")
                 else _stats_for_node(db, node),
        "children": children,
    }


def _child_summary(db: Session, node: Dict[str, Any]) -> Dict[str, Any]:
    """Summary entry for zone/circle/division/subdivision children."""
    return {
        "id": node["id"], "name": node["name"], "level": node["level"],
        "center": node.get("center"), "bbox": node.get("bbox"),
        "stats": _compute_aggregates(db, _substations_under(node)),
        "has_children": True,
    }


def _substation_summary(db: Session, substation_name: str, parent: Dict[str, Any]) -> Dict[str, Any]:
    feeders = db.query(Feeder).filter(Feeder.substation == substation_name).all()
    feeder_ids = [f.id for f in feeders]
    transformers = (
        db.query(Transformer).filter(Transformer.feeder_id.in_(feeder_ids)).all()
        if feeder_ids else []
    )
    lat = (sum(t.latitude for t in transformers) / len(transformers)) if transformers else parent["center"][0]
    lon = (sum(t.longitude for t in transformers) / len(transformers)) if transformers else parent["center"][1]
    ss_id = f"substation:{substation_name.lower().replace(' ', '-')}"
    node = {
        "id": ss_id,
        "name": substation_name,
        "level": "substation",
        "substation_name": substation_name,
        "center": [lat, lon],
        "path": parent.get("path", []) + [ss_id],
    }
    _FLAT[ss_id] = node  # cache for later drill-down
    return {
        **{k: node[k] for k in ("id", "name", "level", "center")},
        "stats": _compute_aggregates(db, [substation_name]),
        "has_children": len(feeders) > 0,
    }


def _feeder_summary(db: Session, feeder: Feeder, parent: Dict[str, Any]) -> Dict[str, Any]:
    transformers = db.query(Transformer).filter(Transformer.feeder_id == feeder.id).all()
    lat = (sum(t.latitude for t in transformers) / len(transformers)) if transformers else parent["center"][0]
    lon = (sum(t.longitude for t in transformers) / len(transformers)) if transformers else parent["center"][1]
    f_id = f"feeder:{feeder.id}"
    node = {
        "id": f_id,
        "name": feeder.name,
        "level": "feeder",
        "feeder_id": feeder.id,
        "center": [lat, lon],
        "path": parent.get("path", []) + [f_id],
    }
    _FLAT[f_id] = node

    loading_pct = (
        (feeder.current_load_kw / feeder.capacity_kva * 100.0)
        if feeder.capacity_kva else 0.0
    )
    tx_ids = [t.id for t in transformers]
    meter_count = (
        db.query(func.count(Meter.id))
        .filter(Meter.transformer_id.in_(tx_ids))
        .scalar() or 0
    ) if tx_ids else 0
    alarms = (
        db.query(func.count(Alarm.id))
        .filter(Alarm.transformer_id.in_(tx_ids), Alarm.status == AlarmStatus.ACTIVE)
        .scalar() or 0
    ) if tx_ids else 0

    return {
        **{k: node[k] for k in ("id", "name", "level", "center")},
        "stats": {
            "transformer_count": len(transformers),
            "meter_count": meter_count,
            "active_alarms": alarms,
            "voltage_kv": feeder.voltage_kv,
            "capacity_kva": feeder.capacity_kva,
            "current_load_kw": feeder.current_load_kw,
            "loading_pct": round(loading_pct, 1),
        },
        "has_children": len(transformers) > 0,
    }


def _transformer_summary(db: Session, tx: Transformer, parent: Dict[str, Any]) -> Dict[str, Any]:
    t_id = f"dtr:{tx.id}"
    node = {
        "id": t_id,
        "name": tx.name,
        "level": "dtr",
        "transformer_id": tx.id,
        "center": [tx.latitude, tx.longitude],
        "path": parent.get("path", []) + [t_id],
    }
    _FLAT[t_id] = node
    meter_count = (
        db.query(func.count(Meter.id))
        .filter(Meter.transformer_id == tx.id)
        .scalar() or 0
    )
    online = (
        db.query(func.count(Meter.id))
        .filter(Meter.transformer_id == tx.id, Meter.status == MeterStatus.ONLINE)
        .scalar() or 0
    )
    alarms = (
        db.query(func.count(Alarm.id))
        .filter(Alarm.transformer_id == tx.id, Alarm.status == AlarmStatus.ACTIVE)
        .scalar() or 0
    )
    return {
        **{k: node[k] for k in ("id", "name", "level", "center")},
        "stats": {
            "meter_count": meter_count,
            "meters_online": online,
            "meters_offline": meter_count - online,
            "active_alarms": alarms,
            "capacity_kva": tx.capacity_kva,
            "loading_pct": round(tx.loading_percent or 0, 1),
            "voltage_pu": tx.voltage_pu,
            "phase": tx.phase,
        },
        "has_children": meter_count > 0,
    }


def _meter_summary(meter: Meter, parent: Dict[str, Any]) -> Dict[str, Any]:
    c_id = f"consumer:{meter.serial}"
    return {
        "id": c_id,
        "name": meter.customer_name or meter.serial,
        "level": "consumer",
        "center": [meter.latitude, meter.longitude],
        "stats": {
            "serial": meter.serial,
            "status": meter.status.value if meter.status else "unknown",
            "meter_type": meter.meter_type.value if meter.meter_type else "unknown",
            "tariff_class": meter.tariff_class,
            "address": meter.address,
            "account_number": meter.account_number,
        },
        "has_children": False,
    }


def _stats_for_node(db: Session, node: Dict[str, Any]) -> Dict[str, Any]:
    """Per-node stats for non-geographic levels."""
    if node["level"] == "substation":
        return _compute_aggregates(db, [node["substation_name"]])
    if node["level"] == "feeder":
        feeder = db.query(Feeder).filter(Feeder.id == node["feeder_id"]).first()
        if feeder:
            return {
                "voltage_kv": feeder.voltage_kv,
                "capacity_kva": feeder.capacity_kva,
                "current_load_kw": feeder.current_load_kw,
                "loading_pct": round(
                    (feeder.current_load_kw / feeder.capacity_kva * 100.0)
                    if feeder.capacity_kva else 0.0, 1
                ),
            }
    if node["level"] == "dtr":
        tx = db.query(Transformer).filter(Transformer.id == node["transformer_id"]).first()
        if tx:
            return {
                "capacity_kva": tx.capacity_kva,
                "loading_pct": round(tx.loading_percent or 0, 1),
                "voltage_pu": tx.voltage_pu,
            }
    return {}


def get_commands_for_level(level: str) -> List[Dict[str, str]]:
    """Per-level command palette shown in the right side panel."""
    palette = {
        "zone": [
            {"cmd": "broadcast_crew_alert", "label": "Broadcast crew alert"},
            {"cmd": "export_alarms_csv", "label": "Export alarms CSV"},
            {"cmd": "open_regional_report", "label": "Regional consumption report"},
        ],
        "circle": [
            {"cmd": "broadcast_crew_alert", "label": "Broadcast crew alert"},
            {"cmd": "load_balance_circle", "label": "Rebalance circle load"},
            {"cmd": "open_circle_report", "label": "Circle performance report"},
        ],
        "division": [
            {"cmd": "dispatch_crew", "label": "Dispatch crew"},
            {"cmd": "load_balance_division", "label": "Rebalance division load"},
            {"cmd": "outage_sms_division", "label": "Outage SMS to division"},
        ],
        "subdivision": [
            {"cmd": "dispatch_crew", "label": "Dispatch crew"},
            {"cmd": "load_balance_subdivision", "label": "Rebalance loads"},
        ],
        "substation": [
            {"cmd": "switching_schedule", "label": "Switching schedule"},
            {"cmd": "load_transfer", "label": "Transfer load to adjacent feeder"},
            {"cmd": "reclose_main_cb", "label": "Reclose main CB"},
        ],
        "feeder": [
            {"cmd": "isolate_feeder", "label": "Isolate feeder"},
            {"cmd": "restore_feeder", "label": "Restore feeder"},
            {"cmd": "feeder_load_profile", "label": "View load profile"},
        ],
        "dtr": [
            {"cmd": "curtail_tx_load", "label": "Curtail DTR by 55 kVA"},
            {"cmd": "force_fan_override", "label": "Force fan override"},
            {"cmd": "poll_sensors", "label": "Poll sensors"},
            {"cmd": "raise_work_order", "label": "Raise oil sample WO"},
            {"cmd": "dispatch_thermal_crew", "label": "Dispatch thermal inspection"},
        ],
        "consumer": [
            {"cmd": "meter_read_now", "label": "Meter read now"},
            {"cmd": "meter_disconnect", "label": "Remote disconnect"},
            {"cmd": "meter_reconnect", "label": "Remote reconnect"},
            {"cmd": "view_consumption", "label": "View consumption history"},
        ],
    }
    return palette.get(level, [])


def get_boundaries_geojson() -> Dict[str, Any]:
    """
    Simple GeoJSON FeatureCollection of top-4-level bounding polygons
    (zone + circles + divisions + subdivisions), computed from the static
    bbox definitions. Useful for choropleth rendering before drill-down.
    """
    features = []
    for node in _flatten(HIERARCHY[0]):
        if node["level"] not in ("zone", "circle", "division", "subdivision"):
            continue
        bbox = node.get("bbox")
        if not bbox:
            continue
        min_lon, min_lat, max_lon, max_lat = bbox
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]],
            },
            "properties": {
                "id": node["id"], "name": node["name"],
                "level": node["level"], "path": node["path"],
            },
        })
    return {"type": "FeatureCollection", "features": features}
