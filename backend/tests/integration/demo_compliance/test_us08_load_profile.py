"""US-8 Load Profiles by Customer Class — spec 018 §User Story 8.

Acceptance (spec lines 170-173, matrix row 8):

1. Class + date range → half-hourly curve renders with p50 (and p10/p90
   when MDMS-T3 landed).
2. Export CSV download matches MDMS payload within rounding.

p10/p90 path is xfail-marked until MDMS-T3 (load_profile_by_class MV) lands.
"""
from __future__ import annotations

import pytest

from tests.integration.demo_compliance._proxy_stub import install_proxy_stub


def test_load_profile_residential_week(client, monkeypatch):
    """Residential class, April 1-7 → 336 half-hour points (48 × 7), p50 present."""
    stub = install_proxy_stub(monkeypatch)
    points = [
        {
            "ts": f"2026-04-0{(i // 48) + 1}T{((i % 48) // 2):02d}:{'30' if i % 2 else '00'}:00+05:30",
            "p50_kw": 1.2 + 0.05 * (i % 48),
        }
        for i in range(336)
    ]
    stub.when("GET", "/api/v1/analytics/load-profile").reply(
        {"class": "residential", "points": points}
    )
    r = client.get(
        "/api/v1/mdms/api/v1/analytics/load-profile",
        params={"class": "residential", "from": "2026-04-01", "to": "2026-04-07"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["class"] == "residential"
    assert len(body["points"]) == 336
    assert all("p50_kw" in p for p in body["points"])


@pytest.mark.xfail(
    reason=(
        "p10/p90 anomaly bands depend on MDMS-T3 (load_profile_by_class MV). "
        "Until it lands, EMS renders only the p50 line — acceptance #1 "
        "says 'p10/p50/p90 if MDMS-T3 available'."
    ),
    strict=False,
)
def test_load_profile_p10_p90_bands_available(client, monkeypatch):
    stub = install_proxy_stub(monkeypatch)
    points = [
        {
            "ts": f"2026-04-01T{h:02d}:00:00+05:30",
            "p10_kw": 0.8,
            "p50_kw": 1.2,
            "p90_kw": 2.1,
        }
        for h in range(24)
    ]
    stub.when("GET", "/api/v1/analytics/load-profile").reply(
        {"class": "residential", "points": points}
    )
    r = client.get(
        "/api/v1/mdms/api/v1/analytics/load-profile",
        params={"class": "residential", "from": "2026-04-01", "to": "2026-04-01"},
    )
    body = r.json()
    assert all(
        all(k in p for k in ("p10_kw", "p50_kw", "p90_kw")) for p in body["points"]
    )


def test_csv_export_matches_mdms_payload(client, monkeypatch):
    stub = install_proxy_stub(monkeypatch)
    csv_payload = (
        "ts,class,p50_kw\n"
        "2026-04-01T00:00:00+05:30,residential,1.20\n"
        "2026-04-01T00:30:00+05:30,residential,1.25\n"
    )
    stub.when("GET", "/api/v1/analytics/load-profile").reply(
        content=csv_payload.encode(),
        headers={"content-type": "text/csv"},
    )
    r = client.get(
        "/api/v1/mdms/api/v1/analytics/load-profile",
        params={
            "class": "residential",
            "from": "2026-04-01",
            "to": "2026-04-01",
            "format": "csv",
        },
    )
    assert r.status_code == 200
    assert r.content == csv_payload.encode()
