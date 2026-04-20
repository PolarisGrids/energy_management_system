# Polaris EMS — Database

PostgreSQL 16 schema defined via SQLAlchemy 2.0 models. No Alembic migrations are tracked yet — `Base.metadata.create_all()` (or seed script) materialises the schema on first boot.

## Connection

- **Engine**: PostgreSQL 16 (Alpine in Docker Compose; managed EC2 PG in AWS dev)
- **Driver**: `psycopg2-binary`
- **Session factory**: `app/db/base.py` → `SessionLocal` (autocommit off, autoflush off, `pool_pre_ping=True`)
- **URL**: `postgresql://smoc:<pw>@db:5432/smoc_ems` (overridable via `DATABASE_URL` in `backend/.env`)

## Schema Overview

20 application tables grouped by domain. All timestamps are timezone-naïve IST unless specified.

### Identity & Audit

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Operators / supervisors / admins for SMOC login | `id` PK, `username` UQ, `email` UQ, `role` (OPERATOR/SUPERVISOR/ADMIN), `hashed_password`, `is_active`, `last_login` |
| `audit_events` | Every operator action (command, ack, threshold change, login) | `id` PK, `timestamp` IDX, `user_name`, `user_role`, `event_type` IDX, `action`, `resource`, `ip_address`, `result`, `details` JSONB |

### Network Topology

| Table | Purpose | Key columns |
|---|---|---|
| `feeders` | HV/MV feeders (model referenced from `__init__.py`; definition inline in routers) | `id` PK |
| `transformers` | Distribution transformers | `id` PK, FK referenced from sensors/DER |
| `meters` | Smart meters (consumer end-points) | `serial` key used across readings/alarms/DER |
| `network_events` | Outage / restore / fault / switching / DER connect/disconnect / overload / voltage violation | `event_type` enum, `feeder_id`, `transformer_id`, `meter_serial`, `der_asset_id`, `lat/lng`, `affected_customers`, `duration_minutes`, `resolved`, `event_data` JSONB, `occurred_at` IDX, `scenario_id` |

> Note: `Meter`, `Transformer`, `Feeder`, `MeterStatus`, `RelayState` are imported from `app/models/meter.py`. That file is currently stubbed out in the working tree — re-hydrate before removing the seed script dependency.

### Metering Data

| Table | Purpose | Key columns |
|---|---|---|
| `meter_readings` | Interval readings (energy, demand, voltage, current, PF, Hz, THD) | `meter_serial` IDX, `timestamp` IDX, composite `ix_meter_readings_serial_ts`, `is_estimated` flag |
| `energy_daily_summary` | Pre-aggregated network totals per day | `date` UQ, import/export kWh, peak demand, avg PF, residential/commercial/prepaid splits |

### Assets & Telemetry

| Table | Purpose | Key columns |
|---|---|---|
| `transformer_sensors` | Winding/oil temp, level, vibration, humidity, phase current | `transformer_id` FK, `sensor_type`, `value`, `unit`, `threshold_warning`, `threshold_critical`, `status` (NORMAL/WARNING/CRITICAL/OFFLINE) |
| `der_assets` | PV / BESS / EV charger / microgrid / wind | `asset_type`, `status`, `rated_capacity_kw`, `current_output_kw`, `state_of_charge`, `generation_today_kwh`, `num_ports`, `active_sessions`, `islanded`, `metadata` JSONB |
| `alarms` | Operational alarms across the fleet | `alarm_type` (14 enum values inc. TAMPER/OUTAGE/OVERVOLTAGE/NTS_DETECTED), `severity`, `status`, `meter_serial`/`transformer_id`/`feeder_id`/`der_asset_id`, `triggered_at` IDX, `acknowledged_at/by`, `resolved_at`, `scenario_id` |

### Simulation Engine

| Table | Purpose | Key columns |
|---|---|---|
| `simulation_scenarios` | Scripted demo scenarios (SOLAR_OVERVOLTAGE, EV_FAST_CHARGING, PEAKING_MICROGRID, NETWORK_FAULT, SENSOR_ASSET) | `scenario_type`, `status` (IDLE/RUNNING/PAUSED/COMPLETED/ABORTED), `current_step`, `total_steps`, `parameters` JSONB |
| `simulation_steps` | Per-step network state + alarm set | `scenario_id` FK, `step_number`, `network_state` JSONB, `alarms_triggered` JSONB, `commands_available` JSONB, `duration_seconds` |

### HES Mirror (AMI)

| Table | Purpose | Key columns |
|---|---|---|
| `hes_dcus` | Data Concentrator Units | `id` PK (str), `location`, `total_meters`, `online_meters`, `last_comm`, `status`, `firmware_version`, `comm_tech` |
| `hes_command_log` | RC/DC, timesync, read commands dispatched to meters | `timestamp` IDX, `meter_serial`, `command_type`, `status`, `operator`, `response_time_ms`, `details` JSONB |
| `hes_fota_jobs` | Firmware OTA rollouts | `id` PK (str), `target_description`, `total_meters`, `updated_count`, `failed_count`, `status`, `firmware_from/to` |

### MDMS Mirror

| Table | Purpose | Key columns |
|---|---|---|
| `vee_daily_summary` | Daily VEE pass/estimate/fail totals | `date` UQ |
| `vee_exceptions` | Per-meter VEE exceptions pending operator review | `meter_serial`, `exception_type`, `date` IDX, `original_value`, `corrected_value`, `status` (Pending/Approved/Rejected) |
| `consumer_accounts` | Consumer master data mirrored from CIS | `account_number` PK, `customer_name`, `tariff_name`, `meter_serial`, `transformer_id`, `phase`, `prepaid_balance` |
| `tariff_schedules` | TOU tariff rates | `name`, `tariff_type`, `offpeak_rate`, `standard_rate`, `peak_rate`, `effective_from`, `currency` (ZAR) |
| `ntl_suspects` | Non-technical loss candidates | `meter_serial`, `risk_score` IDX, `flag` (Red/Amber/Green), `pattern_description` |
| `power_quality_zones` | Zone-level PQ compliance | `zone_name`, `voltage_deviation_pct`, `thd_pct`, `flicker_pst`, `compliant` |

## Seeding

`backend/scripts/seed_data.py` runs on container start (`CMD` in Dockerfile) and populates a demo dataset: feeders → transformers → meters → readings + alarms + DER + scenarios. Safe to re-run — guards against duplicates by natural key.

## Migration Path

When schema churn slows, introduce Alembic:

```bash
cd backend
alembic init alembic              # already initialised; revisions dir empty
alembic revision --autogenerate -m "baseline"
alembic upgrade head
```

Drop reliance on `create_all()` in the lifespan once the baseline is committed.
