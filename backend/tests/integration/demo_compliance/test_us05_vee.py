"""US-5 VEE Pipeline Surfaced from MDMS — spec 018 §User Story 5.

Acceptance (spec lines 124-129, matrix row 5):

1. MDMS VEE has data today → summary renders totals and percentages that
   match MDMS (no ``NaN%``).
2. MDMS VEE returns zero → endpoint returns empty state; the frontend MUST
   render "No VEE activity in selected window" (asserted in Playwright spec).
3. Clicking a rule → exceptions page returns paginated MDMS rows.
4. Manual edit round-trips to ``POST /mdms/vee/edit`` via the proxy.
"""
from __future__ import annotations

from tests.integration.demo_compliance._proxy_stub import install_proxy_stub


def test_vee_summary_90_5_5_split_from_mdms(client, monkeypatch):
    """1000 reads split 900/50/50 → percentages 90/5/5, no NaN."""
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/vee/summary").reply(
        {
            "items": [
                {
                    "date": "2026-04-18",
                    "validated_count": 900,
                    "estimated_count": 50,
                    "failed_count": 50,
                    "rules": {
                        "HIGH_CONSUMPTION": 10,
                        "NEGATIVE_CONSUMPTION": 15,
                        "MISSING_INTERVAL": 25,
                    },
                }
            ]
        }
    )
    r = client.get("/api/v1/mdms/api/v1/vee/summary", params={"date": "2026-04-18"})
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    total = item["validated_count"] + item["estimated_count"] + item["failed_count"]
    assert total == 1000
    assert item["validated_count"] / total == 0.9


def test_vee_summary_empty_window_renders_empty_not_nan(client, monkeypatch):
    """Zero data → empty items list (UI shows empty state, never NaN)."""
    stub = install_proxy_stub(monkeypatch)
    stub.when("GET", "/api/v1/vee/summary").reply({"items": []})
    r = client.get("/api/v1/mdms/api/v1/vee/summary")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_vee_exceptions_per_rule_pagination(client, monkeypatch):
    stub = install_proxy_stub(monkeypatch)
    rows = [
        {
            "meter_serial": f"S{i:03d}",
            "rule_name": "HIGH_CONSUMPTION",
            "date": "2026-04-18",
            "original_value": 1000 + i,
            "validated_value": 500 + i,
            "status": "failed",
        }
        for i in range(10)
    ]
    stub.when("GET", "/api/v1/vee/exceptions").reply({"total": 10, "items": rows})
    r = client.get(
        "/api/v1/mdms/api/v1/vee/exceptions",
        params={"rule": "HIGH_CONSUMPTION", "page": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    assert len(body["items"]) == 10
    assert all(x["rule_name"] == "HIGH_CONSUMPTION" for x in body["items"])


def test_vee_manual_edit_roundtrips_via_proxy(client, monkeypatch):
    stub = install_proxy_stub(monkeypatch)
    stub.when("POST", "/api/v1/vee/edit").reply({"ok": True, "audit_id": "a-1"})
    r = client.post(
        "/api/v1/mdms/api/v1/vee/edit",
        json={
            "meter_serial": "S123",
            "timestamp": "2026-04-18T12:00:00+05:30",
            "new_value": 123.4,
            "reason": "US-5 test",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
