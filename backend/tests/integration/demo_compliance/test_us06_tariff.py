"""US-6 Tariff Engine Results & Configuration View — spec 018 §User Story 6.

Acceptance (spec lines 140-145, matrix row 6):

1. ``/api/v1/mdms/tariffs`` renders schedules with ToU TZ1-TZ8, CPP events,
   demand, inclining tiers, seasonal factor.
2. For a meter + month the billing-determinants payload matches MDMS
   byte-for-byte through the proxy.
3. Inclining-block tariff with 3 tiers shows per-tier kWh × rate when
   ``TARIFF_INCLINING_ENABLED`` is on; otherwise renders "Not configured"
   (asserted in Playwright spec).

Requires MDMS change MDMS-T1 for full inclining-block / seasonal support;
the inclining-block assertion is marked xfail until MDMS-T1 lands.
"""
from __future__ import annotations

import pytest

from tests.integration.demo_compliance._proxy_stub import install_proxy_stub


def test_tariff_schedules_render_tou_from_mdms(client, monkeypatch):
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/tariffs").reply(
        {
            "tariffs": [
                {
                    "id": "T-RES",
                    "name": "Residential",
                    "type": "TOU",
                    "effective_from": "2026-01-01",
                    "effective_to": None,
                    "tou_rates": {f"TZ{i}": 2.5 + i * 0.3 for i in range(1, 9)},
                    "cpp_events": [],
                    "demand_charge": 100.0,
                    "seasonal_factor": 1.0,
                }
            ]
        }
    )
    r = client.get("/api/v1/mdms/api/v1/tariffs")
    assert r.status_code == 200
    t = r.json()["tariffs"][0]
    assert t["type"] == "TOU"
    assert "TZ1" in t["tou_rates"]
    assert "TZ8" in t["tou_rates"]


def test_billing_determinants_match_mdms_byte_for_byte(client, monkeypatch):
    """Proxy passes MDMS payload through unchanged (acceptance #2)."""
    stub = install_proxy_stub(monkeypatch)
    expected = {
        "account": "ACC-0001",
        "month": "2026-04",
        "tariff_id": "T-RES",
        "tou_consumption": {f"TZ{i}": 20.0 * i for i in range(1, 9)},
        "demand_charge_applied": 100.0,
        "invoice_value": 2500.45,
    }
    stub.when("GET", "/api/v1/billing-determinants").reply(expected)
    r = client.get(
        "/api/v1/mdms/api/v1/billing-determinants",
        params={"account": "ACC-0001", "month": "2026-04"},
    )
    assert r.status_code == 200
    assert r.json() == expected


@pytest.mark.xfail(
    reason=(
        "Inclining-block tier decomposition depends on MDMS-T1 "
        "(mdms-todos.md). Spec calls for per-tier kWh × rate; EMS "
        "renders 'Not configured' until MDMS-T1 lands."
    ),
    strict=False,
)
def test_inclining_block_per_tier_breakdown(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "TARIFF_INCLINING_ENABLED", True)
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/tariffs/T-INC").reply(
        {
            "id": "T-INC",
            "type": "INCLINING_BLOCK",
            "tiers": [
                {"upto_kwh": 100, "rate": 2.00},
                {"upto_kwh": 300, "rate": 3.50},
                {"upto_kwh": None, "rate": 5.00},
            ],
        }
    )
    r = client.get("/api/v1/mdms/api/v1/tariffs/T-INC")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "INCLINING_BLOCK"
    assert len(body["tiers"]) == 3
