"""
Seed script: generates a realistic South Africa-based LV network with meters,
DER assets, alarms, historical readings, and demo simulation scenarios.
Run once after DB migration.
"""
import sys
import os
import random
import math
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal, engine
from app.db.base import Base
import app.models  # ensure all models are imported/registered

from app.models.user import User, UserRole
from app.models.meter import Meter, Transformer, Feeder, MeterType, MeterStatus, RelayState
from app.models.der import DERAsset, DERType, DERStatus
from app.models.alarm import Alarm, AlarmType, AlarmSeverity, AlarmStatus
from app.models.reading import MeterReading
from app.models.network import NetworkEvent, EventType
from app.models.simulation import SimulationScenario, SimulationStep, ScenarioType, ScenarioStatus
from app.models.sensor import TransformerSensor, SensorStatus
from app.models.energy import EnergyDailySummary
from app.models.audit import AuditEvent
from app.models.hes import HESDCU, HESCommandLog, HESFOTAJob
from app.models.mdms import (
    VEEDailySummary, VEEException, ConsumerAccount,
    TariffSchedule, NTLSuspect, PowerQualityZone,
)
from app.core.security import get_password_hash


def seed_alert_defaults(db):
    """Alert Management (2026-04-21) — idempotently create the two default
    virtual-object-groups (feeder meters, critical customers), tag a handful
    of MDMS consumers as hospital/data_centre/fire_station, and wire two
    starter alarm rules (P3 feeder power-cut → email+in-app; P1 critical →
    email+SMS+in-app).

    Safe to re-run: each upsert short-circuits if the named group/rule exists.
    """
    from app.api.v1.endpoints.alert_defaults import (
        _seed_critical_tags,
        _upsert_group,
        _upsert_rule,
        _FEEDER_GROUP_NAME,
        _CRITICAL_GROUP_NAME,
    )

    owner_id = "seed-script"
    tagged = _seed_critical_tags(db, owner_id)
    feeder_group, _ = _upsert_group(
        db, owner_id, _FEEDER_GROUP_NAME,
        "All feeder-connected meters. Used for power-cut + voltage-deviation rules.",
        {"hierarchy": {}, "filters": {}},
    )
    critical_group, _ = _upsert_group(
        db, owner_id, _CRITICAL_GROUP_NAME,
        "Hospitals, data centres, fire stations. Power-cut alarms go to customer email.",
        {"hierarchy": {"site_types": ["hospital", "data_centre", "fire_station"]}, "filters": {}},
    )
    _upsert_rule(
        db, owner_id,
        name="Feeder Meters — Power-cut + Voltage Deviation",
        description="Any power-cut, under/over-voltage on a feeder-side meter.",
        group_id=feeder_group.id,
        condition={
            "source": "alarm_event", "field": "alarm_type", "op": "in",
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
    _upsert_rule(
        db, owner_id,
        name="Critical Customers — Power-cut Email/SMS",
        description="P1 power-cut on a hospital / data-centre / fire-station meter.",
        group_id=critical_group.id,
        condition={
            "source": "alarm_event", "field": "alarm_type", "op": "in",
            "value": ["outage", "power_failure"], "duration_seconds": 0,
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
    db.commit()
    print(f"  Tagged {tagged} new consumers (critical sites).")


# Alembic owns the schema (see Dockerfile CMD: `alembic upgrade head`).
# We intentionally do NOT call `Base.metadata.create_all()` here — it races
# with alembic on partitioned tables (der_telemetry, transformer_sensor_reading)
# and leaves `alembic_version` unstamped, which later breaks `alembic upgrade`
# with DuplicateTable errors (fix captured in 2026-04-19 deploy log).

# ---------------------------------------------------------------------------
# SA geography — representative LV network areas
# ---------------------------------------------------------------------------
SA_AREAS = [
    {"name": "Soweto North", "substation": "Orlando SS",  "center": (-26.2485, 27.8543)},
    {"name": "Sandton CBD",  "substation": "Sandton SS",  "center": (-26.1076, 28.0567)},
    {"name": "Mitchell Plain","substation": "Mitchells SS","center": (-34.0523, 18.6234)},
    {"name": "Durban Central","substation": "Durban North SS","center": (-29.8587, 31.0218)},
    {"name": "Pretoria East", "substation": "Pretoria SS", "center": (-25.7479, 28.2293)},
]

STREET_PREFIXES_SA = [
    "Jan Smuts", "Nelson Mandela", "Vilakazi", "OR Tambo", "Chris Hani",
    "Bram Fischer", "Walter Sisulu", "Steve Biko", "Oliver Tambo", "Mandela",
    "Hendrik Verwoerd", "Paul Kruger", "DF Malan", "Voortrekker", "Church",
    "Claim", "Market", "Commissioner", "Eloff", "Loveday",
]

STREET_TYPES = ["Street", "Avenue", "Drive", "Road", "Crescent", "Lane", "Place"]


def rand_offset(center_lat: float, center_lon: float, radius_km: float = 2.0):
    """Generate a random point within radius_km of center."""
    angle = random.uniform(0, 2 * math.pi)
    distance = random.uniform(0, radius_km)
    dlat = distance / 111.0
    dlon = distance / (111.0 * math.cos(math.radians(center_lat)))
    return (
        center_lat + dlat * math.sin(angle),
        center_lon + dlon * math.cos(angle),
    )


def sa_address(lat: float, lon: float, i: int) -> str:
    prefix = random.choice(STREET_PREFIXES_SA)
    stype = random.choice(STREET_TYPES)
    num = random.randint(1, 999)
    return f"{num} {prefix} {stype}"


def sa_customer_name() -> str:
    first_names = [
        "Sipho", "Thabo", "Nomsa", "Zanele", "Bongani", "Lindiwe", "Kagiso",
        "Nkosi", "Ayanda", "Thandeka", "Mandla", "Siyabonga", "Nonhlanhla",
        "Dumisani", "Phindile", "Blessing", "Themba", "Nozipho", "Musa", "Sandile",
    ]
    last_names = [
        "Dlamini", "Nkosi", "Zulu", "Mokoena", "Khumalo", "Mthembu", "Ndlovu",
        "Mahlangu", "Mabaso", "Cele", "Shabalala", "Zwane", "Buthelezi", "Mkhize",
        "Molefe", "Sithole", "Mavundla", "Ngubane", "Hadebe", "Gumede",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def seed_users(db):
    users = [
        User(username="admin", email="admin@smoc.co.za", full_name="System Administrator",
             hashed_password=get_password_hash("Admin@2026"), role=UserRole.ADMIN, is_active=True),
        User(username="supervisor", email="supervisor@smoc.co.za", full_name="Jane Mokoena",
             hashed_password=get_password_hash("Super@2026"), role=UserRole.SUPERVISOR, is_active=True),
        User(username="operator", email="operator@smoc.co.za", full_name="Sipho Dlamini",
             hashed_password=get_password_hash("Oper@2026"), role=UserRole.OPERATOR, is_active=True),
        # Spec 018 W4.T12 — 5-role RBAC matrix. Analyst is the read-analytics
        # role (/energy, /reports, /mdms, /ntl, /audit). Viewer is
        # read-only-everywhere. Both are required for the Eskom demo
        # walkthrough so the presenter can show role-gated UI.
        User(username="analyst", email="analyst@smoc.co.za", full_name="Amara Khumalo",
             hashed_password=get_password_hash("Analyst@2026"), role=UserRole.ANALYST, is_active=True),
        User(username="viewer", email="viewer@smoc.co.za", full_name="Pieter van der Merwe",
             hashed_password=get_password_hash("Viewer@2026"), role=UserRole.VIEWER, is_active=True),
    ]
    for u in users:
        if not db.query(User).filter(User.username == u.username).first():
            db.add(u)
    db.commit()
    print(f"  Users seeded.")


def seed_network(db):
    feeders = []
    transformers = []
    meters = []

    for area_idx, area in enumerate(SA_AREAS):
        clat, clon = area["center"]

        for f_idx in range(5):
            feeder = Feeder(
                name=f"F{area_idx+1}{f_idx+1:02d} {area['name']}",
                substation=area["substation"],
                voltage_kv=11.0,
                capacity_kva=random.uniform(2000, 5000),
                current_load_kw=random.uniform(800, 2000),
                geojson=None,
            )
            db.add(feeder)
            db.flush()
            feeders.append(feeder)

            for t_idx in range(4):
                tlat, tlon = rand_offset(clat, clon, 1.5)
                transformer = Transformer(
                    name=f"TX-{area_idx+1}{f_idx+1}{t_idx+1:02d}",
                    feeder_id=feeder.id,
                    latitude=tlat,
                    longitude=tlon,
                    capacity_kva=random.uniform(100, 500),
                    current_load_kw=random.uniform(40, 200),
                    loading_percent=random.uniform(30, 85),
                    voltage_pu=random.uniform(0.97, 1.03),
                    phase="3ph",
                )
                db.add(transformer)
                db.flush()
                transformers.append(transformer)

                # 5–8 meters per transformer
                n_meters = random.randint(5, 8)
                for m_idx in range(n_meters):
                    mlat, mlon = rand_offset(tlat, tlon, 0.3)
                    serial = f"SA{area_idx+1:02d}{f_idx+1:02d}{t_idx+1:02d}{m_idx+1:03d}"
                    mtype = random.choices(
                        [MeterType.RESIDENTIAL, MeterType.COMMERCIAL, MeterType.PREPAID],
                        weights=[70, 15, 15]
                    )[0]
                    status = random.choices(
                        [MeterStatus.ONLINE, MeterStatus.OFFLINE, MeterStatus.TAMPER],
                        weights=[88, 8, 4]
                    )[0]
                    meter = Meter(
                        serial=serial,
                        transformer_id=transformer.id,
                        meter_type=mtype,
                        status=status,
                        relay_state=RelayState.CONNECTED,
                        latitude=mlat,
                        longitude=mlon,
                        address=sa_address(mlat, mlon, m_idx),
                        customer_name=sa_customer_name(),
                        account_number=f"ACC{random.randint(100000, 999999)}",
                        tariff_class="Residential" if mtype == MeterType.RESIDENTIAL else "Commercial",
                        prepaid_balance=random.uniform(10, 500) if mtype == MeterType.PREPAID else None,
                        firmware_version="v2.1.4",
                        comm_tech=random.choice(["PLC", "RF Mesh", "GPRS"]),
                        last_seen=datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 60)),
                    )
                    db.add(meter)
                    meters.append(meter)

    db.commit()
    print(f"  Network seeded: {len(feeders)} feeders, {len(transformers)} transformers, {len(meters)} meters")
    return feeders, transformers, meters


def seed_der_assets(db, transformers):
    assets = []
    # Pick 3 specific transformers for DER: PV suburb, EV charger commercial, Microgrid
    t_pv = transformers[5]
    t_ev = transformers[20]
    t_mg = transformers[35]

    # PV Residential Cluster
    pv = DERAsset(
        name="Soweto PV Cluster #1",
        asset_type=DERType.PV,
        status=DERStatus.ONLINE,
        transformer_id=t_pv.id,
        latitude=t_pv.latitude + 0.001,
        longitude=t_pv.longitude + 0.001,
        rated_capacity_kw=250.0,
        current_output_kw=187.5,
        panel_area_m2=1400.0,
        inverter_efficiency=0.97,
        generation_today_kwh=random.uniform(800, 1200),
        generation_achievement_rate=random.uniform(85, 98),
    )
    db.add(pv)

    # BESS
    bess = DERAsset(
        name="Sandton BESS Unit #1",
        asset_type=DERType.BESS,
        status=DERStatus.DISCHARGING,
        transformer_id=t_pv.id,
        latitude=t_pv.latitude - 0.001,
        longitude=t_pv.longitude - 0.001,
        rated_capacity_kw=200.0,
        current_output_kw=120.0,
        capacity_kwh=800.0,
        state_of_charge=62.0,
        charge_cycles=random.randint(100, 400),
        revenue_today=random.uniform(1500, 4500),
    )
    db.add(bess)

    # EV Fast Charger
    ev = DERAsset(
        name="Durban EV Fast Charge Hub",
        asset_type=DERType.EV_CHARGER,
        status=DERStatus.ONLINE,
        transformer_id=t_ev.id,
        latitude=t_ev.latitude + 0.002,
        longitude=t_ev.longitude + 0.002,
        rated_capacity_kw=360.0,
        current_output_kw=216.0,
        num_ports=6,
        active_sessions=3,
        energy_dispensed_today_kwh=random.uniform(400, 900),
        fee_collected_today=random.uniform(3000, 8000),
    )
    db.add(ev)

    # Peaking Microgrid
    mg = DERAsset(
        name="Pretoria Peaking Microgrid",
        asset_type=DERType.MICROGRID,
        status=DERStatus.IDLE,
        transformer_id=t_mg.id,
        latitude=t_mg.latitude + 0.003,
        longitude=t_mg.longitude - 0.002,
        rated_capacity_kw=500.0,
        current_output_kw=0.0,
        islanded=False,
        reverse_power_flow=False,
    )
    db.add(mg)

    db.commit()
    db.refresh(pv); db.refresh(bess); db.refresh(ev); db.refresh(mg)
    assets = [pv, bess, ev, mg]
    print(f"  DER assets seeded: {len(assets)} assets")
    return pv, bess, ev, mg


def seed_alarms(db, meters, transformers):
    alarm_templates = [
        (AlarmType.TAMPER, AlarmSeverity.CRITICAL, "Tamper event detected"),
        (AlarmType.COMM_LOSS, AlarmSeverity.MEDIUM, "Communication loss > 24h"),
        (AlarmType.OVERVOLTAGE, AlarmSeverity.HIGH, "Voltage exceeds 1.10 pu"),
        (AlarmType.UNDERVOLTAGE, AlarmSeverity.HIGH, "Voltage below 0.90 pu"),
        (AlarmType.NTS_DETECTED, AlarmSeverity.HIGH, "Non-technical loss pattern detected"),
        (AlarmType.BATTERY_LOW, AlarmSeverity.LOW, "Meter battery below 10%"),
        (AlarmType.COVER_OPEN, AlarmSeverity.CRITICAL, "Meter cover opened"),
        (AlarmType.OVERCURRENT, AlarmSeverity.HIGH, "Overcurrent on LV feeder"),
    ]

    # Active alarms on some meters
    active_count = 0
    for meter in random.sample(meters, min(25, len(meters))):
        atype, asev, adesc = random.choice(alarm_templates)
        alarm = Alarm(
            alarm_type=atype,
            severity=asev,
            status=AlarmStatus.ACTIVE,
            meter_serial=meter.serial,
            transformer_id=meter.transformer_id,
            title=atype.value.replace("_", " ").title(),
            description=f"{adesc} — Meter {meter.serial}",
            latitude=meter.latitude,
            longitude=meter.longitude,
            triggered_at=datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 48)),
        )
        db.add(alarm)
        active_count += 1

    # Historical resolved alarms
    for transformer in random.sample(transformers, min(10, len(transformers))):
        alarm = Alarm(
            alarm_type=AlarmType.TRANSFORMER_OVERLOAD,
            severity=AlarmSeverity.HIGH,
            status=AlarmStatus.RESOLVED,
            transformer_id=transformer.id,
            title="Transformer Overload",
            description=f"Loading exceeded 100% on {transformer.name}",
            latitude=transformer.latitude,
            longitude=transformer.longitude,
            triggered_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 7)),
            resolved_at=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 24)),
        )
        db.add(alarm)

    db.commit()
    print(f"  Alarms seeded: {active_count} active")


