"""Notification + reliability models — spec 016-notifications-outage (MVP).

MVP scope: operator paging only. Consumer-facing notifications are OUT of
scope (gated OFF via CONSUMER_NOTIFICATIONS_ENABLED); the tables below keep
locale/channel columns for future expansion.
"""
from __future__ import annotations

import enum

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    TEAMS = "teams"
    PUSH = "push"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DLQ = "dlq"


class SeverityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    channel = Column(
        Enum(NotificationChannel, name="notification_channel", native_enum=False),
        nullable=False,
    )
    subject_tpl = Column(Text, nullable=True)
    body_tpl = Column(Text, nullable=False)
    locale = Column(String(8), nullable=False, default="en", server_default="en")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id = Column(Integer, primary_key=True, index=True)
    trigger_type = Column(String(100), nullable=False, index=True)
    # severity_min stores a free-form severity label (LOW/MEDIUM/HIGH/CRITICAL)
    # so it works for both alarms and outage state changes.
    severity_min = Column(
        Enum(SeverityLevel, name="severity_level", native_enum=False),
        nullable=True,
    )
    match_filter = Column(JSONB, nullable=True)
    channels = Column(ARRAY(String(16)), nullable=False, server_default="{}")
    recipients = Column(ARRAY(String(200)), nullable=False, server_default="{}")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(
        Enum(NotificationChannel, name="notification_channel", native_enum=False),
        nullable=False,
        index=True,
    )
    recipient = Column(String(300), nullable=False)
    template_id = Column(
        Integer,
        ForeignKey("notification_templates.id"),
        nullable=True,
    )
    status = Column(
        Enum(NotificationStatus, name="notification_status", native_enum=False),
        nullable=False,
        default=NotificationStatus.PENDING,
        index=True,
    )
    retries = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preferences"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    channels = Column(ARRAY(String(16)), nullable=False, server_default="{}")
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    tz = Column(
        String(64),
        nullable=False,
        default="Asia/Kolkata",
        server_default="Asia/Kolkata",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReliabilityMonthly(Base):
    __tablename__ = "reliability_monthly"
    __table_args__ = (
        CheckConstraint("length(year_month) = 7", name="reliability_monthly_yyyymm"),
    )

    feeder_id = Column(Integer, ForeignKey("feeders.id"), primary_key=True)
    year_month = Column(CHAR(7), primary_key=True)  # YYYY-MM
    saidi = Column(Float, nullable=True)
    saifi = Column(Float, nullable=True)
    caidi = Column(Float, nullable=True)
    maifi = Column(Float, nullable=True)
    total_customers = Column(Integer, nullable=True)
    computed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
