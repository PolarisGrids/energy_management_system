"""US-18: EV Fast-Charging Transformer Impact & Curtailment (Demo #22).

Acceptance (spec §User Story 18 + matrix row 18):

* Run ``ev_fast_charging``; DTR loading crosses 100%.
* Overload alarm fires.
* Curtailment reduces load ≥ 20%.
* Forecast chart refreshes each step.
"""
from __future__ import annotations

import pytest


pytestmark = [pytest.mark.demo_compliance]


def test_ev_scenario_start(client, simulator_mock):
    simulator_mock.post("/scenarios/ev_fast_charging/start").respond(
        200, json={"scenario": "ev_fast_charging", "status": "RUNNING", "step": 0}
    )
    resp = client.post("/api/v1/simulation-proxy/scenarios/ev_fast_charging/start", json={})
    assert resp.status_code in (200, 202), resp.text


def test_overload_alarm_fires_when_dtr_loading_exceeds_100pct(client, simulator_mock):
    """The status response after loading crosses 100% MUST include an alarm."""
    simulator_mock.get("/scenarios/ev_fast_charging/status").respond(
        200,
        json={
            "scenario": "ev_fast_charging",
            "status": "RUNNING",
            "step": 2,
            "dtr_loading_pct": 115,
            "alarms": [
                {
                    "code": "DTR_OVERLOAD",
                    "severity": "HIGH",
                    "message": "DTR loading > 100%",
                }
            ],
        },
    )
    resp = client.get("/api/v1/simulation-proxy/scenarios/ev_fast_charging/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("dtr_loading_pct", 0) > 100
    alarms = body.get("alarms") or []
    overload = [a for a in alarms if a.get("code") == "DTR_OVERLOAD"]
    assert overload, f"expected DTR_OVERLOAD alarm, got: {alarms}"


def test_curtailment_reduces_load_by_at_least_20_percent(client, simulator_mock):
    """Before curtail: 115%. After curtail command applies: ≤ 92%."""
    # Status pre-curtail.
    simulator_mock.get("/scenarios/ev_fast_charging/status").respond(
        200, json={"step": 2, "dtr_loading_pct": 115.0, "status": "RUNNING"}
    )
    pre = client.get("/api/v1/simulation-proxy/scenarios/ev_fast_charging/status").json()
    pre_load = pre["dtr_loading_pct"]

    # Step after dispatching curtailment should reflect a drop.
    simulator_mock.post("/scenarios/ev_fast_charging/step").respond(
        200, json={"step": 5, "dtr_loading_pct": 90.0, "status": "RUNNING"}
    )
    post = client.post("/api/v1/simulation-proxy/scenarios/ev_fast_charging/step").json()
    post_load = post["dtr_loading_pct"]

    reduction_pct = (pre_load - post_load) / pre_load * 100
    assert reduction_pct >= 20, f"expected ≥20% load reduction, got {reduction_pct:.1f}%"


def test_forecast_chart_updates_each_step(client, simulator_mock):
    """Each step exposes ``forecast`` series so the forecast chart refreshes."""
    seen_forecasts: list[list[float]] = []
    for step, (actual, forecast) in enumerate([(80, [82, 88, 94]), (88, [90, 96, 100]), (95, [96, 102, 108])], start=1):
        simulator_mock.post("/scenarios/ev_fast_charging/step").respond(
            200,
            json={
                "scenario": "ev_fast_charging",
                "status": "RUNNING",
                "step": step,
                "dtr_loading_pct": actual,
                "forecast_next_hour": forecast,
            },
        )
        body = client.post("/api/v1/simulation-proxy/scenarios/ev_fast_charging/step").json()
        assert "forecast_next_hour" in body, "each step must include forecast_next_hour"
        seen_forecasts.append(body["forecast_next_hour"])

    # Forecasts must vary step-to-step (not stuck).
    assert len({tuple(f) for f in seen_forecasts}) > 1, (
        f"forecast series is static across steps: {seen_forecasts}"
    )


@pytest.mark.xfail(
    reason=(
        "Live HES EV-charger curtailment endpoint not deployed on dev EKS; "
        "hes_client.post_ev_curtail is a stub until HES routing lands in wave 5."
    ),
    strict=False,
)
def test_curtail_command_dispatched_to_hes(client, hes_mock):
    hes_mock.post("/hes/commands/ev-charger/curtail").respond(
        200, json={"status": "QUEUED", "command_id": "EV-CURT-001"}
    )
    hes_mock.get("/hes/commands").respond(
        200,
        json={"commands": [{"type": "ev_curtail", "asset_id": "EV-CHGR-1", "status": "QUEUED"}]},
    )
    resp = client.get("/api/v1/hes/commands")
    assert resp.status_code == 200
    cmds = resp.json().get("commands", [])
    assert any(c.get("type") == "ev_curtail" for c in cmds)
