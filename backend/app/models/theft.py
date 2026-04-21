"""ORM models for theft analysis — current score snapshot + run log.

`theft_score` holds one row per meter (upserted on every scorer run) and
drives the Theft Analysis dashboard. `theft_run_log` records each scorer
invocation so the UI can show "last refreshed N min ago" and ops can
reason about scheduler health.

Both tables live in the Polaris EMS DB — MDMS is read-only and never
modified by this feature.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


def _jsonb():
    # JSONB on Postgres, plain JSON elsewhere (keeps unit tests on SQLite green).
    from sqlalchemy import JSON
    return JSON().with_variant(JSONB(), "postgresql")


class TheftScore(Base):
    """Current theft-risk snapshot for a single meter.

    Upserted on every scorer pass. The full detector breakdown lives in
    ``detector_results`` — the UI drill-down consumes that JSONB directly.
    ``top_evidence`` is a compact 3-5 item array rendered as chips in the
    suspect-list table.
    """
    __tablename__ = "theft_score"

    device_identifier = Column(String(64), primary_key=True)
    meter_type = Column(String(32), nullable=True, index=True)
    account_id = Column(String(32), nullable=True, index=True)
    manufacturer = Column(String(128), nullable=True)
    sanctioned_load_kw = Column(Float, nullable=True)

    score = Column(Float, nullable=False, default=0.0)      # 0..100
    risk_tier = Column(String(16), nullable=False, default="low", index=True)

    fired_detectors = Column(_jsonb(), nullable=False,
                             server_default="[]")  # array of detector_ids
    top_evidence = Column(_jsonb(), nullable=False,
                          server_default="[]")     # compact chip summaries
    detector_results = Column(_jsonb(), nullable=False,
                              server_default="[]") # full detector payload

    computed_at = Column(DateTime(timezone=True), nullable=False,
                         server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_theft_score_score_desc", score.desc()),
        Index("ix_theft_score_tier_score", "risk_tier", score.desc()),
    )


class TheftRunLog(Base):
    """One row per scorer invocation."""
    __tablename__ = "theft_run_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    meters_scored = Column(Integer, nullable=False, default=0)
    meters_critical = Column(Integer, nullable=False, default=0)
    meters_high = Column(Integer, nullable=False, default=0)
    meters_medium = Column(Integer, nullable=False, default=0)
    meters_low = Column(Integer, nullable=False, default=0)
    trigger = Column(String(32), nullable=False, default="scheduled")  # scheduled|manual|startup
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_theft_run_log_started_at_desc", started_at.desc()),
    )
