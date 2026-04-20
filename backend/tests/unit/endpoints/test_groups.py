"""Unit tests for spec 018 W4.T3 virtual object group CRUD + resolver."""
from __future__ import annotations

import uuid

import pytest

from app.models.meter import Feeder, Meter, MeterStatus, RelayState, Transformer
from app.models.virtual_object_group import VirtualObjectGroup
from app.services.group_resolver import resolve_group_members


def _seed_topology(db, n_meters=3, feeder_name="FDR-A", dtr_name="DTR-A",
                   substation="SS-A"):
    f = Feeder(name=feeder_name, substation=substation, voltage_kv=11.0, capacity_kva=500.0)
    db.add(f); db.flush()
    t = Transformer(
        name=dtr_name, feeder_id=f.id, latitude=0.0, longitude=0.0, capacity_kva=100.0,
    )
    db.add(t); db.flush()
    serials = []
    for i in range(n_meters):
        m = Meter(
            serial=f"M-{dtr_name}-{i:03d}",
            transformer_id=t.id,
            status=MeterStatus.ONLINE,
            relay_state=RelayState.CONNECTED,
            latitude=0.0, longitude=0.0,
        )
        db.add(m)
        serials.append(m.serial)
    db.commit()
    return f, t, serials


# ── Endpoint happy path ────────────────────────────────────────────────────


def test_create_list_get_group(client):
    resp = client.post(
        "/api/v1/groups",
        json={
            "name": "Feeder A group",
            "description": "All of A",
            "selector": {"hierarchy": {"feeder_ids": ["FDR-A"]}},
            "shared_with_roles": ["OPERATOR"],
        },
    )
    assert resp.status_code == 201, resp.text
    gid = resp.json()["id"]

    # list
    resp = client.get("/api/v1/groups")
    assert resp.status_code == 200
    assert any(g["id"] == gid for g in resp.json())

    # detail
    resp = client.get(f"/api/v1/groups/{gid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Feeder A group"
    assert body["selector"]["hierarchy"]["feeder_ids"] == ["FDR-A"]


def test_get_group_not_found(client):
    resp = client.get(f"/api/v1/groups/{uuid.uuid4().hex}")
    assert resp.status_code == 404


def test_update_group(client):
    gid = client.post(
        "/api/v1/groups",
        json={"name": "orig", "selector": {}},
    ).json()["id"]
    resp = client.patch(f"/api/v1/groups/{gid}", json={"name": "renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"


def test_delete_group(client):
    gid = client.post("/api/v1/groups", json={"name": "todel", "selector": {}}).json()["id"]
    resp = client.delete(f"/api/v1/groups/{gid}")
    assert resp.status_code == 204
    assert client.get(f"/api/v1/groups/{gid}").status_code == 404


def test_members_resolve_by_feeder(client, db):
    _seed_topology(db, n_meters=4, feeder_name="FDR-R1", dtr_name="DTR-R1",
                   substation="SS-R1")
    gid = client.post(
        "/api/v1/groups",
        json={
            "name": "feeder-r1",
            "selector": {"hierarchy": {"feeder_ids": ["FDR-R1"]}},
        },
    ).json()["id"]
    resp = client.get(f"/api/v1/groups/{gid}/members")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 4
    for s in body["meter_serials"]:
        assert s.startswith("M-DTR-R1-")


# ── Resolver unit tests ────────────────────────────────────────────────────


def test_resolver_empty_hierarchy_returns_all(db):
    _seed_topology(db, n_meters=2, feeder_name="F-all", dtr_name="D-all",
                   substation="SS-all")
    g = VirtualObjectGroup(
        id=uuid.uuid4().hex, name="x", selector={}, owner_user_id="42",
    )
    assert len(resolve_group_members(db, g)) == 2


def test_resolver_by_dtr(db):
    _seed_topology(db, n_meters=3, feeder_name="F-d", dtr_name="D-target",
                   substation="SS-d")
    _seed_topology(db, n_meters=2, feeder_name="F-e", dtr_name="D-other",
                   substation="SS-e")
    g = VirtualObjectGroup(
        id=uuid.uuid4().hex,
        name="by-dtr",
        selector={"hierarchy": {"dtr_ids": ["D-target"]}},
        owner_user_id="42",
    )
    out = resolve_group_members(db, g)
    assert len(out) == 3
    assert all("D-target" in s for s in out)


def test_resolver_exclude_filter(db):
    _seed_topology(db, n_meters=3, feeder_name="F-x", dtr_name="D-x",
                   substation="SS-x")
    g = VirtualObjectGroup(
        id=uuid.uuid4().hex,
        name="excl",
        selector={
            "hierarchy": {"feeder_ids": ["F-x"]},
            "filters": {"meter_serials_exclude": ["M-D-x-001"]},
        },
        owner_user_id="42",
    )
    out = resolve_group_members(db, g)
    assert "M-D-x-001" not in out
    assert len(out) == 2


def test_resolver_meter_status_filter(db):
    f = Feeder(name="F-s", substation="SS-s", voltage_kv=11.0, capacity_kva=500.0)
    db.add(f); db.flush()
    t = Transformer(name="D-s", feeder_id=f.id, latitude=0.0, longitude=0.0,
                    capacity_kva=100.0)
    db.add(t); db.flush()
    db.add(Meter(serial="S1", transformer_id=t.id, status=MeterStatus.ONLINE,
                 relay_state=RelayState.CONNECTED, latitude=0.0, longitude=0.0))
    db.add(Meter(serial="S2", transformer_id=t.id, status=MeterStatus.OFFLINE,
                 relay_state=RelayState.CONNECTED, latitude=0.0, longitude=0.0))
    db.commit()

    g = VirtualObjectGroup(
        id=uuid.uuid4().hex,
        name="offline",
        selector={
            "hierarchy": {"feeder_ids": ["F-s"]},
            "filters": {"meter_status": MeterStatus.OFFLINE.value},
        },
        owner_user_id="42",
    )
    out = resolve_group_members(db, g)
    assert out == ["S2"]