def seed_readings(db, meters):
    """Seed 7 days of 30-min interval readings for every meter."""
    now = datetime.now(timezone.utc)
    readings = []
    total = 0

    for meter in meters:
        base_demand = random.uniform(0.5, 5.0)
        for hour_offset in range(24 * 7):  # 7 days, 24 readings/day (hourly)
            ts = now - timedelta(hours=hour_offset)
            # Realistic diurnal load curve
            hour_of_day = ts.hour
            load_factor = 0.3 + 0.7 * math.exp(-0.5 * ((hour_of_day - 18) / 4) ** 2)
            noise = random.uniform(0.9, 1.1)
            demand = base_demand * load_factor * noise
            reading = MeterReading(
                meter_serial=meter.serial,
                timestamp=ts,
                energy_import_kwh=round(demand * 1.0, 4),
                energy_export_kwh=round(random.uniform(0, 0.1), 4),
                demand_kw=round(demand, 3),
                voltage_v=round(random.uniform(220, 240), 1),
                current_a=round(demand * 1000 / 230, 2),
                power_factor=round(random.uniform(0.85, 0.99), 3),
                frequency_hz=50.0,
                thd_percent=round(random.uniform(1.5, 5.0), 1),
                is_estimated=0,
            )
            readings.append(reading)
            total += 1

    db.bulk_save_objects(readings)
    db.commit()
    print(f"  Readings seeded: {total} records")


def seed_energy_daily_summary(db, meters):
    """Aggregate meter_readings into daily summary rows."""
    now = datetime.now(timezone.utc)
    for day_offset in range(7):
        day = (now - timedelta(days=day_offset)).date()
        res_count = sum(1 for m in meters if m.tariff_class == "Residential")
        com_count = sum(1 for m in meters if m.tariff_class == "Commercial")
        pre_count = sum(1 for m in meters if m.tariff_class not in ("Residential", "Commercial"))
        res_import = res_count * random.uniform(2.5, 5.0)
        com_import = com_count * random.uniform(8.0, 20.0)
        pre_import = pre_count * random.uniform(1.5, 4.0)
        total_import = res_import + com_import + pre_import
        total_export = total_import * random.uniform(0.03, 0.08)
        summary = EnergyDailySummary(
            date=day,
            total_import_kwh=round(total_import, 2),
            total_export_kwh=round(total_export, 2),
            net_kwh=round(total_import - total_export, 2),
            peak_demand_kw=round(total_import * random.uniform(0.06, 0.1), 2),
            avg_power_factor=round(random.uniform(0.91, 0.97), 3),
            residential_import_kwh=round(res_import, 2),
            commercial_import_kwh=round(com_import, 2),
            prepaid_import_kwh=round(pre_import, 2),
        )
        db.add(summary)
    db.commit()
    print(f"  Energy daily summary seeded: 7 days")


