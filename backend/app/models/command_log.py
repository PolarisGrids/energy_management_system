"""Spec 018 `command_log` — HES meter-command lifecycle owned by EMS.

Distinct from legacy `hes_command_log` (display mirror). This table holds
command records EMS publishes to HES routing via `POST /api/v1/commands`;
Kafka `hesv2.command.status` consumer updates rows on ACK/EXECUTED/CONFIRMED/
FAILED/TIMEOUT.
"""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func


def _json_col():
    """Portable JSON column: JSONB on PostgreSQL, JSON elsewhere (SQLite unit tests)."""
    return JSON().with_variant(JSONB(), "postgresql")


def _uuid_col():
    """Portable UUID column: native UUID on PostgreSQL, CHAR(36) on SQLite."""
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")

from app.db.base import Base


class CommandLog(Base):
    __tablename__ = "command_log"

    id = Column(_uuid_col(), primary_key=True)  # command_id
    meter_serial = Column(String(100), nullable=False, index=True)
    command_type = Column(String(60), nullable=False)  # DISCONNECT / CONNECT / FOTA / etc.
    payload = Column(_json_col(), nullable=True)
    status = Column(String(20), nullable=False, default="QUEUED")
    # QUEUED -> ACK -> EXECUTED -> CONFIRMED / FAILED / TIMEOUT
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    acked_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    response_payload = Column(_json_col(), nullable=True)
    retry_count = Column(Integer, default=0)
    issuer_user_id = Column(String(200), nullable=True)
    trace_id = Column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_command_log_meter_serial_issued_at", "meter_serial", "issued_at"),
    )
