"""DER consumer + sub-type catalog (W5).

`DERConsumer` is the owner/account record that one or more `DERAssetEMS`
rows belong to. `DERTypeCatalog` is the seeded sub-type taxonomy
(rooftop_pv / dc_fast_charger / lithium_bess / …) that lets the UI
group the fleet beyond the broad PV/BESS/EV/microgrid category.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


def _json_col():
    from sqlalchemy import JSON

    return JSON().with_variant(JSONB(), "postgresql")


class DERConsumer(Base):
    __tablename__ = "der_consumer"

    id = Column(String(36), primary_key=True)
    name = Column(Text, nullable=False)
    account_no = Column(String(40), nullable=True)
    email = Column(String(200), nullable=True)
    phone = Column(String(40), nullable=True)
    premise_address = Column(Text, nullable=True)
    lat = Column(Numeric(10, 6), nullable=True)
    lon = Column(Numeric(10, 6), nullable=True)
    tariff_code = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    onboarded_at = Column(DateTime(timezone=True), server_default=func.now())
    consumer_metadata = Column("metadata", _json_col(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','terminated','pending')",
            name="ck_der_consumer_status",
        ),
        UniqueConstraint("account_no", name="uq_der_consumer_account_no"),
        Index("ix_der_consumer_name", "name"),
        Index("ix_der_consumer_status", "status"),
    )


class DERTypeCatalog(Base):
    __tablename__ = "der_type_catalog"

    code = Column(String(40), primary_key=True)
    category = Column(String(20), nullable=False)
    display_name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    typical_kw_min = Column(Numeric(12, 2), nullable=True)
    typical_kw_max = Column(Numeric(12, 2), nullable=True)
    default_unit = Column(String(10), nullable=False, default="kW")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('pv','bess','ev','microgrid','wind')",
            name="ck_der_type_catalog_category",
        ),
        Index("ix_der_type_catalog_category", "category"),
    )