def seed_audit_events(db, meters):
    """Seed realistic operator audit events over 7 days."""
    now = datetime.now(timezone.utc)
    users = [("admin", "Admin"), ("supervisor", "Supervisor"), ("operator", "Operator")]
    ips = {"admin": "10.1.5.4", "supervisor": "10.1.5.8", "operator": "10.1.5.11"}
    event_templates = [
        ("Login", "User login", "Auth service", "Success"),
        ("Login", "Session expired, re-auth", "Auth service", "Success"),
        ("Command", "Remote connect issued", None, "Success"),
        ("Command", "Remote disconnect issued", None, "Success"),
        ("Command", "On-demand read requested", None, "Success"),
        ("Command", "Load limit set 20A", None, "Success"),
        ("Command", "Load limit removed", None, "Success"),
        ("Command", "Time sync issued", None, "Success"),
        ("Alarm", "Alarm acknowledged", None, "Success"),
        ("Alarm", "Tamper alarm acknowledged", None, "Success"),
        ("Alarm", "Overvoltage alarm acknowledged", None, "Success"),
        ("Alarm", "Power quality alarm ack", None, "Success"),
        ("Configuration", "Tariff block updated", "Tariff / Block B2", "Success"),
        ("Configuration", "Alarm threshold updated", "VoltHigh threshold 1.08pu", "Success"),
        ("Configuration", "Dashboard layout saved", "Layout: Ops-Main-v3", "Success"),
        ("Configuration", "Prepaid credit loaded", None, "Success"),
        ("System", "Report generated", "Rpt: Daily Energy", "Success"),
        ("System", "FOTA job scheduled", None, "Queued"),
        ("System", "FOTA job started", None, "Running"),
        ("System", "Simulation scenario started", "Sim: Overvoltage-ODP4", "Running"),
        ("System", "Simulation scenario stopped", "Sim: Overvoltage-ODP4", "Success"),
    ]
    sample_serials = [m.serial for m in random.sample(meters, min(50, len(meters)))]
    events = []
    for day_offset in range(7):
        day_base = now - timedelta(days=day_offset)
        n_events = random.randint(25, 35)
        for _ in range(n_events):
            user_name, user_role = random.choice(users)
            etype, action, resource, result = random.choice(event_templates)
            hour = random.randint(7, 17)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = day_base.replace(hour=hour, minute=minute, second=second)
            if resource is None:
                if etype == "Command":
                    serial = random.choice(sample_serials)
                    resource = f"Meter {serial}"
                elif etype == "Alarm":
                    resource = f"ALM-{ts.strftime('%Y%m%d')}-{random.randint(1, 50):03d}"
                elif etype == "Configuration" and "Prepaid" in action:
                    serial = random.choice(sample_serials)
                    resource = f"Meter {serial} +{random.randint(20, 200)}U"
                elif etype == "System" and "FOTA" in action:
                    resource = f"Job FOTA-2026-{random.randint(40, 60):04d}"
                else:
                    resource = "System"
            events.append(AuditEvent(
                timestamp=ts, user_name=user_name, user_role=user_role,
                event_type=etype, action=action, resource=resource,
                ip_address=ips.get(user_name, "10.1.5.20"), result=result,
            ))
    db.bulk_save_objects(events)
    db.commit()
    print(f"  Audit events seeded: {len(events)} events")


def seed_hes_data(db, feeders, meters):
    """Seed HES DCUs, command history, and FOTA jobs."""
    now = datetime.now(timezone.utc)
    for i, feeder in enumerate(feeders):
        meter_count = sum(1 for m in meters if m.transformer_id in
                         [t.id for t in (db.query(Transformer).filter(Transformer.feeder_id == feeder.id).all())])
        online_pct = random.uniform(0.88, 0.98)
        status = "online"
        if i == len(feeders) - 1:
            status = "offline"
            online_pct = 0.0
        elif i == len(feeders) - 2:
            status = "degraded"
            online_pct = random.uniform(0.65, 0.80)
        dcu = HESDCU(
            id=f"DCU-{i+1:03d}", location=feeder.name,
            total_meters=meter_count, online_meters=int(meter_count * online_pct),
            last_comm=now - timedelta(minutes=random.randint(1, 180) if status != "offline" else random.randint(180, 600)),
            status=status, firmware_version=random.choice(["v3.2.1", "v3.2.0", "v3.1.8"]),
            comm_tech=random.choice(["GPRS", "RF Mesh", "PLC"]),
        )
        db.add(dcu)
    cmd_types = ["Remote Connect"] * 30 + ["Remote Disconnect"] * 20 + ["On-Demand Read"] * 25 + ["Time Sync"] * 10 + ["Load Limit Set"] * 10 + ["Prepaid Credit"] * 5
    sample_serials = [m.serial for m in random.sample(meters, min(80, len(meters)))]
    operators = ["admin", "supervisor", "operator"]
    commands = []
    for _ in range(150):
        day_off = random.randint(0, 6)
        ts = now - timedelta(days=day_off, hours=random.randint(0, 23), minutes=random.randint(0, 59))
        cmd_ok = random.random() > 0.05
        commands.append(HESCommandLog(
            timestamp=ts, meter_serial=random.choice(sample_serials),
            command_type=random.choice(cmd_types),
            status="ok" if cmd_ok else "failed",
            operator=random.choice(operators),
            response_time_ms=random.randint(200, 3000) if cmd_ok else None,
        ))
    db.bulk_save_objects(commands)
    fota_jobs = [
        HESFOTAJob(id="FOTA-0041", target_description="All / v2.0.x meters", total_meters=120,
                   updated_count=112, failed_count=3, status="running",
                   firmware_from="v2.0.1", firmware_to="v2.1.4", created_at=now - timedelta(hours=6)),
        HESFOTAJob(id="FOTA-0040", target_description="Feeder F12 meters", total_meters=48,
                   updated_count=48, failed_count=0, status="complete",
                   firmware_from="v2.0.9", firmware_to="v2.1.4",
                   created_at=now - timedelta(days=2), completed_at=now - timedelta(days=1)),
        HESFOTAJob(id="FOTA-0039", target_description="Type: STS prepaid", total_meters=30,
                   updated_count=22, failed_count=8, status="failed",
                   firmware_from="v1.8.2", firmware_to="v2.0.1",
                   created_at=now - timedelta(days=5), completed_at=now - timedelta(days=4)),
        HESFOTAJob(id="FOTA-0042", target_description="Sandton CBD sector", total_meters=65,
                   updated_count=0, failed_count=0, status="scheduled",
                   firmware_from="v2.1.4", firmware_to="v2.2.0", created_at=now - timedelta(hours=1)),
    ]
    for j in fota_jobs:
        db.add(j)
    db.commit()
    print(f"  HES data seeded: {len(feeders)} DCUs, 150 commands, 4 FOTA jobs")


