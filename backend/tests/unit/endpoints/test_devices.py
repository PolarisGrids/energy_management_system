"""W4 / no-mock-data — unified device search endpoints."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.meter import Feeder, Meter, MeterStatus, RelayState, Transformer


class _FakeMDMS:
    def __init__(self):
        self.consumers_payload = {"items": []}
        self.hierarchy_payload = {"tree": []}
        self.calls: list[tuple[str, dict]] = []

    async def search_consumers(self, query: str, limit: int = 20):
        self.calls.append(("search_consumers", {"q": query, "limit": limit}))
        return self.consumers_payload

    async def get_hierarchy(self, node=None):
        self.calls.append(("get_hierarchy", {"node": node}))
        return self.hierarchy_payload


@pytest.fixture
def fake_mdms(monkeypatch):
    fake = _FakeMDMS()
    import app.api.v1.endpoints.devices as devices_ep

    monkeypatch.setattr(devices_ep, "mdms_client", fake)
    monkeypatch.setattr(settings, "MDMS_ENABLED", True)
    yield fake


@pytest.fixture
def seed_inventory(db):
    feeder = Feeder(name="FDR-Alpha", substation="SS-North", voltage_kv=11.0, capacity_kva=500.0)
    db.add(feeder)
    db.flush()
    tx = Transformer(
        name="DTR-42",
        feeder_id=feeder.id,
        latitude=0.0,
        longitude=0.0,
        capacity_kva=100.0,
    )
    db.add(tx)
    db.flush()
    meter = Meter(
        serial="M0001",
        transformer_id=tx.id,
        status=MeterStatus.ONLINE,
        relay_state=RelayState.CONNECTED,
        latitude=0.0,
        longitude=0.0,
        customer_name="Alice Example",
        account_number="ACC-777",
    )
    db.add(meter)
    db.commit()
    return feeder, tx, meter


def test_search_merges_mdms_consumers_and_local_meters(client, fake_mdms, seed_inventory):
    fake_mdms.consumers_payload = {
        "items": [
            {
                "account_number": "ACC-500",
                "consumer_name": "Bob Example",
                "meter_serial": "M0500",
                "feeder": "FDR-Beta",
            }
        ]
    }
    r = client.get("/api/v1/devices/search", params={"q": "Example", "limit": 20})
    assert r.status_code == 200
    body = r.json()
    types = {item["type"] for item in body["items"]}
    # MDMS consumer and local meter both surfaced.
    assert "consumer" in types
    assert "meter" in types
    assert body["count"] >= 2


def test_search_type_filter(client, fake_mdms, seed_inventory):
    r = client.get("/api/v1/devices/search", params={"q": "FDR", "type": "feeder"})
    assert r.status_code == 200
    body = r.json()
    assert all(i["type"] == "feeder" for i in body["items"])
    assert any(i["name"] == "FDR-Alpha" for i in body["items"])
    # MDMS consumer lookup must not be called under type=feeder.
    assert not any(c[0] == "search_consumers" for c in fake_mdms.calls)


def test_search_dtr_local(client, fake_mdms, seed_inventory):
    r = client.get("/api/v1/devices/search", params={"q": "DTR-42", "type": "dtr"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["name"] == "DTR-42" for i in items)


def test_search_meter_local(client, fake_mdms, seed_inventory):
    r = client.get("/api/v1/devices/search", params={"q": "ACC-777", "type": "meter"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["account"] == "ACC-777" for i in items)


def test_search_rejects_bad_type(client, fake_mdms):
    r = client.get("/api/v1/devices/search", params={"q": "x", "type": "building"})
    assert r.status_code == 422


def test_search_mdms_off_local_only(client, fake_mdms, seed_inventory, monkeypatch):
    monkeypatch.setattr(settings, "MDMS_ENABLED", False)
    r = client.get("/api/v1/devices/search", params={"q": "M0001"})
    assert r.status_code == 200
    assert fake_mdms.calls == []
    items = r.json()["items"]
    assert any(i["meter_serial"] == "M0001" for i in items)


def test_hierarchy_mdms_on_returns_upstream_tree(client, fake_mdms, seed_inventory):
    fake_mdms.hierarchy_payload = {"tree": [{"id": "feeder:1", "name": "FDR-Alpha"}]}
    r = client.get("/api/v1/devices/hierarchy")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mdms"


def test_hierarchy_fallback_builds_local_tree(client, fake_mdms, seed_inventory, monkeypatch):
    monkeypatch.setattr(settings, "MDMS_ENABLED", False)
    r = client.get("/api/v1/devices/hierarchy")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "ems-local"
    assert len(body["tree"]) >= 1
    node = body["tree"][0]
    assert node["level"] == "feeder"
    # Expect a DTR child
    dtr_children = [c for c in node.get("children", []) if c["level"] == "dtr"]
    assert dtr_children
