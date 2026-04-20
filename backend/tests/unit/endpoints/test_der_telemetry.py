"""Spec 018 W3.T11/T12 — der telemetry + feeder aggregate endpoints.

Exercises the happy path (rows in der_telemetry), the empty-window banner
path, and the feeder aggregation grouping.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.der_ems import DERAssetEMS


# ── Isolate table creation: the shared conftest calls
# Base.metadata.create_all() which fails on SQLite for models that use
# PostgreSQL-only ARRAY columns (e.g. outage_incident). Override the engine
# fixture here to create only the tables this suite needs.


_TABLES_FOR_SUITE = (
    "users", "feeders", "transformers", "meters", "der_asset", "der_command",
)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_FOR_SUITE if t in Base.metadata.tables]
    Base.metadata.create_all(eng, tables=tables)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def SessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Fixtures ──


@pytest.fixture
def seed_der_assets(db):
    assets = [
        DERAssetEMS(id="PV-A", type="pv", name="PV Feeder A", feeder_id="FDR-A",
                    dtr_id="DTR-A", capacity_kw=50.0),
        DERAssetEMS(id="PV-B", type="pv", name="PV Feeder A #2", feeder_id="FDR-A",
                    dtr_id="DTR-A", capacity_kw=30.0),
        DERAssetEMS(id="BESS-A", type="bess", name="BESS A", feeder_id="FDR-A",
                    dtr_id="DTR-A", capacity_kw=20.0, capacity_kwh=40.0),
        DERAssetEMS(id="EV-B", type="ev", name="EV Feeder B", feeder_id="FDR-B",
                    dtr_id="DTR-B", capacity_kw=22.0),
    ]
    for a in assets:
        db.add(a)
    db.commit()
    return assets


@pytest.fixture
def seed_der_table(engine, db):
    """The der_telemetry table is Postgres-partitioned in prod. For unit
    tests we create a plain in-memory table with the same columns."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS der_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT,
                ts TIMESTAMP,
                state TEXT,
                active_power_kw REAL,
                reactive_power_kvar REAL,
                soc_pct REAL,
                session_energy_kwh REAL,
                achievement_rate_pct REAL,
                curtailment_pct REAL
            )
            """
        )
    )
    db.commit()


def _insert_telemetry(db, asset_id: str, minutes_ago: int, **kw):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    db.execute(
        text(
            """
            INSERT INTO der_telemetry
              (asset_id, ts, state, active_power_kw, reactive_power_kvar,
               soc_pct, session_energy_kwh, achievement_rate_pct, curtailment_pct)
            VALUES (:a, :t, :s, :ap, :rp, :soc, :se, :ar, :cp)
            """
        ),
        {
            "a": asset_id, "t": ts,
            "s": kw.get("state", "online"),
            "ap": kw.get("active_power_kw"),
            "rp": kw.get("reactive_power_kvar"),
            "soc": kw.get("soc_pct"),
            "se": kw.get("session_energy_kwh"),
            "ar": kw.get("achievement_rate_pct"),
            "cp": kw.get("curtailment_pct"),
        },
    )
    db.commit()


# ── Tests ──


def test_telemetry_empty_table_returns_banner(client, seed_der_assets):
    r = client.get("/api/v1/der/telemetry?type=pv&window=24h")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "pv"
    assert body["banner"]
    # Assets are still returned (shape stable); just with no telemetry.
    assert len(body["assets"]) == 2
    assert all(a.get("last_ts") is None for a in body["assets"])


def test_telemetry_latest_per_asset(client, seed_der_assets, seed_der_table, db):
    _insert_telemetry(db, "PV-A", 30, active_power_kw=12.5, state="online", achievement_rate_pct=78.0)
    _insert_telemetry(db, "PV-A", 10, active_power_kw=15.0, state="online", achievement_rate_pct=85.0)
    _insert_telemetry(db, "PV-B", 5,  active_power_kw=8.0, state="online")

    r = client.get("/api/v1/der/telemetry?type=pv&window=24h")
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {a["id"]: a for a in body["assets"]}
    assert by_id["PV-A"]["current_output_kw"] == 15.0
    assert by_id["PV-A"]["inverter_online"] is True
    assert by_id["PV-B"]["current_output_kw"] == 8.0
    # Aggregate: at least one bucket with total ~15 + 8 = 23
    assert body["aggregate"]
    total = sum(b["total_kw"] for b in body["aggregate"])
    assert total > 0


def test_feeder_aggregate_stacks_by_type(client, seed_der_assets, seed_der_table, db):
    _insert_telemetry(db, "PV-A",   10, active_power_kw=10.0)
    _insert_telemetry(db, "BESS-A", 10, active_power_kw=5.0)
    _insert_telemetry(db, "EV-B",   10, active_power_kw=9.0)  # different feeder

    r = client.get("/api/v1/der/feeder/FDR-A/aggregate?window=1h")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feeder_id"] == "FDR-A"
    assert body["assets_by_type"]["pv"]
    assert body["assets_by_type"]["bess"]
    # Only feeder-A telemetry contributes; EV-B's 9 kW should not leak in.
    totals = sum(b["pv_kw"] + b["bess_kw"] + b["ev_kw"] for b in body["buckets"])
    assert totals > 0
    assert all(b["ev_kw"] == 0 for b in body["buckets"])


def test_feeder_aggregate_no_assets(client):
    r = client.get("/api/v1/der/feeder/FDR-UNKNOWN/aggregate")
    assert r.status_code == 200
    body = r.json()
    assert body["buckets"] == []
    assert "No DER assets" in (body["banner"] or "")