def seed_mdms_data(db, meters, transformers):
    """Seed MDMS VEE, consumer accounts, tariffs, NTL, power quality."""
    now = datetime.now(timezone.utc)
    for day_offset in range(7):
        day = (now - timedelta(days=day_offset)).date()
        total_readings = len(meters) * random.randint(22, 26)
        validated = int(total_readings * random.uniform(0.88, 0.92))
        failed = int(total_readings * random.uniform(0.01, 0.03))
        estimated = total_readings - validated - failed
        db.add(VEEDailySummary(date=day, validated_count=validated,
                               estimated_count=estimated, failed_count=failed))
    exc_types = ["Spike detected", "Missing read", "Zero consumption", "Negative delta"]
    exc_weights = [25, 30, 30, 15]
    sample_serials = [m.serial for m in random.sample(meters, min(60, len(meters)))]
    exceptions = []
    for day_offset in range(7):
        day = (now - timedelta(days=day_offset)).date()
        for _ in range(random.randint(8, 12)):
            etype = random.choices(exc_types, weights=exc_weights)[0]
            orig = ("—" if etype == "Missing read" else
                    f"{random.randint(3000, 9999)} kWh" if etype == "Spike detected" else
                    "0 kWh" if etype == "Zero consumption" else
                    f"-{random.randint(1, 20)} kWh")
            resolved = day_offset >= 2
            corr = (f"{random.randint(200, 800)} kWh" if etype == "Spike detected" and resolved else
                    f"Est {random.randint(100, 500)} kWh" if etype == "Missing read" and resolved else
                    "Pending")
            exceptions.append(VEEException(
                meter_serial=random.choice(sample_serials), exception_type=etype,
                date=day, original_value=orig, corrected_value=corr,
                status="Resolved" if resolved else "Pending",
            ))
    db.bulk_save_objects(exceptions)
    accounts = []
    for i, meter in enumerate(meters):
        prefix = "ESK-A" if meter.meter_type in (MeterType.RESIDENTIAL, MeterType.PREPAID) else "ESK-B"
        tariff_map = {"Residential": random.choice(["Residential Lifeline", "Residential Standard"]), "Commercial": "Commercial TOU"}
        accounts.append(ConsumerAccount(
            account_number=f"{prefix}{i+1:06d}",
            customer_name=meter.customer_name or f"Customer {i+1}",
            address=meter.address or f"{random.randint(1, 999)} Main Rd",
            tariff_name=tariff_map.get(meter.tariff_class, "Residential Standard"),
            meter_serial=meter.serial, transformer_id=str(meter.transformer_id),
            phase="Single" if meter.meter_type in (MeterType.RESIDENTIAL, MeterType.PREPAID) else "Three",
            prepaid_balance=round(random.uniform(20, 500), 2) if meter.meter_type == MeterType.PREPAID else None,
        ))
    db.bulk_save_objects(accounts)
    tariffs = [
        TariffSchedule(name="Residential Lifeline", tariff_type="IBT", offpeak_rate=0.85, standard_rate=1.24, peak_rate=1.87, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Residential Standard", tariff_type="IBT", offpeak_rate=1.12, standard_rate=1.65, peak_rate=2.34, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Residential Mid", tariff_type="IBT", offpeak_rate=1.28, standard_rate=1.88, peak_rate=2.67, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Residential High", tariff_type="IBT", offpeak_rate=1.45, standard_rate=2.12, peak_rate=3.01, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Commercial TOU", tariff_type="Time of Use", offpeak_rate=0.95, standard_rate=1.78, peak_rate=3.12, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Commercial Retail", tariff_type="Time of Use", offpeak_rate=0.98, standard_rate=1.82, peak_rate=3.25, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Industrial Shift", tariff_type="Time of Use", offpeak_rate=0.72, standard_rate=1.35, peak_rate=2.85, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="Industrial 24H", tariff_type="Time of Use", offpeak_rate=0.65, standard_rate=1.22, peak_rate=2.65, effective_from=datetime(2025, 7, 1).date()),
        TariffSchedule(name="EV / Solar Prosumer", tariff_type="Time of Use", offpeak_rate=0.88, standard_rate=1.55, peak_rate=2.95, effective_from=datetime(2025, 7, 1).date()),
    ]
    for t in tariffs:
        db.add(t)
    ntl_patterns = ["Flat baseline, sudden zero", "Reverse flow detected", "Meter bypass suspected",
                    "Consistent underread", "Spike then flat", "Tamper event + zero read",
                    "Long zero periods", "Irregular deltas"]
    ntl_count = max(1, int(len(meters) * 0.05))
    ntl_meters = random.sample(meters, ntl_count)
    for meter in ntl_meters:
        score = random.randint(40, 95)
        flag = "High Risk" if score >= 75 else ("Medium" if score >= 50 else "Low")
        db.add(NTLSuspect(meter_serial=meter.serial, customer_name=meter.customer_name,
                          pattern_description=random.choice(ntl_patterns), risk_score=score, flag=flag))
    pq_transformers = random.sample(transformers, min(80, len(transformers)))
    for transformer in pq_transformers:
        feeder = db.query(Feeder).filter(Feeder.id == transformer.feeder_id).first()
        area = feeder.name.split(" ", 1)[-1] if feeder else "Unknown"
        v_dev = round(random.uniform(1.2, 7.0), 1)
        thd = round(random.uniform(1.8, 8.0), 1)
        flicker = round(random.uniform(0.2, 2.2), 1)
        compliant = v_dev < 5.0 and thd < 8.0 and flicker < 1.0
        db.add(PowerQualityZone(zone_name=f"{transformer.name} {area}",
                                voltage_deviation_pct=v_dev, thd_pct=thd,
                                flicker_pst=flicker, compliant=compliant))
    db.commit()
    print(f"  MDMS data seeded: VEE 7 days, {len(exceptions)} exceptions, {len(accounts)} accounts, "
          f"9 tariffs, {ntl_count} NTL suspects, {len(pq_transformers)} PQ zones")


