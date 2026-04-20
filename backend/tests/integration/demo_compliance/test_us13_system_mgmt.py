"""US-13 System Management: Supplier & Product Registry — spec 018 §User Story 13.

Acceptance (integration-test-matrix row 13):

* Seeded suppliers appear in the registry with per-supplier failure-rate +
  MTBF computed from meter status history.
* CSV import of 50 new meters bound to supplier + model succeeds and the
  imported rows appear in the registry.

Status: P3 feature. The backing endpoints (``/api/v1/system-mgmt/suppliers``
+ CSV import handler) are NOT yet implemented — tracked under W4.T15/T16.
All three acceptance tests are ``@pytest.mark.xfail`` until the endpoints
land. Shape of the assertions is frozen here so the endpoint contract
can't silently drift.
"""
from __future__ import annotations

import io

import pytest


pytestmark = pytest.mark.xfail(
    reason="System Management supplier registry endpoints not yet "
    "implemented (spec 018 W4.T15/T16). Once /api/v1/system-mgmt/* "
    "lands, remove this module-level xfail.",
    strict=False,
)


def test_supplier_registry_lists_seeded_suppliers(client):
    """Seeded suppliers from `supplier_registry` should surface with
    per-supplier metrics.
    """
    resp = client.get("/api/v1/system-mgmt/suppliers")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    # Each row must expose: name, meter_count, failure_rate_pct, mtbf_hours.
    for s in items:
        assert "name" in s
        assert "meter_count" in s
        assert "failure_rate_pct" in s
        assert "mtbf_hours" in s


def test_supplier_performance_mv_values_bounded(client):
    """failure_rate_pct bounded in [0, 100]; MTBF non-negative."""
    resp = client.get("/api/v1/system-mgmt/suppliers")
    for s in resp.json():
        assert 0 <= s["failure_rate_pct"] <= 100
        assert s["mtbf_hours"] >= 0


def test_bulk_meter_csv_import_registers_50_meters(client):
    """Upload a 50-row CSV → imported meters appear with supplier + model."""
    header = "meter_serial,supplier_name,model_name\n"
    rows = "\n".join(
        f"US13-CSV-{i:03d},ACME,Model-X" for i in range(50)
    )
    payload = header + rows + "\n"
    files = {"file": ("meters.csv", io.BytesIO(payload.encode()), "text/csv")}
    resp = client.post("/api/v1/system-mgmt/meters/import", files=files)
    assert resp.status_code == 201
    assert resp.json()["imported"] == 50

    # Listing now surfaces them.
    listed = client.get(
        "/api/v1/system-mgmt/meters", params={"supplier": "ACME", "limit": 100}
    )
    assert listed.status_code == 200
    serials = {m["serial_number"] for m in listed.json()}
    assert serials.issuperset({f"US13-CSV-{i:03d}" for i in range(50)})
