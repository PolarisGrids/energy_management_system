"""Energy-Saving Analysis tables (post-W5 extension).

Introduces a small org-hierarchy + appliance-usage model used by the
``/api/v1/energy-savings/*`` endpoints. The hierarchy is 4 levels deep
(company > department > branch > customer) and customer rows link back
to a real smart meter via ``meter_serial`` so the tab can project
downstream meter load when we want to.

Tables:
  * org_unit          — hierarchical tree
  * appliance_catalog — reference rows (AC, water pump, EV charger, geyser…)
  * appliance_usage   — per-customer usage rows (kW rating, running hours,
                        peak-hours portion, count, shiftable hours)
  * tou_tariff        — named tariff with peak/standard/off-peak rates.
                        A single ``is_default=true`` row holds the
                        Megaflex baseline; additional rows are editable
                        scenarios saved from the UI.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.base import Base


# 4-level hierarchy used by the Savings Analysis tab.
ORG_LEVELS = ("company", "department", "branch", "customer")

# Appliance broad groups shown in the UI filter.
APPLIANCE_CATEGORIES = ("ac", "water_pump", "ev_charger", "geyser", "lighting", "other")


class OrgUnit(Base):
    __tablename__ = "org_unit"

    id = Column(String(36), primary_key=True)
    parent_id = Column(String(36), ForeignKey("org_unit.id"), nullable=True)
    level = Column(String(20), nullable=False)
    name = Column(Text, nullable=False)
    code = Column(String(40), nullable=True)
    # Customer-level rows optionally pin to a real meter for later linkage.
    meter_serial = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "level IN ('company','department','branch','customer')",
            name="ck_org_unit_level",
        ),
        Index("ix_org_unit_parent_id", "parent_id"),
        Index("ix_org_unit_level", "level"),
        Index("ix_org_unit_meter_serial", "meter_serial"),
    )


class ApplianceCatalog(Base):
    __tablename__ = "appliance_catalog"

    code = Column(String(40), primary_key=True)
    category = Column(String(30), nullable=False)
    display_name = Column(Text, nullable=False)
    typical_kw = Column(Numeric(8, 3), nullable=False)
    typical_running_hours = Column(Numeric(5, 2), nullable=False)
    # Defines how many of `typical_running_hours` are safely shiftable
    # from peak to off-peak (e.g. a geyser is very shiftable, an AC less so).
    shiftable_hours = Column(Numeric(5, 2), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('ac','water_pump','ev_charger','geyser','lighting','other')",
            name="ck_appliance_catalog_category",
        ),
        Index("ix_appliance_catalog_category", "category"),
    )


class ApplianceUsage(Base):
    __tablename__ = "appliance_usage"

    id = Column(String(36), primary_key=True)
    org_unit_id = Column(
        String(36), ForeignKey("org_unit.id", ondelete="CASCADE"), nullable=False
    )
    appliance_code = Column(
        String(40), ForeignKey("appliance_catalog.code"), nullable=False
    )
    count = Column(Integer, nullable=False, default=1)
    # Per-day running hours broken into the three TOU bands.
    peak_hours = Column(Numeric(5, 2), nullable=False, default=0)
    standard_hours = Column(Numeric(5, 2), nullable=False, default=0)
    offpeak_hours = Column(Numeric(5, 2), nullable=False, default=0)
    # How many of `peak_hours` can realistically be shifted to off-peak.
    shiftable_peak_hours = Column(Numeric(5, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_appliance_usage_org_unit_id", "org_unit_id"),
        Index("ix_appliance_usage_appliance_code", "appliance_code"),
    )


class TouTariff(Base):
    __tablename__ = "tou_tariff"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    currency = Column(String(8), nullable=False, default="ZAR")
    peak_rate = Column(Numeric(10, 4), nullable=False)
    standard_rate = Column(Numeric(10, 4), nullable=False)
    offpeak_rate = Column(Numeric(10, 4), nullable=False)
    # Peak / off-peak windows as comma-separated "HH-HH" ranges (weekday).
    # Defaults reflect Eskom Megaflex (peak 06-09 & 17-20; off-peak 22-06).
    peak_windows = Column(String(60), nullable=False, default="06-09,17-20")
    offpeak_windows = Column(String(60), nullable=False, default="22-06")
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_tou_tariff_name"),
        Index("ix_tou_tariff_is_default", "is_default"),
    )