def seed_simulation_scenarios(db, feeders, transformers, pv, ev, mg):
    """Seed the 4 DER simulation scenarios with step-by-step network states."""

    # --- Scenario 1: Solar Overvoltage ---
    # Rich topology + inverter fleet + droop algorithm state feed
    # SolarOvervoltageViz on the Simulations page. Each step's network_state
    # carries per-node voltages, algorithm step indicator, and per-inverter
    # setpoints so the UI can animate curtailment propagation.
    solar_nodes = [
        {"id": f"N{i}", "name": f"N{i}", "distance_m": i * 80}
        for i in range(1, 8)
    ]
    solar_inverters = [
        {"id": f"INV-0{i}", "node": f"N{min(7, max(1, (i+1)//2 + 1))}",
         "rated_kw": 5.0 if i <= 6 else 3.0, "customer": f"Consumer {i:02d}"}
        for i in range(1, 10)
    ]
    s1 = SimulationScenario(
        name="REQ-21: Solar Export Overvoltage",
        scenario_type=ScenarioType.SOLAR_OVERVOLTAGE,
        status=ScenarioStatus.IDLE,
        description="Sunny afternoon with high solar export causing overvoltage on LV feeder. Demonstrates smart inverter volt-watt droop curtailment.",
        feeder_id=feeders[0].id,
        transformer_id=transformers[5].id,
        der_asset_id=pv.id,
        parameters={
            "feeder_name": "F3 — Residential LV",
            "target_voltage_max_pu": 1.10,
            "curtailment_threshold_pu": 1.08,
            "v_nominal": 230.0,
            "v_ref": 230.0,
            "v_onset": 246.0,
            "v_limit": 253.0,
            "k_droop_kw_per_v": 2.5,
            "topology": {"nodes": solar_nodes, "inverters": solar_inverters},
            "standards": ["AS/NZS 4777.2", "IEEE 1547-2018", "EN 50549"],
        },
        total_steps=6,
    )
    db.add(s1)
    db.flush()

    def _voltage_profile(v_end: float) -> dict:
        """Linearly ramp node voltage from substation (1.00 pu) to feeder tip."""
        v0 = 230.0
        v_final = v_end
        return {
            node["id"]: round(v0 + (v_final - v0) * (i / (len(solar_nodes) - 1)), 2)
            for i, node in enumerate(solar_nodes)
        }

    def _inverter_setpoints(avail_factor: float, curtail_kw_total: float) -> list:
        """Proportionally share curtailment across the 6 nearest inverters."""
        curtailing = solar_inverters[3:]  # INV-04..INV-09 closest to feeder tip
        sum_avail = sum(inv["rated_kw"] * avail_factor for inv in curtailing)
        out = []
        for inv in solar_inverters:
            avail = inv["rated_kw"] * avail_factor
            if inv in curtailing and curtail_kw_total > 0 and sum_avail > 0:
                share = (avail / sum_avail) * curtail_kw_total
                setpoint = max(0.0, avail - share)
            else:
                setpoint = avail
            out.append({
                "id": inv["id"], "node": inv["node"],
                "rated_kw": inv["rated_kw"],
                "available_kw": round(avail, 2),
                "setpoint_kw": round(setpoint, 2),
                "curtailed_pct": round(100 * (1 - (setpoint / max(avail, 0.01))), 1),
                "is_curtailing": setpoint < avail - 0.01,
            })
        return out

    solar_steps = [
        (1, "Morning — PV fleet at 40% available, all voltages nominal",
         {
             "voltage_pu": 1.01, "pv_output_kw": 100.0, "load_kw": 180.0,
             "algorithm_step": "monitor",
             "node_voltages": _voltage_profile(236.0),
             "v_tip": 236.0,
             "inverters": _inverter_setpoints(0.40, 0.0),
             "total_curtailment_kw": 0.0,
         }, False),
        (2, "Irradiance rising — fleet at 75%, tip voltage 244 V",
         {
             "voltage_pu": 1.04, "pv_output_kw": 187.5, "load_kw": 160.0,
             "algorithm_step": "monitor",
             "node_voltages": _voltage_profile(244.0),
             "v_tip": 244.0,
             "inverters": _inverter_setpoints(0.75, 0.0),
             "total_curtailment_kw": 0.0,
         }, False),
        (3, "Peak solar — fleet at 100%, tip 251 V (approaching limit)",
         {
             "voltage_pu": 1.07, "pv_output_kw": 250.0, "load_kw": 140.0,
             "algorithm_step": "detect",
             "node_voltages": _voltage_profile(251.0),
             "v_tip": 251.0,
             "inverters": _inverter_setpoints(1.0, 0.0),
             "total_curtailment_kw": 0.0,
         }, False),
        (4, "Overvoltage — N7 at 253.4 V — droop algorithm triggers",
         {
             "voltage_pu": 1.12, "pv_output_kw": 250.0, "load_kw": 120.0,
             "algorithm_step": "compute",
             "node_voltages": _voltage_profile(253.4),
             "v_tip": 253.4,
             "delta_v": 0.4,
             "k_kw_per_v": 2.5,
             "delta_p_kw": 1.0,
             "inverters": _inverter_setpoints(1.0, 0.0),
             "total_curtailment_kw": 0.0,
         }, True),
        (5, "Curtailment dispatched — INV-04..09 reduced, voltage falling",
         {
             "voltage_pu": 1.08, "pv_output_kw": 150.0, "load_kw": 120.0,
             "algorithm_step": "curtail",
             "node_voltages": _voltage_profile(248.5),
             "v_tip": 248.5,
             "delta_v": 0.4,
             "k_kw_per_v": 2.5,
             "delta_p_kw": 1.0,
             "inverters": _inverter_setpoints(1.0, 1.0),
             "total_curtailment_kw": 1.0,
         }, False),
        (6, "Voltage stable — ramping setpoints back up (10%/min)",
         {
             "voltage_pu": 1.03, "pv_output_kw": 150.0, "load_kw": 130.0,
             "algorithm_step": "restore",
             "node_voltages": _voltage_profile(240.0),
             "v_tip": 240.0,
             "inverters": _inverter_setpoints(0.85, 0.0),
             "total_curtailment_kw": 0.0,
         }, False),
    ]
    for step_num, desc, state, trigger_alarm in solar_steps:
        db.add(SimulationStep(
            scenario_id=s1.id,
            step_number=step_num,
            description=desc,
            network_state=state,
            alarms_triggered=[{"type": "overvoltage"}] if trigger_alarm else [],
            commands_available=[{"cmd": "curtail_inverter", "label": "Curtail PV Inverter", "target_id": pv.id}],
            duration_seconds=8.0,
        ))

    # --- Scenario 2: EV Fast Charging ---
    # 4-bay fast-charging hub on a 150 kVA zone TX. State per step gives
    # winding temp, per-bay SoC/kW, OCPP setpoint, 4-hour forecast.
    ev_bays = [
        {"id": "BAY-1", "rated_kw": 150.0, "connector": "CCS2"},
        {"id": "BAY-2", "rated_kw": 150.0, "connector": "CCS2"},
        {"id": "BAY-3", "rated_kw": 150.0, "connector": "CHAdeMO"},
        {"id": "BAY-4", "rated_kw": 150.0, "connector": "CCS2"},
    ]
    # 4-hour forecast (15-min buckets). Evening peak 16:30–17:30.
    ev_forecast = [
        {"t_offset_min": i * 15,
         "predicted_kw": round(140 + 40 * math.sin(math.pi * i / 16) + 20 * (1 if 9 <= i <= 13 else 0), 1),
         "curtailed_kw": 140.0}
        for i in range(16)
    ]

    s2 = SimulationScenario(
        name="REQ-22: EV Fast Charging Station Impact",
        scenario_type=ScenarioType.EV_FAST_CHARGING,
        status=ScenarioStatus.IDLE,
        description="DC fast-charging hub energised — transformer overload risk. Demonstrates OCPP SetChargingProfile curtailment and 4-hour demand forecasting.",
        feeder_id=feeders[4].id,
        transformer_id=transformers[20].id,
        der_asset_id=ev.id,
        parameters={
            "station_name": "TX-07 Fast-Charge Hub",
            "transformer_id_label": "TX-07",
            "transformer_capacity_kva": 150.0,
            "overload_threshold_pct": 100.0,
            "winding_alarm_c": 90.0,
            "winding_trip_c": 105.0,
            "bays": ev_bays,
            "forecast_4h": ev_forecast,
            "station_envelope_kw": 140.0,
            "protocol": "OCPP 2.0.1",
        },
        total_steps=6,
    )
    db.add(s2)
    db.flush()

    def _bay_state(plugged: list[bool], kw: list[float], soc: list[float],
                   limit: list[float]) -> list:
        out = []
        for i, bay in enumerate(ev_bays):
            out.append({
                "id": bay["id"],
                "connector": bay["connector"],
                "plugged": plugged[i],
                "charging_kw": kw[i],
                "soc_pct": soc[i],
                "setpoint_kw": limit[i],
                "rated_kw": bay["rated_kw"],
            })
        return out

    ev_steps = [
        (1, "Station energised — standby, no vehicles connected",
         {
             "ev_demand_kw": 0.0, "transformer_load_kw": 45.0,
             "loading_percent": 30.0, "active_sessions": 0,
             "winding_temp_c": 58.0, "oil_temp_c": 52.0,
             "bays": _bay_state([False, False, False, False], [0, 0, 0, 0], [0, 0, 0, 0], [150, 150, 150, 150]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 600.0,
         }, False),
        (2, "1 EV connected — 125 kW draw, TX loading 113%",
         {
             "ev_demand_kw": 125.0, "transformer_load_kw": 170.0,
             "loading_percent": 113.0, "active_sessions": 1,
             "winding_temp_c": 76.0, "oil_temp_c": 68.0,
             "bays": _bay_state([True, False, False, False], [125, 0, 0, 0], [32, 0, 0, 0], [150, 150, 150, 150]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 600.0,
         }, False),
        (3, "3 EVs charging — 177 kW demand, TX at 118% OVERLOAD",
         {
             "ev_demand_kw": 177.0, "transformer_load_kw": 177.0,
             "loading_percent": 118.0, "active_sessions": 3,
             "winding_temp_c": 92.0, "oil_temp_c": 79.0,
             "bays": _bay_state([True, True, True, False], [75, 62, 40, 0], [48, 65, 82, 0], [150, 150, 150, 150]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 600.0,
         }, True),
        (4, "Curtailment via OCPP — SetChargingProfile 140 kW envelope",
         {
             "ev_demand_kw": 140.0, "transformer_load_kw": 140.0,
             "loading_percent": 93.0, "active_sessions": 3,
             "winding_temp_c": 86.0, "oil_temp_c": 74.0,
             "bays": _bay_state([True, True, True, False], [60, 50, 30, 0], [52, 70, 88, 0], [65, 55, 35, 150]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 140.0,
             "curtailment_active": True,
         }, False),
        (5, "4th EV connected — station at envelope limit 140 kW",
         {
             "ev_demand_kw": 140.0, "transformer_load_kw": 140.0,
             "loading_percent": 93.0, "active_sessions": 4,
             "winding_temp_c": 82.0, "oil_temp_c": 71.0,
             "bays": _bay_state([True, True, True, True], [40, 40, 25, 35], [60, 78, 94, 22], [45, 45, 30, 45]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 140.0,
             "curtailment_active": True,
         }, False),
        (6, "Steady state — TX stable, winding temp falling, forecast armed",
         {
             "ev_demand_kw": 138.0, "transformer_load_kw": 138.0,
             "loading_percent": 92.0, "active_sessions": 4,
             "winding_temp_c": 74.0, "oil_temp_c": 68.0,
             "bays": _bay_state([True, True, True, True], [42, 38, 20, 38], [68, 85, 96, 30], [45, 45, 30, 45]),
             "forecast": ev_forecast,
             "station_setpoint_kw": 140.0,
             "curtailment_active": True,
         }, False),
    ]
    for step_num, desc, state, trigger_alarm in ev_steps:
        db.add(SimulationStep(
            scenario_id=s2.id,
            step_number=step_num,
            description=desc,
            network_state=state,
            alarms_triggered=[{"type": "transformer_overload"}] if trigger_alarm else [],
            commands_available=[{"cmd": "curtail_ev_charger", "label": "Curtail EV Station (140 kW)", "target_id": ev.id}],
            duration_seconds=8.0,
        ))

    # --- Scenario 3: Peaking Microgrid ---
    # 4-DER VPP with PV, gas peaker, BESS, EV fleet. network_state includes
    # dispatch vector, reverse-flow vs relay margin, island mode, voltage
    # at injection point.
    s3 = SimulationScenario(
        name="REQ-23: Peaking Microgrid Online",
        scenario_type=ScenarioType.PEAKING_MICROGRID,
        status=ScenarioStatus.IDLE,
        description="Riverside Industrial peaking microgrid with 4 DERs (PV + gas peaker + BESS + EV fleet V2G). Reverse power flow event, VPP aggregation and island transition.",
        feeder_id=feeders[3].id,
        transformer_id=transformers[35].id,
        der_asset_id=mg.id,
        parameters={
            "microgrid_name": "Riverside Industrial Precinct",
            "feeder_name": "F7",
            "reverse_power_relay_kw": -150.0,
            "v_limit_pu": 1.10,
            "v_limit_v": 253.0,
            "assets": [
                {"id": "PV-F7", "type": "pv", "rated_kw": 200.0, "label": "Solar PV Array"},
                {"id": "GAS-F7", "type": "gas_peaker", "rated_kw": 150.0, "label": "Gas Peaker"},
                {"id": "BESS-F7", "type": "bess", "rated_kw": 100.0, "capacity_kwh": 300.0, "label": "BESS"},
                {"id": "EVF-F7", "type": "ev_fleet", "rated_kw": 120.0, "vehicles": 8, "label": "EV Fleet (V2G)"},
            ],
            "rated_capacity_kw": 500.0,
        },
        total_steps=7,
    )
    db.add(s3)
    db.flush()

    def _vpp(pv, gas, bess, evf, local_load, mode="individual",
             islanded=False, v_pu=1.03):
        generation = pv + gas + max(0, bess) + max(0, evf)
        absorb = -min(0, bess) + -min(0, evf)  # positive when charging/absorbing
        net_export = generation - local_load - absorb
        reverse_power_kw = -net_export if net_export > 0 else 0.0
        return {
            "pv_kw": pv, "gas_kw": gas, "bess_kw": bess, "ev_fleet_kw": evf,
            "total_gen_kw": round(generation, 1),
            "local_load_kw": local_load,
            "net_export_kw": round(net_export, 1),
            "reverse_power_kw": round(reverse_power_kw, 1),
            "relay_margin_kw": round(150.0 - reverse_power_kw, 1),
            "output_kw": round(generation, 1),
            "islanded": islanded,
            "aggregation_mode": mode,
            "v_pu_injection": v_pu,
            "v_v_injection": round(230.0 * v_pu, 1),
            "bess_soc_pct": 68.0,
            "ev_fleet_soc_pct": 68.0,
            "feeder_load_kw": round(max(0, local_load - generation), 1),
        }

    mg_steps = [
        (1, "Microgrid startup — PV warming up, local load 145 kW",
         {**_vpp(55, 0, 0, 45, 145, mode="individual", v_pu=1.01),
          "phase": "startup"}, False),
        (2, "Solar ramping — PV at 140 kW, approaching net zero export",
         {**_vpp(140, 0, 0, 45, 145, mode="individual", v_pu=1.03),
          "phase": "ramp"}, False),
        (3, "Solar peak — 200 kW PV, reverse flow 100 kW (relay margin 50 kW)",
         {**_vpp(200, 0, 0, 45, 145, mode="individual", v_pu=1.06),
          "phase": "reverse_flow"}, False),
        (4, "Reverse flow 142 kW — 8 kW from −150 kW relay trip",
         {**_vpp(287, 0, 0, 0, 145, mode="individual", v_pu=1.078),
          "phase": "reverse_flow_critical"}, True),
        (5, "VPP aggregation — BESS charging, EV fleet boosted, PV held",
         {**_vpp(200, 0, -60, -30, 145, mode="vpp", v_pu=1.05),
          "phase": "vpp_dispatch"}, False),
        (6, "Fully resolved — +18 kW import target, all DERs balanced",
         {**_vpp(200, 0, -75, -35, 178, mode="vpp", v_pu=1.02),
          "phase": "resolved"}, False),
        (7, "Island mode — grid disconnected, gas peaker forming voltage",
         {**_vpp(180, 60, -20, 0, 220, mode="vpp", islanded=True, v_pu=1.00),
          "phase": "island"}, False),
    ]
    for step_num, desc, state, trigger_alarm in mg_steps:
        db.add(SimulationStep(
            scenario_id=s3.id,
            step_number=step_num,
            description=desc,
            network_state=state,
            alarms_triggered=[{"type": "reverse_power"}] if trigger_alarm else [],
            commands_available=[
                {"cmd": "curtail_inverter", "label": "Curtail PV", "target_id": mg.id},
                {"cmd": "isolate_feeder", "label": "Isolate Feeder", "target_id": feeders[3].id},
            ],
            duration_seconds=8.0,
        ))

    # --- Scenario 4: Network Fault / FLISR ---
    # Use transformers [4..7] on feeders[1] as the 4 transformers of this feeder
    # Fault occurs between transformer index 6 (T-012) and 7 (T-015)
    fault_feeder = feeders[1]
    # Get transformer IDs on this feeder for the step data
    fault_transformers = [t for t in transformers if t.feeder_id == fault_feeder.id]
    # We expect 4 transformers per feeder from seed_network
    ft_ids = [t.id for t in fault_transformers]
    # Downstream of fault = last 2 transformers; upstream = first 2
    downstream_ids = ft_ids[2:] if len(ft_ids) >= 4 else ft_ids[-2:]
    upstream_ids = ft_ids[:2] if len(ft_ids) >= 4 else ft_ids[:2]
    ft_names = [t.name for t in fault_transformers]

    # Count meters per section
    total_meters_feeder = sum(
        len([m for m in (db.query(Meter).filter(Meter.transformer_id == tid).all())])
        for tid in ft_ids
    )
    downstream_meters = sum(
        len([m for m in (db.query(Meter).filter(Meter.transformer_id == tid).all())])
        for tid in downstream_ids
    )
    upstream_meters = total_meters_feeder - downstream_meters

    s4 = SimulationScenario(
        name="REQ-24: Network Fault & FLISR",
        scenario_type=ScenarioType.NETWORK_FAULT,
        status=ScenarioStatus.IDLE,
        description=(
            "Fault Location, Isolation, and Service Restoration (FLISR) scenario. "
            "A cable fault on Feeder F-003 triggers AMI-based fault location using first-dark-meter "
            "analysis, automated isolation via sectionalizer switches, staged service restoration "
            "through tie switches, and crew dispatch for repair."
        ),
        feeder_id=fault_feeder.id,
        transformer_id=fault_transformers[2].id if len(fault_transformers) > 2 else fault_transformers[0].id,
        parameters={
            "affected_customers_initial": downstream_meters,
            "total_customers_feeder": total_meters_feeder,
            "feeder_name": "F-003",
            "fault_segment": {
                "upstream_transformer": ft_names[2] if len(ft_names) > 2 else "T-012",
                "downstream_transformer": ft_names[3] if len(ft_names) > 3 else "T-015",
            },
            "topology": {
                "nodes": [
                    {"id": ft_ids[i], "name": ft_names[i], "type": "transformer",
                     "meter_count": len(db.query(Meter).filter(Meter.transformer_id == ft_ids[i]).all())}
                    for i in range(len(ft_ids))
                ],
                "switches": [
                    {"id": f"SW-{i+1}", "between": [ft_ids[i], ft_ids[i+1]], "state": "closed"}
                    for i in range(len(ft_ids) - 1)
                ],
            },
        },
        total_steps=8,
    )
    db.add(s4)
    db.flush()

    fault_steps = [
        # Step 1: Normal Operation
        (1,
         "Normal operation — all feeders energised, all meters online, green status across the board",
         {
             "phase": "normal",
             "affected_customers": 0,
             "feeder_voltage_kv": 11.0,
             "feeder_current_a": 180.0,
             "meters_online": total_meters_feeder,
             "meters_offline": 0,
             "switches": {"SW-1": "closed", "SW-2": "closed", "SW-3": "closed", "TIE-1": "open"},
             "topology_status": {str(tid): "energised" for tid in ft_ids},
         },
         False,
         []),

        # Step 2: Fault Occurs
        (2,
         f"FAULT on Feeder F-003 between {ft_names[2] if len(ft_names) > 2 else 'T-012'} and "
         f"{ft_names[3] if len(ft_names) > 3 else 'T-015'} — current spike 3x, protection relay trips, "
         f"{downstream_meters} customers lose supply",
         {
             "phase": "fault_occurs",
             "fault_type": "LV cable fault",
             "affected_customers": downstream_meters,
             "current_spike_factor": 3.0,
             "feeder_voltage_kv": 11.0,
             "feeder_current_a": 540.0,
             "downstream_transformer_ids": downstream_ids,
             "meters_online": upstream_meters,
             "meters_offline": downstream_meters,
             "switches": {"SW-1": "closed", "SW-2": "closed", "SW-3": "tripped", "TIE-1": "open"},
             "topology_status": {
                 **{str(tid): "energised" for tid in upstream_ids},
                 **{str(tid): "faulted" for tid in downstream_ids},
             },
         },
         True,
         [{"type": "fault_detected"}, {"type": "outage"}]),

        # Step 3: Fault Detection & Location
        (3,
         f"Fault location identified via first-dark-meter analysis — fault pinpointed between "
         f"{ft_names[2] if len(ft_names) > 2 else 'T-012'} and {ft_names[3] if len(ft_names) > 3 else 'T-015'}",
         {
             "phase": "fault_detection",
             "affected_customers": downstream_meters,
             "first_dark_meter": f"SA0102{len(ft_ids)-1:02d}001",
             "fault_location": {
                 "upstream": ft_names[2] if len(ft_names) > 2 else "T-012",
                 "downstream": ft_names[3] if len(ft_names) > 3 else "T-015",
             },
             "feeder_current_a": 0.0,
             "meters_online": upstream_meters,
             "meters_offline": downstream_meters,
             "switches": {"SW-1": "closed", "SW-2": "closed", "SW-3": "tripped", "TIE-1": "open"},
             "topology_status": {
                 **{str(tid): "energised" for tid in upstream_ids},
                 **{str(tid): "fault_located" for tid in downstream_ids},
             },
         },
         True,
         [{"type": "comm_loss"}]),

        # Step 4: Fault Isolation
        (4,
         "Fault segment isolated — sectionalizer switches opened at fault boundary",
         {
             "phase": "fault_isolation",
             "affected_customers": downstream_meters,
             "feeder_current_a": 120.0,
             "meters_online": upstream_meters,
             "meters_offline": downstream_meters,
             "switches": {"SW-1": "closed", "SW-2": "open", "SW-3": "open", "TIE-1": "open"},
             "topology_status": {
                 **{str(tid): "energised" for tid in upstream_ids},
                 **{str(tid): "isolated" for tid in downstream_ids},
             },
         },
         False,
         [{"cmd": "open_switch_upstream", "label": "Open Upstream Switch"}, {"cmd": "open_switch_downstream", "label": "Open Downstream Switch"}]),

        # Step 5: Service Restoration Phase 1
        (5,
         f"Tie switch closed to alternate feeder — ~60% of affected consumers restored "
         f"({int(downstream_meters * 0.6)} of {downstream_meters})",
         {
             "phase": "restore_phase1",
             "affected_customers": downstream_meters,
             "restored_customers": int(downstream_meters * 0.6),
             "restore_transformer_ids": downstream_ids[:1],
             "feeder_current_a": 140.0,
             "meters_online": upstream_meters + int(downstream_meters * 0.6),
             "meters_offline": downstream_meters - int(downstream_meters * 0.6),
             "restoration_percent": 60,
             "switches": {"SW-1": "closed", "SW-2": "open", "SW-3": "open", "TIE-1": "closed"},
             "topology_status": {
                 **{str(tid): "energised" for tid in upstream_ids},
                 str(downstream_ids[0]): "restored_alt" if downstream_ids else "restored_alt",
                 **(
                     {str(downstream_ids[1]): "isolated"} if len(downstream_ids) > 1 else {}
                 ),
             },
         },
         False,
         [{"cmd": "restore_feeder", "label": "Close Tie Switch", "target_id": fault_feeder.id}]),

        # Step 6: Service Restoration Phase 2
        (6,
         f"Remaining switches reconfigured — ~95% restored "
         f"({int(downstream_meters * 0.95)} of {downstream_meters}). "
         f"Only fault-segment meters remain offline",
         {
             "phase": "restore_phase2",
             "affected_customers": downstream_meters,
             "restored_customers": int(downstream_meters * 0.95),
             "restore_transformer_ids": downstream_ids[1:] if len(downstream_ids) > 1 else [],
             "feeder_current_a": 160.0,
             "meters_online": upstream_meters + int(downstream_meters * 0.95),
             "meters_offline": downstream_meters - int(downstream_meters * 0.95),
             "restoration_percent": 95,
             "switches": {"SW-1": "closed", "SW-2": "open", "SW-3": "closed", "TIE-1": "closed"},
             "topology_status": {str(tid): "restored_alt" if tid in downstream_ids else "energised" for tid in ft_ids},
         },
         False,
         []),

        # Step 7: Crew Dispatch & Repair
        (7,
         f"Work order WO-{s4.id:04d} generated — repair crew dispatched to fault segment. "
         f"Network stable on alternate feed",
         {
             "phase": "crew_dispatch",
             "affected_customers": downstream_meters - int(downstream_meters * 0.95),
             "feeder_current_a": 160.0,
             "meters_online": upstream_meters + int(downstream_meters * 0.95),
             "meters_offline": downstream_meters - int(downstream_meters * 0.95),
             "restoration_percent": 95,
             "work_order": f"WO-{s4.id:04d}",
             "crew_status": "dispatched",
             "switches": {"SW-1": "closed", "SW-2": "open", "SW-3": "closed", "TIE-1": "closed"},
             "topology_status": {str(tid): "restored_alt" if tid in downstream_ids else "energised" for tid in ft_ids},
         },
         True,
         [{"type": "fault_detected", "severity": "medium"}]),

        # Step 8: Normal Operation Restored
        (8,
         "Fault repaired — original switching restored, all meters online, all alarms resolved",
         {
             "phase": "fully_restored",
             "affected_customers": 0,
             "feeder_voltage_kv": 11.0,
             "feeder_current_a": 180.0,
             "normal_load_kw": fault_feeder.current_load_kw,
             "meters_online": total_meters_feeder,
             "meters_offline": 0,
             "restoration_percent": 100,
             "switches": {"SW-1": "closed", "SW-2": "closed", "SW-3": "closed", "TIE-1": "open"},
             "topology_status": {str(tid): "energised" for tid in ft_ids},
         },
         False,
         []),
    ]

    for step_num, desc, state, trigger_alarm, cmds_or_alarms in fault_steps:
        # Determine alarms_triggered and commands_available
        alarms_triggered = cmds_or_alarms if trigger_alarm else []
        # Commands available change by step
        commands = []
        if step_num == 4:
            commands = cmds_or_alarms  # switch commands
        elif step_num == 5:
            commands = cmds_or_alarms  # restore command
        elif step_num in (1, 2, 3):
            commands = []
        else:
            commands = []

        db.add(SimulationStep(
            scenario_id=s4.id,
            step_number=step_num,
            description=desc,
            network_state=state,
            alarms_triggered=alarms_triggered if trigger_alarm else [],
            commands_available=commands if not trigger_alarm else [
                {"cmd": "isolate_feeder", "label": "Isolate Fault Section", "target_id": fault_feeder.id},
                {"cmd": "restore_feeder", "label": "Restore Feeder", "target_id": fault_feeder.id},
            ],
            duration_seconds=10.0,
        ))

    # --- Scenario 5: Transformer Sensor Monitoring (REQ-25) ---
    # Use transformer T-005 (index 4) in Soweto area
    t_sensor = transformers[4]
    t_sensor_backup = transformers[5]

    s5 = SimulationScenario(
        name="REQ-25: Transformer Sensor Monitoring",
        scenario_type=ScenarioType.SENSOR_ASSET,
        status=ScenarioStatus.IDLE,
        description=(
            "Monitor transformer health via DCU-connected sensors on 11kV/400V 315kVA "
            "transformer T-005. Detect overtemperature and oil anomalies, apply load "
            "management and emergency response."
        ),
        feeder_id=feeders[0].id,
        transformer_id=t_sensor.id,
        parameters={
            "transformer_name": t_sensor.name,
            "transformer_capacity_kva": 315.0,
            "voltage_class": "11kV/400V",
            "backup_transformer_id": t_sensor_backup.id,
            "backup_transformer_name": t_sensor_backup.name,
        },
        total_steps=8,
    )
    db.add(s5)
    db.flush()

    sensor_steps = [
        # Step 1: Normal Monitoring
        (1,
         "Normal monitoring — all transformer sensors within operating range. "
         "T-005 (315 kVA, 11kV/400V) at 65% loading.",
         {
             "loading_percent": 65.0,
             "sensor_values": {
                 "winding_temp": 65.0, "oil_temp": 55.0, "oil_level": 95.0,
                 "vibration": 0.5, "humidity": 35.0,
                 "current_phase_a": 280.0, "current_phase_b": 275.0, "current_phase_c": 282.0,
             },
             "resolve_alarms": True,
         },
         [],
         []),

        # Step 2: Temperature Rising
        (2,
         "Load increasing on T-005 — winding temperature rising towards warning threshold. "
         "Oil temperature elevated.",
         {
             "loading_percent": 82.0,
             "sensor_values": {
                 "winding_temp": 75.0, "oil_temp": 62.0, "oil_level": 94.5,
                 "vibration": 0.7, "humidity": 36.0,
                 "current_phase_a": 354.0, "current_phase_b": 348.0, "current_phase_c": 356.0,
             },
         },
         [{"type": "transformer_overload", "severity": "info",
           "message": "Temperature trend alert: winding temp 75 degC approaching warning threshold (80 degC)",
           "value": 75.0, "threshold": 80.0, "unit": "degC"}],
         []),

        # Step 3: Warning Threshold Crossed
        (3,
         "WARNING — Winding temperature 85 degC exceeds warning threshold (80 degC). "
         "Oil temperature elevated. Vibration increasing.",
         {
             "loading_percent": 95.0,
             "sensor_values": {
                 "winding_temp": 85.0, "oil_temp": 72.0, "oil_level": 94.0,
                 "vibration": 1.2, "humidity": 38.0,
                 "current_phase_a": 410.0, "current_phase_b": 405.0, "current_phase_c": 412.0,
             },
         },
         [{"type": "transformer_overload", "severity": "high",
           "message": "Transformer overtemperature WARNING: winding 85 degC (threshold 80 degC), oil 72 degC. "
                      "Vibration 1.2 mm/s. Recommend load reduction.",
           "value": 85.0, "threshold": 80.0, "unit": "degC"}],
         [{"cmd": "reduce_load", "label": "Reduce Load (Shift to Adjacent TX)", "target_id": t_sensor.id}]),

        # Step 4: Load Reduction Applied
        (4,
         "Load reduction applied — meters shifted to adjacent transformer. "
         "Winding temp stabilises at 82 degC. Loading drops from 95% to 75%.",
         {
             "loading_percent": 75.0,
             "sensor_values": {
                 "winding_temp": 82.0, "oil_temp": 68.0, "oil_level": 94.0,
                 "vibration": 0.9, "humidity": 37.0,
                 "current_phase_a": 324.0, "current_phase_b": 320.0, "current_phase_c": 326.0,
             },
         },
         [],
         []),

        # Step 5: Oil Level Anomaly
        (5,
         "Oil level anomaly detected — dropped from 95% to 85%. Possible gasket leak. "
         "Maintenance required.",
         {
             "loading_percent": 75.0,
             "sensor_values": {
                 "winding_temp": 80.0, "oil_temp": 66.0, "oil_level": 85.0,
                 "vibration": 0.8, "humidity": 42.0,
                 "current_phase_a": 324.0, "current_phase_b": 320.0, "current_phase_c": 326.0,
             },
         },
         [{"type": "transformer_overload", "severity": "high",
           "message": "Oil level WARNING: 85% (threshold 90%). Possible gasket leak detected. "
                      "Humidity rising to 42%. Schedule maintenance inspection.",
           "value": 85.0, "threshold": 90.0, "unit": "%"}],
         [{"cmd": "schedule_maintenance", "label": "Schedule Maintenance Inspection", "target_id": t_sensor.id}]),

        # Step 6: Critical Alert
        (6,
         "CRITICAL — Winding temperature 90 degC (critical threshold). "
         "Oil level 80%. Immediate action required.",
         {
             "loading_percent": 88.0,
             "sensor_values": {
                 "winding_temp": 90.0, "oil_temp": 80.0, "oil_level": 80.0,
                 "vibration": 1.8, "humidity": 48.0,
                 "current_phase_a": 380.0, "current_phase_b": 374.0, "current_phase_c": 382.0,
             },
         },
         [{"type": "transformer_overload", "severity": "critical",
           "message": "CRITICAL: Winding temp 90 degC (limit 90 degC), oil temp 80 degC, "
                      "oil level 80% (critical 82%). Vibration 1.8 mm/s. "
                      "IMMEDIATE ACTION REQUIRED — risk of transformer failure.",
           "value": 90.0, "threshold": 90.0, "unit": "degC"}],
         [{"cmd": "emergency_load_transfer", "label": "Emergency Load Transfer", "target_id": t_sensor.id},
          {"cmd": "crew_dispatch", "label": "Dispatch Maintenance Crew", "target_id": t_sensor.id}]),

        # Step 7: Emergency Response
        (7,
         "Emergency load transfer executed — all load transferred to backup transformer. "
         "T-005 de-energised for inspection. Temperatures dropping.",
         {
             "loading_percent": 0.0,
             "sensor_values": {
                 "winding_temp": 72.0, "oil_temp": 65.0, "oil_level": 80.0,
                 "vibration": 0.1, "humidity": 45.0,
                 "current_phase_a": 0.0, "current_phase_b": 0.0, "current_phase_c": 0.0,
             },
         },
         [],
         []),

        # Step 8: Resolution
        (8,
         "Maintenance complete — gasket replaced, oil topped up. "
         "T-005 re-energised at reduced load. All sensors back to normal.",
         {
             "loading_percent": 55.0,
             "sensor_values": {
                 "winding_temp": 58.0, "oil_temp": 48.0, "oil_level": 96.0,
                 "vibration": 0.4, "humidity": 33.0,
                 "current_phase_a": 238.0, "current_phase_b": 234.0, "current_phase_c": 240.0,
             },
             "resolve_alarms": True,
         },
         [],
         []),
    ]

    for step_num, desc, state, alarms_data, cmds_data in sensor_steps:
        db.add(SimulationStep(
            scenario_id=s5.id,
            step_number=step_num,
            description=desc,
            network_state=state,
            alarms_triggered=alarms_data,
            commands_available=cmds_data,
            duration_seconds=8.0,
        ))

    db.commit()
    print(f"  Simulation scenarios seeded: 5 scenarios with steps (REQ-21 to REQ-25)")


def seed_transformer_sensors(db, transformers):
    """Seed DCU-connected sensors for key transformers (REQ-25)."""
    # Sensor definitions: (sensor_type, name, unit, default_value, warning, critical)
    SENSOR_DEFS = [
        ("winding_temp",    "Winding Temperature",  "degC",  65.0, 80.0,  90.0),
        ("oil_temp",        "Oil Temperature",      "degC",  55.0, 70.0,  80.0),
        ("oil_level",       "Oil Level",            "%",     95.0, 90.0,  82.0),   # reverse: warning when LOW
        ("vibration",       "Vibration",            "mm/s",   0.5,  1.5,   2.5),
        ("humidity",        "Humidity",             "%",     35.0, 50.0,  65.0),
        ("current_phase_a", "Current Phase A",      "A",    280.0, 400.0, 450.0),
        ("current_phase_b", "Current Phase B",      "A",    275.0, 400.0, 450.0),
        ("current_phase_c", "Current Phase C",      "A",    282.0, 400.0, 450.0),
    ]

    # Instrument 4 key transformers: T-005 (primary scenario), plus 3 others
    target_indices = [4, 5, 10, 15]
    total = 0

    for t_idx in target_indices:
        if t_idx >= len(transformers):
            continue
        transformer = transformers[t_idx]
        for stype, sname, unit, default_val, warn, crit in SENSOR_DEFS:
            # Add slight variation per transformer
            variation = random.uniform(0.95, 1.05)
            sensor = TransformerSensor(
                transformer_id=transformer.id,
                sensor_type=stype,
                name=f"{sname} — {transformer.name}",
                value=round(default_val * variation, 1),
                unit=unit,
                threshold_warning=warn,
                threshold_critical=crit,
                status=SensorStatus.NORMAL,
            )
            db.add(sensor)
            total += 1

    db.commit()
    print(f"  Transformer sensors seeded: {total} sensors on {len(target_indices)} transformers")


def _refresh_simulation_scenarios(db):
    """Idempotent reseed of just the demo simulation scenarios.

    The scenarios table holds presentation data driving the SMOC
    /simulation page — safe to delete+recreate on every pod start so the
    richer per-step `network_state` payloads flow without a DB wipe.
    """
    feeders = db.query(Feeder).order_by(Feeder.id).all()
    transformers = db.query(Transformer).order_by(Transformer.id).all()
    if not feeders or not transformers:
        print("  Skipping scenario refresh — network not seeded.")
        return
    # Microgrid-typed DERs aren't always seeded in older dev DBs — fall back
    # to any DER on a feeder as the FK target so the scenario still seeds.
    pv = db.query(DERAsset).filter(DERAsset.asset_type == DERType.PV).first()
    ev = db.query(DERAsset).filter(DERAsset.asset_type == DERType.EV_CHARGER).first()
    mg = (
        db.query(DERAsset).filter(DERAsset.asset_type == DERType.MICROGRID).first()
        or db.query(DERAsset).filter(DERAsset.asset_type == DERType.BESS).first()
        or pv
    )
    if not (pv and ev and mg):
        print("  Skipping scenario refresh — required DER assets missing.")
        return

    # Only delete after prereq check so a failed lookup never empties the
    # scenarios table.
    from app.models.alarm import Alarm
    db.query(Alarm).filter(Alarm.scenario_id.isnot(None)).update(
        {Alarm.scenario_id: None}, synchronize_session=False
    )
    db.query(SimulationStep).delete(synchronize_session=False)
    db.query(SimulationScenario).delete(synchronize_session=False)
    db.commit()

    seed_simulation_scenarios(db, feeders, transformers, pv, ev, mg)
    db.commit()
    print("  Scenario refresh complete.")


def main():
    print("Seeding SMOC EMS database with South Africa LV network data...")
    db = SessionLocal()
    try:
        # Always ensure the full user set exists (idempotent — seed_users
        # itself short-circuits per username). This lets us add analyst /
        # viewer roles to dev without wiping the seeded network.
        print("Ensuring seed users...")
        seed_users(db)

        # Check if the rest of the network is already seeded
        if db.query(User).count() > 0 and db.query(Meter).count() > 0:
            print("Database already seeded. Refreshing simulation scenarios only.")
            # Refresh demo simulation scenarios so richer network_state /
            # parameters roll in without a full DB wipe. Safe because the
            # scenarios table is a presentation artefact, not load-bearing data.
            _refresh_simulation_scenarios(db)
            return

        print("Seeding SA LV network (feeders, transformers, meters)...")
        feeders, transformers, meters = seed_network(db)

        print("Seeding DER assets...")
        pv, bess, ev, mg = seed_der_assets(db, transformers)

        print("Seeding active alarms...")
        seed_alarms(db, meters, transformers)

        print(f"Seeding 7-day historical readings ({len(meters)} meters × 168 hours)...")
        seed_readings(db, meters)

        print("Seeding transformer sensors (REQ-25)...")
        seed_transformer_sensors(db, transformers)

        print("Seeding simulation scenarios...")
        seed_simulation_scenarios(db, feeders, transformers, pv, ev, mg)

        print("Seeding energy daily summary...")
        seed_energy_daily_summary(db, meters)

        print("Seeding audit events...")
        seed_audit_events(db, meters)

        print("Seeding HES data (DCUs, commands, FOTA)...")
        seed_hes_data(db, feeders, meters)

        print("Seeding MDMS data (VEE, consumers, tariffs, NTL, PQ)...")
        seed_mdms_data(db, meters, transformers)

        print("Seeding Alert Management default groups + critical-customer tags...")
        seed_alert_defaults(db)

        print("\nSeed complete!")
        print(f"  Users:       3 (admin/Admin@2026, supervisor/Super@2026, operator/Oper@2026)")
        print(f"  Feeders:     {len(feeders)}")
        print(f"  Transformers:{len(transformers)}")
        print(f"  Meters:      {len(meters)}")
        print(f"  DER assets:  4 (PV, BESS, EV charger, Microgrid)")
        print(f"  Sensors:     32 (8 sensors x 4 transformers)")
        print(f"  Scenarios:   5 (REQ-21 to REQ-25)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
