"""Alarm-rule engine models — spec 018 W4.T4 / W4.T5.

``alarm_rule`` — user-defined condition + action over a virtual object group.
``alarm_rule_firing`` — one row per unique (rule, dedup window) firing.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class _JsonbOrJson(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class AlarmRule(Base):
    """User-authored rule that fires notifications / actions.

    ``condition`` AST::

        {"source": "alarm_event|der_telemetry",
         "field":  "severity|alarm_type|load_pct|active_power_kw|...",
         "op":     ">|>=|<|<=|==|in|contains",
         "value":  <scalar or list>,
         "duration_seconds": 0 }

    ``action``::

        {"channels": [{"type": "email|sms|teams|push",
                       "recipients": ["ops@x.co"],
                       "template": "optional subject/body override"}],
         "webhook_url": "https://...",
         "priority": 1..5,
         "notes": "..."}

    ``schedule`` (optional)::

        {"quiet_hours": {"start": "22:00", "end": "06:00", "tz": "Asia/Kolkata"},
         "tiers": [{"after_seconds": 300,
                    "channels": [{"type": "sms",
                                   "recipients": ["supervisor@x.co"]}]}]}
    """

    __tablename__ = "alarm_rule"

    id = Column(String(36), primary_key=True)
    group_id = Column(
        String(36),
        ForeignKey("virtual_object_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)
    condition = Column(_JsonbOrJson, nullable=False, default=dict)
    action = Column(_JsonbOrJson, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=3)  # 1 (highest) .. 5
    active = Column(Boolean, nullable=False, default=True, index=True)
    schedule = Column(_JsonbOrJson, nullable=True)
    dedup_window_seconds = Column(Integer, nullable=False, default=300)
    owner_user_id = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    firings = relationship(
        "AlarmRuleFiring",
        back_populates="rule",
        cascade="all, delete-orphan",
    )


class AlarmRuleFiring(Base):
    __tablename__ = "alarm_rule_firing"

    id = Column(String(36), primary_key=True)
    rule_id = Column(
        String(36),
        ForeignKey("alarm_rule.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dedup_key = Column(String(200), nullable=False, index=True)
    match_count = Column(Integer, nullable=False, default=0)
    sample_meter_serial = Column(String(100), nullable=True)
    sample_dtr_id = Column(String(100), nullable=True)
    context = Column(_JsonbOrJson, nullable=True)  # snapshot of matched events
    trace_id = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(200), nullable=True)
    escalation_tier = Column(Integer, nullable=False, default=0)

    rule = relationship("AlarmRule", back_populates="firings")


__all__ = ["AlarmRule", "AlarmRuleFiring"]
