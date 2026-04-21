"""Alert Management — seed + reset defaults endpoint.

Idempotent: creating twice is a no-op. Produces:

* ``Default — Feeder Meters``
  Virtual-object-group bound to the entire local feeder network. Target for
  power-cut and voltage-deviation alarms.

* ``Default — Critical Customers``
  Virtual-object-group scoped to any meter whose consumer_tag.site_type is
  hospital / data_centre / fire_station. Target for priority-1 power-cut
  email alerts.

Plus two seeded alarm rules wired to those groups so the demo has a
working end-to-end flow without operator clicks.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.rbac import P_ALARM_CONFIGURE, require_permission
from app.db.base import get_db
from app.models.alarm_rule import AlarmRule
from app.models.consumer_tag import ConsumerTag
from app.models.user import User
from app.models.virtual_object_group import VirtualObjectGroup
from app.services import mdms_cis_client as cis

log = logging.getLogger(__name__)
router = APIRouter()


# Default seed identifiers. Kept stable so "seed again" is idempotent.
_FEEDER_GROUP_NAME = "Default — Feeder Meters"
_CRITICAL_GROUP_NAME = "Default — Critical Customers"

# A handful of MDMS account IDs we tag as critical sites for the demo.
# Picked to spread across the 3 feeders seen in consumer_master_data.
_DEMO_CRITICAL_TAGS = [
    # meterSrno,  site_type,      consumer_name,                 notes
    ("PO10000001", "hospital",    "Soweto General Hospital",     "Level-1 trauma centre"),
    ("PO10000008", "data_centre", "Orlando Data Centre",         "Tier-III colo facility"),
    ("PO10000015", "fire_station","Orlando Fire Station",        "Southern response unit"),
    ("PO10000022", "hospital",    "Baragwanath Emergency Ward",  "Critical care unit"),
    ("PO10000031", "data_centre", "Gauteng Cloud Region",        "Regional availability zone"),
    ("PO10000044", "fire_station","Orlando East Brigade",        "Eastern response unit"),
]


class SeedOut(BaseModel):
    created_groups: List[str]
    reused_groups: List[str]
    created_rules: List[str]
    reused_rules: List[str]
    tagged_consumers: int
    critical_members: int
    feeder_members_hint: str


def _upsert_group(
    db: Session,
    owner_id: str,
    name: str,
    description: str,
    selector: dict,
) -> tuple[VirtualObjectGroup, bool]:
    existing = (
        db.query(VirtualObjectGroup)
        .filter(VirtualObjectGroup.name == name)
        .first()
    )
    if existing:
        return existing, False
    now = datetime.now(timezone.utc)
    row = VirtualObjectGroup(
        id=uuid.uuid4().hex,
        name=name,
        description=description,
        selector=selector,
        owner_user_id=owner_id,
        shared_with_roles=["admin", "supervisor", "operator"],
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row, True


def _upsert_rule(
    db: Session,
    owner_id: str,
    *,
    name: str,
    description: str,
    group_id: str,
    condition: dict,
    action: dict,
    priority: int,
) -> tuple[AlarmRule, bool]:
    existing = db.query(AlarmRule).filter(AlarmRule.name == name).first()
    if existing:
        return existing, False
    now = datetime.now(timezone.utc)
    row = AlarmRule(
        id=uuid.uuid4().hex,
        group_id=group_id,
        name=name,
        description=description,
        condition=condition,
        action=action,
        priority=priority,
        active=True,
        dedup_window_seconds=300,
        owner_user_id=owner_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row, True


def _seed_critical_tags(db: Session, owner_id: str) -> int:
    """Create demo consumer_tag rows. Returns number of new rows added."""
    new_count = 0
    now = datetime.now(timezone.utc)
    # Enrich from MDMS CIS when reachable so consumer_name + account_id are
    # real, but fall back to the hard-coded labels when offline.
    cis_map: dict = {}
    if _DEMO_CRITICAL_TAGS:
        serials = [s for (s, *_rest) in _DEMO_CRITICAL_TAGS]
        for row in cis.list_consumers(meter_serials=serials, limit=len(serials)):
            cis_map[row.meter_serial] = row

    for serial, site_type, fallback_name, notes in _DEMO_CRITICAL_TAGS:
        existing = (
            db.query(ConsumerTag).filter(ConsumerTag.meter_serial == serial).first()
        )
        c = cis_map.get(serial)
        account_id = c.account_id if c else None
        consumer_name = (c.consumer_name if c else None) or fallback_name
        if existing:
            # Preserve operator edits; just refresh CIS-sourced account_id + name.
            if account_id and not existing.account_id:
                existing.account_id = account_id
            if consumer_name and not existing.consumer_name:
                existing.consumer_name = consumer_name
            existing.updated_at = now
            continue
        db.add(
            ConsumerTag(
                meter_serial=serial,
                site_type=site_type,
                account_id=account_id,
                consumer_name=consumer_name,
                notes=notes,
                tagged_by=owner_id,
                created_at=now,
                updated_at=now,
            )
        )
        new_count += 1
    return new_count


@router.post("/defaults", response_model=SeedOut)
def seed_alert_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(P_ALARM_CONFIGURE)),
) -> SeedOut:
    """Create (idempotently) the two demo groups + rules + critical tags."""
    owner_id = str(current_user.id)

    tagged = _seed_critical_tags(db, owner_id)

    # Feeder meters group — empty hierarchy = "every meter". The description
    # captures the intent. Operators can later narrow the selector.
    feeder_group, feeder_new = _upsert_group(
        db,
        owner_id,
        name=_FEEDER_GROUP_NAME,
        description="All feeder-connected meters. Used for power-cut + voltage-deviation rules.",
        selector={"hierarchy": {}, "filters": {}},
    )

    # Critical customers — any meter whose consumer_tag.site_type marks it so.
    critical_group, critical_new = _upsert_group(
        db,
        owner_id,
        name=_CRITICAL_GROUP_NAME,
        description="Hospitals, data centres, fire stations. Power-cut alarms go to customer email.",
        selector={
            "hierarchy": {
                "site_types": ["hospital", "data_centre", "fire_station"],
            },
            "filters": {},
        },
    )

    created_groups = [g.name for g, new in [
        (feeder_group, feeder_new), (critical_group, critical_new)
    ] if new]
    reused_groups = [g.name for g, new in [
        (feeder_group, feeder_new), (critical_group, critical_new)
    ] if not new]

    # Power-cut + voltage-deviation rule on feeder meters. Priority 3, in-app.
    feeder_rule, feeder_rule_new = _upsert_rule(
        db,
        owner_id,
        name="Feeder Meters — Power-cut + Voltage Deviation",
        description="Any power-cut, under/over-voltage on a feeder-side meter.",
        group_id=feeder_group.id,
        condition={
            "source": "alarm_event",
            "field": "alarm_type",
            "op": "in",
            "value": ["outage", "undervoltage", "overvoltage", "power_failure"],
            "duration_seconds": 0,
        },
        action={
            "channels": [
                {"type": "in_app", "recipients": ["operations-desk"]},
                {"type": "email", "recipients": ["noc@eskom.co.za"]},
            ],
            "priority": 3,
        },
        priority=3,
    )

    # Critical customers — P1 power-cut to customer email + SMS + in-app.
    critical_rule, critical_rule_new = _upsert_rule(
        db,
        owner_id,
        name="Critical Customers — Power-cut Email/SMS",
        description="P1 power-cut on a hospital / data-centre / fire-station meter.",
        group_id=critical_group.id,
        condition={
            "source": "alarm_event",
            "field": "alarm_type",
            "op": "in",
            "value": ["outage", "power_failure"],
            "duration_seconds": 0,
        },
        action={
            "channels": [
                {"type": "email", "recipients": ["critical-sites@eskom.co.za"]},
                {"type": "sms", "recipients": ["+27100000000"]},
                {"type": "in_app", "recipients": ["critical-desk"]},
            ],
            "priority": 1,
        },
        priority=1,
    )

    created_rules = [r.name for r, new in [
        (feeder_rule, feeder_rule_new), (critical_rule, critical_rule_new)
    ] if new]
    reused_rules = [r.name for r, new in [
        (feeder_rule, feeder_rule_new), (critical_rule, critical_rule_new)
    ] if not new]

    db.commit()

    critical_members = (
        db.query(ConsumerTag)
        .filter(ConsumerTag.site_type.in_(["hospital", "data_centre", "fire_station"]))
        .count()
    )
    # Rough feeder-meter count hint (we don't resolve the empty-hierarchy
    # group here because it would block the request on large fleets).
    feeder_hint = "all meters in EMS (resolved per-firing by rule engine)"

    return SeedOut(
        created_groups=created_groups,
        reused_groups=reused_groups,
        created_rules=created_rules,
        reused_rules=reused_rules,
        tagged_consumers=tagged,
        critical_members=critical_members,
        feeder_members_hint=feeder_hint,
    )


@router.get("/defaults/status")
def defaults_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P_ALARM_CONFIGURE)),
):
    """Quick check whether the defaults have been seeded."""
    f = db.query(VirtualObjectGroup).filter(VirtualObjectGroup.name == _FEEDER_GROUP_NAME).first()
    c = db.query(VirtualObjectGroup).filter(VirtualObjectGroup.name == _CRITICAL_GROUP_NAME).first()
    tagged = db.query(ConsumerTag).count()
    return {
        "feeder_group_id": f.id if f else None,
        "critical_group_id": c.id if c else None,
        "tagged_consumers": tagged,
        "seeded": bool(f and c and tagged > 0),
    }
