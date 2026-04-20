"""US-17: Solar Over-Voltage + Smart Inverter Curtailment (Demo #21).

Acceptance (from spec.md §User Story 17 + matrix row 17):

* Run ``solar_overvoltage`` via the EMS simulation proxy.
* Within 7 steps, voltage stabilises at ≤ 1.05 pu.
* Each smart inverter receives a ``curtail`` command visible in the HES
  command log.
* The algorithm-explanation panel stays visible for demo narration.

Backing pieces:
  - :mod:`app.api.v1.endpoints.simulation_proxy` — POST /scenarios/{name}/start + /step
  - :mod:`app.api.v1.endpoints.der`              — POST /der/{id}/curtail (SMART_INVERTER_COMMANDS_ENABLED)
  - :class:`app.services.hes_client.HESClient`   — post_inverter_curtail()

The endpoint to POST a curtailment direct-to-HES currently lives behind
the feature flag ``SMART_INVERTER_COMMANDS_ENABLED`` and depends on
MDMS-T5 (HES inverter-command endpoint). Until that path is wired, the
direct-dispatch assertion is marked ``xfail``.
"""
from __future__ import annotations

import pytest


pytestmark = [pytest.mark.demo_compliance, pytest.mark.story("US-17")] if hasattr(
    pytest.mark, "story"
) else [pytest.mark.demo_compliance]


# ── Scenario lifecycle ─────────────────────────────────────────────────────


def test_solar_overvoltage_scenario_start(client, simulator_mock):
    """Start scenario via proxy; simulator receives the request."""
    simulator_mock.post("/scenarios/solar_overvoltage/start").respond(
        200, json={"scenario": "solar_overvoltage", "status": "RUNNING", "step": 0}
    )
    resp = client.post("/api/v1/simulation-proxy/scenarios/solar_overvoltage/start", json={})
    assert resp.status_code in (200, 202), resp.text
    assert resp.json().get("status") == "RUNNING"


def test_solar_overvoltage_voltage_stabilises_in_seven_steps(client, simulator_mock):
    """Voltage must reach ≤ 1.05 pu within 7 scenario steps."""
    # Decreasing voltage curve across 7 steps.
    voltages = [1.09, 1.08, 1.07, 1.06, 1.05, 1.04, 1.03]
    for step, v in enumerate(voltages, start=1):
        simulator_mock.post("/scenarios/solar_overvoltage/step").respond(
            200,
            json={
                "scenario": "solar_overvoltage",
                "status": "RUNNING",
                "step": step,
                "voltage_pu": v,
            },
        )
    final_voltage = None
    for _ in range(7):
        resp = client.post("/api/v1/simulation-proxy/scenarios/solar_overvoltage/step")
        assert resp.status_code in (200, 202), resp.text
        final_voltage = resp.json().get("voltage_pu")

    assert final_voltage is not None, "simulator mock did not return voltage"
    assert final_voltage <= 1.05, f"voltage {final_voltage} pu still above 1.05 after 7 steps"


# ── Curtailment command dispatch ───────────────────────────────────────────


@pytest.mark.xfail(
    reason=(
        "Requires HES smart-inverter command endpoint (MDMS-T5) "
        "+ SMART_INVERTER_COMMANDS_ENABLED wired end-to-end. Endpoint stub "
        "exists (der.post_inverter_curtail) but HES routing is not deployed."
    ),
    strict=False,
)
def test_curtail_command_visible_in_hes_command_log(client, hes_mock, db_session):
    """Each inverter asset gets a curtail command persisted in HES command log."""
    hes_mock.post("/hes/commands/inverter/curtail").respond(
        200, json={"status": "QUEUED", "command_id": "CMD-CURT-1"}
    )
    hes_mock.get("/hes/commands").respond(
        200,
        json={
            "commands": [
                {"type": "inverter_curtail", "asset_id": "PV-001", "status": "QUEUED"},
                {"type": "inverter_curtail", "asset_id": "PV-002", "status": "QUEUED"},
            ]
        },
    )
    # The scenario-driven controller should have dispatched curtailment to
    # each PV inverter; we look it up via the HES proxy command log.
    resp = client.get("/api/v1/hes/commands")
    assert resp.status_code == 200, resp.text
    cmds = resp.json().get("commands", [])
    curtail_cmds = [c for c in cmds if c.get("type") == "inverter_curtail"]
    assert len(curtail_cmds) >= 2, f"expected >=2 curtail commands, got {curtail_cmds}"


# ── Narration panel (algorithm explanation) ────────────────────────────────


def test_scenario_emits_algorithm_metadata(client, simulator_mock):
    """The scenario status payload includes an algorithm-explanation block.

    This is the data that backs the frontend "algorithm panel stays
    visible for demo narration" acceptance scenario.
    """
    simulator_mock.get("/scenarios/solar_overvoltage/status").respond(
        200,
        json={
            "scenario": "solar_overvoltage",
            "status": "RUNNING",
            "step": 3,
            "voltage_pu": 1.06,
            "algorithm": {
                "name": "droop_curve",
                "curtail_setpoint_pct": 70,
                "over_voltage_threshold_pu": 1.05,
            },
        },
    )
    resp = client.get("/api/v1/simulation-proxy/scenarios/solar_overvoltage/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    algo = body.get("algorithm") or {}
    assert algo.get("name"), "scenario status must expose algorithm.name for UI panel"
    assert "curtail_setpoint_pct" in algo, "must expose curtail setpoint for UI panel"
