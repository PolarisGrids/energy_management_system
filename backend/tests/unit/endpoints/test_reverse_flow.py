"""Spec 018 W3.T13 — reverse-flow endpoint tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.reverse_flow import ReverseFlowEvent


_TABLES_FOR_SUITE = (
    "users", "feeders", "transformers", "meters", "reverse_flow_event",
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


def _seed_event(db, **kwargs):
    row = ReverseFlowEvent(
        feeder_id=kwargs.get("feeder_id", "FDR-1"),
        status=kwargs.get("status", "OPEN"),
        net_flow_kw=kwargs.get("net_flow_kw", -12.5),
        detected_at=kwargs.get("detected_at", datetime.now(timezone.utc)),
        closed_at=kwargs.get("closed_at"),
        duration_s=kwargs.get("duration_s"),
        details=kwargs.get("details"),
    )
    db.add(row)
    db.commit()
    return row


def test_active_returns_only_open(client, db):
    _seed_event(db, feeder_id="FDR-A", status="OPEN", net_flow_kw=-20.0)
    _seed_event(db, feeder_id="FDR-B", status="CLOSED", net_flow_kw=-30.0,
                closed_at=datetime.now(timezone.utc),
                duration_s=400)
    r = client.get("/api/v1/reverse-flow/active")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["feeder_id"] == "FDR-A"
    assert body[0]["status"] == "OPEN"


def test_feeder_returns_history(client, db):
    _seed_event(db, feeder_id="FDR-A", status="CLOSED",
                detected_at=datetime.now(timezone.utc) - timedelta(hours=2),
                closed_at=datetime.now(timezone.utc) - timedelta(hours=1))
    _seed_event(db, feeder_id="FDR-A", status="OPEN")
    _seed_event(db, feeder_id="FDR-B", status="OPEN")

    r = client.get("/api/v1/reverse-flow/feeder/FDR-A")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    # Most recent first
    assert body[0]["status"] == "OPEN"
    assert body[1]["status"] == "CLOSED"


def test_list_filters_by_status(client, db):
    _seed_event(db, status="OPEN")
    _seed_event(db, status="CLOSED",
                closed_at=datetime.now(timezone.utc), duration_s=10)
    r = client.get("/api/v1/reverse-flow/?status=CLOSED")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["status"] == "CLOSED"
