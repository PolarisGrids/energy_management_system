"""Energy Saving Analysis endpoints.

Serves the ``Savings Analysis`` tab on ``/energy-monitoring``:

* ``GET  /api/v1/energy-savings/hierarchy``  — full org tree
* ``GET  /api/v1/energy-savings/tariff``     — default TOU tariff
* ``PUT  /api/v1/energy-savings/tariff``     — update default TOU tariff
* ``GET  /api/v1/energy-savings/appliances`` — per-org-unit appliance rows
* ``GET  /api/v1/energy-savings/summary``    — TOU kWh + cost + 24h profile
* ``POST /api/v1/energy-savings/shift-scenario`` — before/after if shifting
                                                   peak hours to off-peak

All calculations are deterministic from the seeded appliance usage rows —
no upstream MDMS call, so no source banner needed.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import P_ENERGY_READ, require_permission
from app.db.base import get_db
from app.models.energy_savings import (
    ApplianceCatalog,
    ApplianceUsage,
    OrgUnit,
    TouTariff,
)
from app.models.user import User
from app.schemas.energy_savings import (
    ApplianceCatalogOut,
    ApplianceShiftOverride,
    ApplianceShiftRow,
    ApplianceUsageOut,
    BandTotals,
    OrgUnitNode,
    ShiftScenarioRequest,
    ShiftScenarioResponse,
    TouSummary,
    TouTariffOut,
    TouTariffUpdate,
)

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_default_tariff(db: Session) -> TouTariff:
    """Return the single default tariff row; 500 if the seed is missing."""
    t = (
        db.query(TouTariff)
        .filter(TouTariff.is_default.is_(True))
        .order_by(TouTariff.id)
        .first()
    )
    if t is None:
        # Fall back to the first row — migration always seeds one; this
        # branch only hits if someone manually nuked the table.
        t = db.query(TouTariff).order_by(TouTariff.id).first()
    if t is None:
        raise HTTPException(
            status_code=500,
            detail="No TOU tariff configured — rerun Alembic to seed the default.",
        )
    return t


def _parse_windows(spec: str) -> List[int]:
    """Expand a spec like ``'06-09,17-20'`` into the list of hours ``[6,7,8,17,18,19]``.

    Each range is treated as [start, end) so ``22-06`` wraps past midnight
    and produces ``[22,23,0,1,2,3,4,5]``.
    """
    hours: List[int] = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk or "-" not in chunk:
            continue
        try:
            start_s, end_s = chunk.split("-", 1)
            start, end = int(start_s), int(end_s)
        except ValueError:
            continue
        if start == end:
            continue
        h = start
        while h != end:
            hours.append(h % 24)
            h = (h + 1) % 24
    return hours


def _band_for_hour(hour: int, peak_hours: List[int], offpeak_hours: List[int]) -> str:
    if hour in peak_hours:
        return "peak"
    if hour in offpeak_hours:
        return "offpeak"
    return "standard"


def _collect_descendants(db: Session, root_id: str) -> List[OrgUnit]:
    """Breadth-first walk from ``root_id`` returning all descendants (inclusive)."""
    out: List[OrgUnit] = []
    stack = [root_id]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        unit = db.query(OrgUnit).filter(OrgUnit.id == cur).first()
        if not unit:
            continue
        out.append(unit)
        children = db.query(OrgUnit.id).filter(OrgUnit.parent_id == cur).all()
        stack.extend([c.id for c in children])
    return out


def _customer_ids_under(db: Session, root_id: str) -> List[str]:
    return [u.id for u in _collect_descendants(db, root_id) if u.level == "customer"]


def _build_tree(units: List[OrgUnit]) -> Optional[OrgUnitNode]:
    """Build a nested OrgUnitNode tree from a flat list. Assumes exactly one root."""
    by_id: Dict[str, OrgUnitNode] = {}
    for u in units:
        by_id[u.id] = OrgUnitNode.model_validate(u)
    root: Optional[OrgUnitNode] = None
    for u in units:
        node = by_id[u.id]
        if u.parent_id and u.parent_id in by_id:
            by_id[u.parent_id].children.append(node)
        else:
            root = node
    return root


# ── Core compute ─────────────────────────────────────────────────────────────


def _compute_usage_rows(
    db: Session, org_unit_id: str
) -> List[tuple[ApplianceUsage, ApplianceCatalog]]:
    """Return every appliance_usage row belonging to this subtree, joined to catalog.

    For a company/department/branch this aggregates every customer underneath.
    """
    customer_ids = _customer_ids_under(db, org_unit_id)
    if not customer_ids:
        return []
    rows = (
        db.query(ApplianceUsage, ApplianceCatalog)
        .join(ApplianceCatalog, ApplianceCatalog.code == ApplianceUsage.appliance_code)
        .filter(ApplianceUsage.org_unit_id.in_(customer_ids))
        .all()
    )
    return rows


def _band_totals_and_profile(
    usage_rows: List[tuple[ApplianceUsage, ApplianceCatalog]],
    tariff: TouTariff,
    peak_override: Dict[str, float] | None = None,
):
    """Compute total kWh per band + 24h hourly kW profile for the subtree.

    ``peak_override`` lets us apply a per-usage-row shift (hours moved from
    peak to off-peak) without mutating the DB row — used by the scenario
    endpoint.
    """
    peak_hours_set = _parse_windows(tariff.peak_windows)
    offpeak_hours_set = _parse_windows(tariff.offpeak_windows)

    peak_kwh = 0.0
    standard_kwh = 0.0
    offpeak_kwh = 0.0
    hourly_peak = [0.0] * 24
    hourly_standard = [0.0] * 24
    hourly_offpeak = [0.0] * 24

    for usage, cat in usage_rows:
        count = int(usage.count or 1)
        kw = float(cat.typical_kw or 0) * count
        raw_peak_h = float(usage.peak_hours or 0)
        raw_standard_h = float(usage.standard_hours or 0)
        raw_offpeak_h = float(usage.offpeak_hours or 0)

        shift = 0.0
        if peak_override:
            shift = float(peak_override.get(usage.id, 0.0))
        shift = max(0.0, min(shift, raw_peak_h))

        peak_h = raw_peak_h - shift
        offpeak_h = raw_offpeak_h + shift
        standard_h = raw_standard_h

        peak_kwh += kw * peak_h
        standard_kwh += kw * standard_h
        offpeak_kwh += kw * offpeak_h

        # Distribute each band's hours evenly across that band's hour-set so
        # the 24h profile shows a plausible load curve. Any hour not in peak
        # or off-peak windows falls under "standard" by construction.
        standard_hours_set = [h for h in range(24) if h not in peak_hours_set and h not in offpeak_hours_set]

        def _sprinkle(target: List[float], h_set: List[int], total_hours: float) -> None:
            if not h_set or total_hours <= 0:
                return
            per = (kw * total_hours) / len(h_set)
            for h in h_set:
                target[h] += per

        _sprinkle(hourly_peak, peak_hours_set, peak_h)
        _sprinkle(hourly_standard, standard_hours_set, standard_h)
        _sprinkle(hourly_offpeak, offpeak_hours_set, offpeak_h)

    peak_cost = peak_kwh * float(tariff.peak_rate)
    standard_cost = standard_kwh * float(tariff.standard_rate)
    offpeak_cost = offpeak_kwh * float(tariff.offpeak_rate)

    return {
        "peak_kwh": peak_kwh,
        "standard_kwh": standard_kwh,
        "offpeak_kwh": offpeak_kwh,
        "peak_cost": peak_cost,
        "standard_cost": standard_cost,
        "offpeak_cost": offpeak_cost,
        "hourly_peak": [round(v, 3) for v in hourly_peak],
        "hourly_standard": [round(v, 3) for v in hourly_standard],
        "hourly_offpeak": [round(v, 3) for v in hourly_offpeak],
    }


def _summary_from_bands(
    org_unit: OrgUnit,
    bands: dict,
    tariff: TouTariff,
    usage_rows: List[tuple[ApplianceUsage, ApplianceCatalog]],
    customer_count: int,
) -> TouSummary:
    total_kwh = bands["peak_kwh"] + bands["standard_kwh"] + bands["offpeak_kwh"]
    total_cost = bands["peak_cost"] + bands["standard_cost"] + bands["offpeak_cost"]
    appliance_count = sum(int(u.count or 1) for u, _ in usage_rows)
    return TouSummary(
        org_unit_id=org_unit.id,
        org_unit_name=org_unit.name,
        level=org_unit.level,
        customer_count=customer_count,
        appliance_count=appliance_count,
        total_kwh=round(total_kwh, 2),
        peak=BandTotals(kwh=round(bands["peak_kwh"], 2), cost=round(bands["peak_cost"], 2)),
        standard=BandTotals(
            kwh=round(bands["standard_kwh"], 2), cost=round(bands["standard_cost"], 2)
        ),
        offpeak=BandTotals(
            kwh=round(bands["offpeak_kwh"], 2), cost=round(bands["offpeak_cost"], 2)
        ),
        total_cost=round(total_cost, 2),
        currency=tariff.currency,
        hourly_peak_kw=bands["hourly_peak"],
        hourly_standard_kw=bands["hourly_standard"],
        hourly_offpeak_kw=bands["hourly_offpeak"],
        tariff=TouTariffOut.model_validate(tariff),
    )


def _apply_tariff_override(
    base: TouTariff, override: Optional[TouTariffUpdate]
) -> TouTariff:
    """Return a copy of the tariff with one-off overrides applied (not persisted)."""
    if not override:
        return base
    # Build a lightweight, non-persisted TouTariff-like object by mutating a
    # fresh in-memory instance. We avoid ``db.expunge(base)`` because we
    # don't want to touch the actual ORM row.
    shadow = TouTariff(
        id=base.id,
        name=base.name,
        currency=base.currency,
        peak_rate=override.peak_rate if override.peak_rate is not None else base.peak_rate,
        standard_rate=(
            override.standard_rate
            if override.standard_rate is not None
            else base.standard_rate
        ),
        offpeak_rate=(
            override.offpeak_rate
            if override.offpeak_rate is not None
            else base.offpeak_rate
        ),
        peak_windows=override.peak_windows or base.peak_windows,
        offpeak_windows=override.offpeak_windows or base.offpeak_windows,
        is_default=base.is_default,
        updated_at=base.updated_at,
    )
    return shadow


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/hierarchy",
    response_model=OrgUnitNode,
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def get_hierarchy(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    units = db.query(OrgUnit).order_by(OrgUnit.level, OrgUnit.name).all()
    tree = _build_tree(units)
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail="No org_unit rows — run the seed script to populate the hierarchy.",
        )
    return tree


@router.get(
    "/tariff",
    response_model=TouTariffOut,
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def get_tariff(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _get_default_tariff(db)


@router.put(
    "/tariff",
    response_model=TouTariffOut,
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def update_tariff(
    payload: TouTariffUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    t = _get_default_tariff(db)
    if payload.peak_rate is not None:
        t.peak_rate = payload.peak_rate
    if payload.standard_rate is not None:
        t.standard_rate = payload.standard_rate
    if payload.offpeak_rate is not None:
        t.offpeak_rate = payload.offpeak_rate
    if payload.peak_windows is not None:
        t.peak_windows = payload.peak_windows
    if payload.offpeak_windows is not None:
        t.offpeak_windows = payload.offpeak_windows
    db.commit()
    db.refresh(t)
    return t


@router.get(
    "/appliances",
    response_model=List[ApplianceUsageOut],
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def list_appliances(
    org_unit_id: str = Query(..., description="Any level — summed across descendants"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = _compute_usage_rows(db, org_unit_id)
    out: List[ApplianceUsageOut] = []
    for usage, cat in rows:
        total_h = float(
            (usage.peak_hours or 0)
            + (usage.standard_hours or 0)
            + (usage.offpeak_hours or 0)
        )
        count = int(usage.count or 1)
        daily_kwh = float(cat.typical_kw or 0) * count * total_h
        out.append(
            ApplianceUsageOut(
                id=usage.id,
                org_unit_id=usage.org_unit_id,
                appliance_code=usage.appliance_code,
                display_name=cat.display_name,
                category=cat.category,
                typical_kw=float(cat.typical_kw or 0),
                count=count,
                peak_hours=float(usage.peak_hours or 0),
                standard_hours=float(usage.standard_hours or 0),
                offpeak_hours=float(usage.offpeak_hours or 0),
                shiftable_peak_hours=float(usage.shiftable_peak_hours or 0),
                total_hours=round(total_h, 2),
                daily_kwh=round(daily_kwh, 2),
            )
        )
    # Stable sort: biggest daily_kwh first so the UI table leads with impact.
    out.sort(key=lambda r: r.daily_kwh, reverse=True)
    return out


@router.get(
    "/catalog",
    response_model=List[ApplianceCatalogOut],
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def list_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(ApplianceCatalog)
        .order_by(ApplianceCatalog.category, ApplianceCatalog.code)
        .all()
    )


@router.get(
    "/summary",
    response_model=TouSummary,
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def get_summary(
    org_unit_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    org_unit = db.query(OrgUnit).filter(OrgUnit.id == org_unit_id).first()
    if not org_unit:
        raise HTTPException(status_code=404, detail=f"org_unit {org_unit_id} not found")
    tariff = _get_default_tariff(db)
    usage_rows = _compute_usage_rows(db, org_unit.id)
    bands = _band_totals_and_profile(usage_rows, tariff)
    customer_count = len(_customer_ids_under(db, org_unit.id))
    return _summary_from_bands(org_unit, bands, tariff, usage_rows, customer_count)


@router.post(
    "/shift-scenario",
    response_model=ShiftScenarioResponse,
    dependencies=[Depends(require_permission(P_ENERGY_READ))],
)
def shift_scenario(
    payload: ShiftScenarioRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    org_unit = (
        db.query(OrgUnit).filter(OrgUnit.id == payload.org_unit_id).first()
    )
    if not org_unit:
        raise HTTPException(
            status_code=404, detail=f"org_unit {payload.org_unit_id} not found"
        )
    tariff = _apply_tariff_override(_get_default_tariff(db), payload.tariff)
    usage_rows = _compute_usage_rows(db, org_unit.id)
    customer_count = len(_customer_ids_under(db, org_unit.id))

    # Build a shift map — default to each row's safe shift_peak_hours.
    shift_map: Dict[str, float] = {}
    shift_rows: List[ApplianceShiftRow] = []
    overrides_by_id: Dict[str, float] = {}
    if payload.overrides:
        overrides_by_id = {o.appliance_usage_id: o.shift_hours for o in payload.overrides}

    for usage, cat in usage_rows:
        default_shift = float(usage.shiftable_peak_hours or 0)
        requested = overrides_by_id.get(usage.id, default_shift)
        requested = max(0.0, min(requested, float(usage.peak_hours or 0)))
        if requested <= 0:
            continue
        shift_map[usage.id] = requested
        kwh_shifted = float(cat.typical_kw or 0) * int(usage.count or 1) * requested
        saving = kwh_shifted * (float(tariff.peak_rate) - float(tariff.offpeak_rate))
        shift_rows.append(
            ApplianceShiftRow(
                appliance_usage_id=usage.id,
                display_name=cat.display_name,
                category=cat.category,
                shift_hours=round(requested, 2),
                kwh_shifted=round(kwh_shifted, 2),
                saving=round(saving, 2),
            )
        )

    before_bands = _band_totals_and_profile(usage_rows, tariff)
    after_bands = _band_totals_and_profile(usage_rows, tariff, peak_override=shift_map)

    before = _summary_from_bands(org_unit, before_bands, tariff, usage_rows, customer_count)
    after = _summary_from_bands(org_unit, after_bands, tariff, usage_rows, customer_count)

    saving_cost = before.total_cost - after.total_cost
    saving_kwh = sum(r.kwh_shifted for r in shift_rows)
    saving_pct = (saving_cost / before.total_cost * 100.0) if before.total_cost > 0 else 0.0

    return ShiftScenarioResponse(
        org_unit_id=org_unit.id,
        before=before,
        after=after,
        saving_kwh=round(saving_kwh, 2),
        saving_cost=round(saving_cost, 2),
        saving_pct=round(saving_pct, 2),
        shifted=shift_rows,
    )
