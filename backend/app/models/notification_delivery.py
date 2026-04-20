"""Notification delivery log — spec 018 W4.T2.

One row per send attempt. Persisted regardless of transport outcome so the
operator UI can show a full delivery history and the rule engine can retry.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class _JsonbOrJson(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class NotificationDelivery(Base):
    """Every send attempt lands here (success or failure).

    ``status`` vocabulary:

    * ``SENT``      — provider accepted the message.
    * ``FAILED``    — provider errored or transport raised.
    * ``DISABLED``  — channel feature flag off — message was dropped.
    * ``QUEUED``    — quiet hours suppressed; email staged for later send.
    """

    __tablename__ = "notification_delivery"

    id = Column(String(36), primary_key=True)
    rule_id = Column(
        String(36),
        ForeignKey("alarm_rule.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    firing_id = Column(
        String(36),
        ForeignKey("alarm_rule_firing.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel = Column(String(20), nullable=False, index=True)  # email / sms / teams / push
    recipient = Column(Text, nullable=False)
    subject = Column(String(500), nullable=True)
    payload = Column(_JsonbOrJson, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    provider_reference = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    escalation_tier = Column(Integer, nullable=False, default=0)
    send_after = Column(DateTime(timezone=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    trace_id = Column(String(64), nullable=True)


__all__ = ["NotificationDelivery"]
