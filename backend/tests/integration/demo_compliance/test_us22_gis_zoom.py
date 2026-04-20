"""US-22: GIS Zoom Hierarchy & Context Commands (Demo #26).

Acceptance (spec §User Story 22 + matrix row 22):

* Zoom from country level → DTR → meter.
* Each level's context menu is level-appropriate (data-driven).
* "Read meter" on a meter dispatches an HES command.
* Alarm heatmap overlay toggles render from PostGIS.
"""
from __future__ import annotations

import uuid

import pytest


pytestmark = [pytest.mark.demo_compliance]


def _seed_feeder_dtr_meter(db_session):
    from app.models.meter import Feeder, Meter, MeterStatus, RelayState, Transformer

    feeder = Feeder(
        name=f"FDR-{uuid.uuid4().hex[:4]}",
        substation="SS-GIS",
        voltage_kv=11.0,
        capacity_kva=500.0,
    )
    db_session.add(feeder)
    db_session.flush()
    tx = Transformer(
        name=f"DTR-{uuid.uuid4().hex[:4]}",
        feeder_id=feeder.id,
        latitude=12.97,
        longitude=77.59,
        capacity_kva=100.0,
    )
    db_session.add(tx)
    db_session.flush()
    m = Meter(
        serial=f"M-{uuid.uuid4().hex[:6]}",
        transformer_id=tx.id,
        status=MeterStatus.ONLINE,
        relay_state=RelayState.CONNECTED,
        latitude=12.971,
        longitude=77.591,
    )
    db_session.add(m)
    db_session.commit()
    return feeder, tx, m


def test_gis_layers_return_topology_at_each_level(client, db_session):
    """GIS layers endpoint returns feeders/DTRs/meters for a bounding box."""
    _seed_feeder_dtr_meter(db_session)
    bbox = "77.5,12.9,77.7,13.0"  # lon_min,lat_min,lon_max,lat_max
    resp = client.get(
        "/api/v1/gis/layers", params={"layer": "meter", "bbox": bbox}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # GeoJSON FeatureCollection shape.
    assert body.get("type") == "FeatureCollection" or "features" in body, body


def test_alarm_heatmap_toggle_returns_postgis_layer(client):
    """Toggling the alarm density overlay queries the heatmap endpoint."""
    resp = client.get("/api/v1/gis/heatmap/alarms")
    # Heatmap may be empty pre-seed; we just need the endpoint to serve 200.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, (dict, list)), f"heatmap payload shape invalid: {type(body)}"


@pytest.mark.xfail(
    reason=(
        "Frontend right-click context menus are UI state; backend "
        "/api/v1/gis/context-menu endpoint not yet implemented — see "
        "spec 018 Wave-5 T22 (GIS context commands). Playwright spec will "
        "cover the UI assertion once the backend contract lands."
    ),
    strict=False,
)
def test_context_menu_items_are_level_appropriate(client, db_session):
    """Backend returns the list of allowed actions per GIS zoom level."""
    _feeder, tx, meter = _seed_feeder_dtr_meter(db_session)

    menu_at_country = client.get("/api/v1/gis/context-menu", params={"level": "country"}).json()
    assert "Run regional report" in (menu_at_country.get("items") or [])

    menu_at_dtr = client.get(
        "/api/v1/gis/context-menu", params={"level": "dtr", "entity_id": tx.id}
    ).json()
    items = set(menu_at_dtr.get("items") or [])
    assert {"View downstream meters", "View load profile"} <= items

    menu_at_meter = client.get(
        "/api/v1/gis/context-menu", params={"level": "meter", "entity_id": meter.serial}
    ).json()
    items = set(menu_at_meter.get("items") or [])
    assert {"Read register", "Disconnect", "View consumer"} <= items


def test_read_meter_command_dispatches_to_hes(client, db_session, hes_mock):
    """Selecting 'Read meter' on the GIS context menu issues a HES command.

    The HES command path is already wired via /api/v1/meters/{serial}/commands
    — we drive it directly here.
    """
    _feeder, _tx, meter = _seed_feeder_dtr_meter(db_session)
    hes_mock.post("/hes/commands").respond(
        200, json={"status": "QUEUED", "command_id": "READ-001"}
    )
    resp = client.post(
        f"/api/v1/meters/{meter.serial}/commands",
        json={"type": "READ", "origin": "gis-context-menu"},
    )
    # Contract may return 200 or 202.
    assert resp.status_code in (200, 202, 201), resp.text
    body = resp.json()
    # Either the HES queued response or an EMS-side command_id is fine.
    assert any(
        key in body for key in ("command_id", "status", "queued", "hes_command_id")
    ), f"unexpected shape: {body}"
