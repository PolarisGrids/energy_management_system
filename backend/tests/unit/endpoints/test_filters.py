"""Unit tests for the common filter parser — spec 018 no-mock-data closure."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1._filters import CommonFilters, _parse_iso, get_common_filters


def test_parse_iso_date_only():
    dt = _parse_iso("2026-04-01")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 4 and dt.day == 1
    assert dt.tzinfo is not None


def test_parse_iso_with_z_suffix():
    dt = _parse_iso("2026-04-18T10:00:00Z")
    assert dt is not None and dt.tzinfo is not None


def test_parse_iso_none_returns_none():
    assert _parse_iso(None) is None
    assert _parse_iso("") is None


def test_parse_iso_invalid_raises():
    with pytest.raises(ValueError):
        _parse_iso("not-a-date")


def test_default_filters():
    # FastAPI `Query(...)` default objects aren't resolved when calling the
    # dependency directly; pass literal values to exercise the defaulting path.
    f = get_common_filters(
        meter=None, consumer=None, dtr=None, feeder=None,
        tariff_class=None, from_=None, to=None, interval="1h",
    )
    assert isinstance(f, CommonFilters)
    assert f.interval == "1h"
    delta = datetime.now(timezone.utc) - f.from_dt
    # default is now-7d
    assert timedelta(days=6, hours=23) <= delta <= timedelta(days=7, hours=1)


def test_scope_precedence():
    f = CommonFilters(meter="M1", feeder="F1")
    assert f.scope == "meter"
    f2 = CommonFilters(feeder="F1")
    assert f2.scope == "feeder"
    f3 = CommonFilters()
    assert f3.scope == "all"


def test_to_mdms_params_strips_none():
    f = CommonFilters(meter="M0001", feeder=None, tariff_class="Residential")
    p = f.to_mdms_params()
    assert p["meter"] == "M0001"
    assert p["tariff_class"] == "Residential"
    assert "feeder" not in p
    assert "from" in p and "to" in p and "interval" in p


def test_get_common_filters_custom_range():
    f = get_common_filters(
        meter="M001",
        consumer=None,
        dtr=None,
        feeder=None,
        tariff_class=None,
        from_="2026-04-01",
        to="2026-04-10",
        interval="30m",
    )
    assert f.meter == "M001"
    assert f.from_dt.date().isoformat() == "2026-04-01"
    assert f.to_dt.date().isoformat() == "2026-04-10"
    assert f.interval == "30m"


def test_get_common_filters_rejects_bad_interval():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        get_common_filters(interval="5s")
    assert exc.value.status_code == 422


def test_get_common_filters_rejects_bad_date():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        get_common_filters(from_="nonsense", interval="1h")
    assert exc.value.status_code == 422
