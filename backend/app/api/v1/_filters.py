"""Common query-parameter filter parser — spec 018 no-mock-data closure.

Every new metrology endpoint (``/api/v1/consumption/*``, ``/api/v1/devices/*``)
accepts the same set of device-scope + date-range + tariff/interval filters.
Rather than repeat the ``Query(...)`` plumbing on every route, we parse once
into a ``CommonFilters`` dataclass and pass that downstream.

Defaults (when callers omit the field):

* ``from_dt`` : now − 7 days  (UTC)
* ``to_dt``   : now           (UTC)
* ``interval``: ``"1h"``       (only used by ``load-profile``)

Usage::

    from app.api.v1._filters import CommonFilters, get_common_filters

    @router.get("/something")
    async def something(f: CommonFilters = Depends(get_common_filters)):
        ...

The returned dataclass is a frozen value object; downstream code should call
``f.to_mdms_params()`` to build the upstream query dict rather than accessing
attributes ad-hoc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Query


ALLOWED_INTERVALS = {"15m", "30m", "1h", "1d"}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 date or datetime string into a timezone-aware UTC dt.

    Accepts ``YYYY-MM-DD`` (treated as start-of-day UTC) and full ISO-8601
    timestamps (with or without timezone). Returns ``None`` on empty / ``None``.
    Raises ``ValueError`` if the format is unrecognised so FastAPI surfaces a
    422 to the caller.
    """
    if value is None or value == "":
        return None
    # datetime.fromisoformat handles "YYYY-MM-DD" as a date; make it a datetime.
    try:
        if "T" not in value and " " not in value:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid ISO datetime: {value!r}") from exc


@dataclass(frozen=True)
class CommonFilters:
    """Normalised filter payload for consumption + device endpoints."""

    meter: Optional[str] = None
    consumer: Optional[str] = None
    dtr: Optional[str] = None
    feeder: Optional[str] = None
    tariff_class: Optional[str] = None
    from_dt: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7))
    to_dt: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    interval: str = "1h"

    # ── Convenience ─────────────────────────────────────────────────────────

    @property
    def from_iso(self) -> str:
        return self.from_dt.isoformat()

    @property
    def to_iso(self) -> str:
        return self.to_dt.isoformat()

    @property
    def from_date(self) -> str:
        return self.from_dt.date().isoformat()

    @property
    def to_date(self) -> str:
        return self.to_dt.date().isoformat()

    @property
    def scope(self) -> str:
        """Most-specific scope label for banners and cache keys.

        Precedence: ``meter`` > ``consumer`` > ``dtr`` > ``feeder`` > ``all``.
        """
        if self.meter:
            return "meter"
        if self.consumer:
            return "consumer"
        if self.dtr:
            return "dtr"
        if self.feeder:
            return "feeder"
        return "all"

    def to_mdms_params(self) -> Dict[str, Any]:
        """Build the upstream MDMS query dict, stripping ``None`` values."""
        raw = {
            "meter": self.meter,
            "consumer": self.consumer,
            "dtr": self.dtr,
            "feeder": self.feeder,
            "tariff_class": self.tariff_class,
            "from": self.from_iso,
            "to": self.to_iso,
            "interval": self.interval,
        }
        return {k: v for k, v in raw.items() if v is not None}


def get_common_filters(
    meter: Optional[str] = Query(None, description="Meter serial"),
    consumer: Optional[str] = Query(None, description="Consumer/account number"),
    dtr: Optional[str] = Query(None, description="DTR id or name"),
    feeder: Optional[str] = Query(None, description="Feeder id or name"),
    tariff_class: Optional[str] = Query(None, description="Tariff class (Residential/Commercial/…)"),
    from_: Optional[str] = Query(None, alias="from", description="ISO date or datetime (default now-7d)"),
    to: Optional[str] = Query(None, description="ISO date or datetime (default now)"),
    interval: str = Query("1h", description="15m | 30m | 1h | 1d"),
) -> CommonFilters:
    """FastAPI dependency — parses + validates the common filter block."""
    if interval not in ALLOWED_INTERVALS:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"interval must be one of {sorted(ALLOWED_INTERVALS)}")
    try:
        frm = _parse_iso(from_)
        to_dt = _parse_iso(to)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    if frm is None:
        frm = now - timedelta(days=7)
    if to_dt is None:
        to_dt = now
    return CommonFilters(
        meter=meter or None,
        consumer=consumer or None,
        dtr=dtr or None,
        feeder=feeder or None,
        tariff_class=tariff_class or None,
        from_dt=frm,
        to_dt=to_dt,
        interval=interval,
    )
