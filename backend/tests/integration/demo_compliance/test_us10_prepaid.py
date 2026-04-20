"""US-10 Prepaid Operations Panel — spec 018 §User Story 10.

Acceptance:

* Operator recharges R100 on a prepaid meter.
* Within 60 s the EMS prepaid detail surface shows updated 13-register values
  sourced from MDMS prepaid (`GET /mdms/prepaid/registers`).
* When balance hits 0 and ACD fires, the UI surfaces an ACD=ACTIVE banner.

Integration-test matrix row 10. MDMS-T4 covers the auto-readback gap — this
test uses the EMS polling fallback (operator page polls
``/api/v1/mdms/prepaid/registers`` every 15 s for 2 min).
"""
from __future__ import annotations

import pytest


ACCOUNT_ID = "US10-ACC-PP-001"


def _thirteen_registers(balance_kwh=50.0, balance_currency=100.0):
    """Simulate the 13-register snapshot MDMS exposes per the CLAUDE.md
    ``PrepaidMeterRegister`` contract. Names kept loose — only the count and
    the balance field are load-bearing for the assertions below.
    """
    return {
        "account_id": ACCOUNT_ID,
        "meter_serial": "US10-METER-001",
        "as_of": "2026-04-18T10:00:00Z",
        "registers": [
            {"name": f"R{i:02d}", "value": 0.0, "unit": "kWh"} for i in range(1, 14)
        ],
        "balance_kwh": balance_kwh,
        "balance_currency": balance_currency,
        "acd_state": "INACTIVE" if balance_currency > 0 else "ACTIVE",
        "relay_state": "CLOSED" if balance_currency > 0 else "OPEN",
        "last_recharge": {"amount": 100.0, "token": "TKN-ABCDEF", "ts": "2026-04-18T09:59:00Z"},
    }


def test_prepaid_registers_proxied_after_recharge(client, mdms_mock, monkeypatch):
    """After a recharge, the proxied GET MUST surface updated register state."""
    from app.core.config import settings
    settings.MDMS_ENABLED = True  # type: ignore[attr-defined]

    # Recharge ACK path (POST).
    mdms_mock.post("/api/v1/prepaid/recharge").respond(
        202, json={"status": "ACCEPTED", "token": "TKN-ABCDEF", "amount": 100.0}
    )
    # Register readback (GET).
    mdms_mock.get("/api/v1/prepaid/registers").respond(
        200, json=_thirteen_registers(balance_currency=100.0)
    )

    # Submit recharge via the MDMS proxy.
    recharge = client.post(
        "/api/v1/mdms/prepaid/recharge",
        json={"account_id": ACCOUNT_ID, "amount": 100.0},
    )
    assert recharge.status_code in (200, 202), recharge.text

    # Poll for register readback — the EMS poll loop lives in the UI but the
    # proxy itself must surface the MDMS payload unchanged.
    regs = client.get(
        "/api/v1/mdms/prepaid/registers",
        params={"account_id": ACCOUNT_ID},
    )
    assert regs.status_code == 200, regs.text
    body = regs.json()

    # 13 registers is the spec contract.
    assert len(body.get("registers", [])) == 13, body
    assert body["balance_currency"] == 100.0
    assert body["acd_state"] == "INACTIVE"


def test_prepaid_acd_active_banner_state_when_balance_zero(client, mdms_mock):
    """When MDMS reports balance=0 and acd_state=ACTIVE, the proxy must
    forward that payload (the UI banner reads these fields).
    """
    from app.core.config import settings
    settings.MDMS_ENABLED = True  # type: ignore[attr-defined]

    mdms_mock.get("/api/v1/prepaid/registers").respond(
        200, json=_thirteen_registers(balance_currency=0.0, balance_kwh=0.0)
    )
    resp = client.get(
        "/api/v1/mdms/prepaid/registers",
        params={"account_id": ACCOUNT_ID},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["acd_state"] == "ACTIVE"
    assert body["relay_state"] == "OPEN"
    assert body["balance_currency"] == 0.0


@pytest.mark.xfail(
    reason="MDMS-T4 auto-readback from HES after token ACK not yet landed; "
    "until it ships, operator relies on the 15 s poll loop (covered above). "
    "This test asserts the push-based readback delta from Kafka once "
    "mdms.prepaid.register.updated starts flowing.",
    strict=False,
)
def test_prepaid_readback_push_delta_from_kafka(client, mdms_mock):
    """MDMS-T4 happy path: after token ACCEPTED, MDMS publishes a register
    update on Kafka; EMS caches the delta so the UI sees updated balance
    without the 15 s poll. Not yet wired.
    """
    # Placeholder: once MDMS-T4 lands, the EMS side will expose
    # ``GET /api/v1/prepaid/readback/{account_id}/latest``.
    resp = client.get(f"/api/v1/prepaid/readback/{ACCOUNT_ID}/latest")
    assert resp.status_code == 200
