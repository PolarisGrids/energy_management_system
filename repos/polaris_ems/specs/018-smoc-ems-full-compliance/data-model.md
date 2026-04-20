# Data Model: EMS-Owned Entities (Spec 018)

EMS owns only domains not in MDMS or HES. Everything else is read-through.

## Owned Tables

### `outage_incident`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| opened_at | TIMESTAMPTZ | |
| closed_at | TIMESTAMPTZ NULL | |
| status | VARCHAR(20) | DETECTED → INVESTIGATING → DISPATCHED → RESTORED |
| suspected_fault_point | GEOMETRY(Point, 4326) | PostGIS |
| affected_dtr_ids | TEXT[] | |
| affected_meter_count | INTEGER | |
| confidence_pct | NUMERIC(5,2) | |
| timeline | JSONB | append-only event list |
| saidi_contribution_s | INTEGER | |
| trigger_trace_id | VARCHAR(64) | for correlation |

Indexes: `status`, `opened_at DESC`, GIST on `suspected_fault_point`.

### `transformer_sensor_reading`
| col | type | notes |
|---|---|---|
| id | BIGSERIAL PK | |
| sensor_id | VARCHAR(100) | |
| dtr_id | VARCHAR(100) | |
| type | VARCHAR(50) | oil_temp / load_current / etc. |
| value | NUMERIC(12,4) | |
| unit | VARCHAR(20) | |
| breach_flag | BOOLEAN | |
| threshold_max | NUMERIC(12,4) | |
| ts | TIMESTAMPTZ | |

Partition by month on `ts`. Index `(sensor_id, ts DESC)`.

### `der_asset`
| col | type | notes |
|---|---|---|
| id | VARCHAR(100) PK | matches simulator |
| type | VARCHAR(20) | pv / bess / ev / microgrid |
| name | TEXT | |
| dtr_id | VARCHAR(100) | |
| feeder_id | VARCHAR(100) | |
| location | GEOMETRY(Point, 4326) | |
| capacity_kw | NUMERIC(10,2) | |
| capacity_kwh | NUMERIC(10,2) NULL | BESS only |
| metadata | JSONB | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `der_telemetry`
| col | type | notes |
|---|---|---|
| id | BIGSERIAL PK | |
| asset_id | VARCHAR(100) | FK |
| ts | TIMESTAMPTZ | |
| state | VARCHAR(20) | |
| active_power_kw | NUMERIC | |
| reactive_power_kvar | NUMERIC | |
| soc_pct | NUMERIC(5,2) NULL | |
| session_energy_kwh | NUMERIC NULL | |
| achievement_rate_pct | NUMERIC NULL | |
| curtailment_pct | NUMERIC | |

Partition by week.

### `der_command`
| col | type | notes |
|---|---|---|
| id | UUID PK | command_id from HES |
| asset_id | VARCHAR(100) | |
| command_type | VARCHAR(40) | curtail / set_active_power / etc. |
| setpoint | NUMERIC | |
| status | VARCHAR(20) | QUEUED / ACK / EXECUTED / CONFIRMED / FAILED / TIMEOUT |
| issued_at | TIMESTAMPTZ | |
| confirmed_at | TIMESTAMPTZ NULL | |
| issuer_user_id | VARCHAR(200) | |
| trace_id | VARCHAR(64) | |

### `alarm_event`
Already exists; extended for `source_trace_id`, `correlation_group_id` (for outage bundling).

### `virtual_object_group`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| name | TEXT | |
| selector | JSONB | { hierarchy: [...], filters: {...} } |
| owner_user_id | VARCHAR(200) | |
| shared_with_roles | TEXT[] | |

### `alarm_rule`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| group_id | UUID FK | virtual_object_group |
| name | TEXT | |
| condition | JSONB | AST of condition |
| action | JSONB | notification channels, webhook, command |
| priority | INTEGER | 1–5 |
| active | BOOLEAN | |
| schedule | JSONB NULL | quiet hours, escalation tiers |

### `notification_delivery`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| rule_id | UUID FK | |
| channel | VARCHAR(20) | sms / email / push / teams |
| recipient | TEXT | |
| payload | JSONB | |
| status | VARCHAR(20) | |
| provider_reference | TEXT NULL | |
| sent_at | TIMESTAMPTZ | |

### `app_def` / `rule_def` / `algorithm_def`
Versioned author/publish model.
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| slug | TEXT UNIQUE per version | |
| version | INTEGER | |
| author_user_id | VARCHAR(200) | |
| status | VARCHAR(20) | DRAFT / PREVIEW / PUBLISHED / ARCHIVED |
| definition | JSONB | widget layout / rule AST / algorithm source |
| published_at | TIMESTAMPTZ NULL | |
| approved_by | VARCHAR(200) NULL | |

Unique constraint on (slug, version). Only one PUBLISHED per slug.

### `dashboard_layout`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| owner_user_id | VARCHAR(200) | |
| name | TEXT | |
| widgets | JSONB | |
| shared_with_roles | TEXT[] | |
| updated_at | TIMESTAMPTZ | |

### `scheduled_report`
| col | type | notes |
|---|---|---|
| id | UUID PK | |
| owner_user_id | VARCHAR(200) | |
| report_ref | TEXT | e.g. `egsm:energy-audit:monthly-consumption` |
| params | JSONB | |
| schedule_cron | TEXT | |
| recipients | TEXT[] | |
| last_run_at | TIMESTAMPTZ NULL | |
| last_status | VARCHAR(20) | |

### `source_status` (cache)
| col | type | notes |
|---|---|---|
| meter_serial | VARCHAR(100) PK | |
| hes_last_seen | TIMESTAMPTZ | |
| mdms_last_validated | TIMESTAMPTZ | |
| cis_last_billing | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

Refreshed by a scheduled job every 5 min joining HES + MDMS + CIS APIs.

## Read-Through References

EMS MUST NOT shadow-copy these entities. It stores only IDs and reads live:

- Meter (authoritative in HES registry + MDMS CIS)
- Consumer (MDMS CIS)
- Tariff (MDMS billing)
- Reading / billing determinant (MDMS VEE + billing)
- VEE rules, exceptions (MDMS VEE)
- NTL suspects (MDMS NTL)
- Feeder / DTR / pole geometry (MDMS CIS PostGIS)
- Audit log rows (MDMS CIS — EMS publishes, MDMS stores)

## Alembic Baseline

First migration `20260418_000_baseline.py` creates the current live schema plus all tables above. Subsequent `20260418_001_outage_correlation.py`, `20260418_002_app_builder.py`, etc. per wave.

## ERD (summary)

```
outage_incident ── affected_dtr_ids → DTR(MDMS,read-through)
der_asset ── dtr_id, feeder_id → MDMS topology
der_telemetry → der_asset
der_command → der_asset
transformer_sensor_reading → sensor_id, dtr_id
alarm_event → meter_serial (HES/MDMS, read-through)
virtual_object_group → hierarchy (MDMS, read-through)
alarm_rule → virtual_object_group
notification_delivery → alarm_rule
app_def | rule_def | algorithm_def — standalone versioned
dashboard_layout → per-user
scheduled_report → per-user
source_status → meter_serial (HES/MDMS, read-through)
```
