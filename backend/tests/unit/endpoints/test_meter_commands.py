"""W2.T8 / W2.T9 — meter connect/disconnect + batch disconnect via HES."""
from __future__ import annotations

from app.models.command_log import CommandLog


def test_disconnect_publishes_to_hes_and_logs_queued(client, fake_hes, seed_meter, db):
    meter = seed_meter("M-T8-01")

    resp = client.post(f"/api/v1/meters/{meter.serial}/disconnect")
    assert resp.status_code == 202, resp.text
    body = resp.json()

    # Contract: endpoint returns a command_id + QUEUED; does NOT change relay_state.
    assert body["command_type"] == "DISCONNECT"
    assert body["status"] == "QUEUED"
    assert body["command_id"]

    # HES was actually called.
    assert any(c[0] == "post_command" for c in fake_hes.calls)
    hes_kwargs = fake_hes.calls[0][1]
    assert hes_kwargs["type"] == "DISCONNECT"
    assert hes_kwargs["meter_serial"] == "M-T8-01"

    # Command log row persisted.
    row = db.query(CommandLog).filter(CommandLog.id == body["command_id"]).first()
    assert row is not None
    assert row.status == "QUEUED"
    assert row.command_type == "DISCONNECT"

    # Meter's relay_state is untouched — only Kafka CONFIRMED mutates it.
    db.refresh(meter)
    assert meter.relay_state.value == "connected"


def test_connect_publishes_to_hes(client, fake_hes, seed_meter):
    meter = seed_meter("M-T8-02")
    resp = client.post(f"/api/v1/meters/{meter.serial}/connect")
    assert resp.status_code == 202
    assert resp.json()["command_type"] == "CONNECT"
    assert fake_hes.calls[0][1]["type"] == "CONNECT"


def test_disconnect_unknown_meter_returns_404(client, fake_hes):
    resp = client.post("/api/v1/meters/UNKNOWN/disconnect")
    assert resp.status_code == 404


def test_disconnect_hes_circuit_open_returns_503(client, fake_hes, seed_meter, db):
    from app.services._resilient_http import CircuitBreakerError

    meter = seed_meter("M-T8-03")
    fake_hes.raise_exc = CircuitBreakerError("HES open")
    resp = client.post(f"/api/v1/meters/{meter.serial}/disconnect")
    assert resp.status_code == 503
    # Row persists as FAILED so operators can see the attempt.
    rows = db.query(CommandLog).filter(CommandLog.meter_serial == meter.serial).all()
    assert any(r.status == "FAILED" for r in rows)


def test_batch_disconnect_concurrency_and_per_meter_rows(client, fake_hes, seed_meter, db):
    serials = [f"M-BATCH-{i:03d}" for i in range(25)]
    for s in serials:
        seed_meter(s)

    resp = client.post(
        "/api/v1/meters/batch/disconnect",
        json={"meter_serials": serials, "reason": "load-shedding block 2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 25
    assert body["queued"] == 25
    assert body["failed"] == 0
    assert len(body["results"]) == 25

    # One command_log row per meter.
    assert db.query(CommandLog).count() == 25


def test_batch_disconnect_skips_missing_meters(client, fake_hes, seed_meter, db):
    seed_meter("M-BATCH-A")
    resp = client.post(
        "/api/v1/meters/batch/disconnect",
        json={"meter_serials": ["M-BATCH-A", "UNKNOWN-1", "UNKNOWN-2"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["queued"] == 1
    assert body["failed"] == 2
    by_serial = {r["meter_serial"]: r for r in body["results"]}
    assert by_serial["UNKNOWN-1"]["status"] == "FAILED"
    assert "meter_not_found" in (by_serial["UNKNOWN-1"]["error"] or "")
