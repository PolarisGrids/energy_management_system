"""Pydantic schemas for DER consumer + type-catalog endpoints (W5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Consumer ──────────────────────────────────────────────────────────────────


class DERConsumerBase(BaseModel):
    name: str
    account_no: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    premise_address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    tariff_code: Optional[str] = None
    status: str = "active"


class DERConsumerCreate(DERConsumerBase):
    id: Optional[str] = None  # server-generated UUID when omitted
    metadata: Optional[dict[str, Any]] = None


class DERConsumerUpdate(BaseModel):
    name: Optional[str] = None
    account_no: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    premise_address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    tariff_code: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DERConsumerOut(DERConsumerBase):
    id: str
    onboarded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Read the SQLAlchemy attribute `consumer_metadata` (the column is named
    # "metadata" in the DB but renamed in the model to dodge SQLAlchemy's
    # `Base.metadata` registry attribute), serialise as JSON `"metadata"`.
    consumer_metadata: Optional[dict[str, Any]] = Field(
        default=None, serialization_alias="metadata"
    )

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True
    )


class DERConsumerSummary(BaseModel):
    """Light version used inline on asset list rows."""

    id: str
    name: str
    account_no: Optional[str] = None
    tariff_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── Type catalog ──────────────────────────────────────────────────────────────


class DERTypeCatalogOut(BaseModel):
    code: str
    category: str
    display_name: str
    description: Optional[str] = None
    typical_kw_min: Optional[float] = None
    typical_kw_max: Optional[float] = None
    default_unit: str = "kW"

    model_config = ConfigDict(from_attributes=True)
