"""AppBuilder models — spec 018 W4.T6.

Author/publish-workflow models for the no-code AppBuilder. All three entities
share a `(slug, version)` unique identity with status {DRAFT, PREVIEW,
PUBLISHED, ARCHIVED}. Only one PUBLISHED row per slug is enforced in the
endpoint layer (Postgres partial unique index added in the migration).

These tables are *distinct* from alarm_rule / virtual_object_group (spec 018
W4 notifications track, owned by Agent L). AppBuilder rules (`rule_def`) are
user-authored widget logic; alarm_rule is the network-level alarm engine.
"""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


def _json_col():
    return JSON().with_variant(JSONB(), "postgresql")


def _uuid_col():
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")


# ── Lifecycle values shared across the three definition tables ──
STATUS_DRAFT = "DRAFT"
STATUS_PREVIEW = "PREVIEW"
STATUS_PUBLISHED = "PUBLISHED"
STATUS_ARCHIVED = "ARCHIVED"

VALID_STATUSES = {STATUS_DRAFT, STATUS_PREVIEW, STATUS_PUBLISHED, STATUS_ARCHIVED}
PUBLISHABLE_FROM = {STATUS_DRAFT, STATUS_PREVIEW}


class AppDef(Base):
    """Versioned no-code app / dashboard definition.

    `definition` holds the widget layout + bindings. Each save bumps the
    version and inserts a new row; history is naturally preserved.
    """

    __tablename__ = "app_def"

    id = Column(_uuid_col(), primary_key=True)
    slug = Column(String(120), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    author_user_id = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default=STATUS_DRAFT, index=True)
    definition = Column(_json_col(), nullable=False)
    required_role = Column(String(100), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_app_def_slug_version"),
    )


class RuleDef(Base):
    """Versioned user-authored rule definition (AppBuilder-scope).

    Not to be confused with `alarm_rule` — this is widget-local logic an
    app author writes in the visual rule editor (trigger/condition/action).
    """

    __tablename__ = "rule_def"

    id = Column(_uuid_col(), primary_key=True)
    slug = Column(String(120), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    name = Column(String(200), nullable=False)
    author_user_id = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default=STATUS_DRAFT, index=True)
    definition = Column(_json_col(), nullable=False)
    # Optional back-link to the app that owns this rule (for app-scope rules).
    app_slug = Column(String(120), nullable=True, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_rule_def_slug_version"),
    )


class AlgorithmDef(Base):
    """Versioned Python algorithm snippet executed via the sandbox runner."""

    __tablename__ = "algorithm_def"

    id = Column(_uuid_col(), primary_key=True)
    slug = Column(String(120), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    author_user_id = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default=STATUS_DRAFT, index=True)
    # The Python source is stored alongside a JSON "definition" envelope
    # holding input-shape hints, entrypoint, and tags.
    source = Column(Text, nullable=False)
    definition = Column(_json_col(), nullable=False, default=dict)
    published_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_algorithm_def_slug_version"),
    )


class ScheduledReport(Base):
    """Spec 018 W4.T10 — scheduled EGSM report runs (email PDF)."""

    __tablename__ = "scheduled_report"

    id = Column(_uuid_col(), primary_key=True)
    owner_user_id = Column(String(200), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    report_ref = Column(
        String(300), nullable=False
    )  # e.g. "egsm:energy-audit:feeder-loss-summary"
    params = Column(_json_col(), nullable=False, default=dict)
    schedule_cron = Column(String(100), nullable=False)
    recipients = Column(_json_col(), nullable=False, default=list)  # list[str]
    enabled = Column(Integer, nullable=False, default=1)  # 0/1 (bool via int)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
