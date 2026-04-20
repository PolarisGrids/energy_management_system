# Contract: EMS ↔ HES Integration

## Transport

- HTTP to HES routing-service: `http://hes-routing-service.hes.svc.cluster.local:8080`
- EMS gateway: `/api/v1/hes/*` pass-through (R/W)
- Kafka: `hesv2.*` topics on dev cluster (SASL/SCRAM auth; creds in Secrets Manager)
- Trace: W3C TraceContext across HTTP and Kafka headers (per `otel-common-*` libraries)

## REST Endpoints EMS Calls (outbound)

| Purpose | Method + Path | Feature flag |
|---|---|---|
| Issue meter command | `POST /api/v1/commands` with `{type, meter_serial, payload}` | `HES_ENABLED` |
| Batch command | `POST /api/v1/commands/batch` | `HES_ENABLED` |
| FOTA job create | `POST /api/v1/firmware-upgrade` | `HES_ENABLED` |
| FOTA job status | `GET /api/v1/firmware-upgrade/:job_id` | `HES_ENABLED` |
| DCU list + health | `GET /api/v1/dcus`, `/dcus/:id/health` | `HES_ENABLED` |
| On-demand register read | `POST /api/v1/commands` with `type=READ_BILLING_REGISTER` | `HES_ENABLED` |
| Time sync broadcast | `POST /api/v1/commands/timesync` | `HES_ENABLED` |
| DER inverter command | `POST /api/v1/commands` with `type=DER_CURTAIL|DER_SET_ACTIVE_POWER|…` | `SMART_INVERTER_COMMANDS_ENABLED` + MDMS-T5 |

## Kafka Topics EMS Consumes

| Topic | Purpose | Partition key | Consumer group |
|---|---|---|---|
| `hesv2.meter.events` | Power failure/restore, cover-open, tamper, reverse-energy | meter_serial | `polaris-ems-events` |
| `hesv2.meter.alarms` | Threshold breaches from meter | meter_serial | `polaris-ems-alarms` |
| `hesv2.command.status` | Command lifecycle ACK/EXECUTED/CONFIRMED/TIMEOUT | command_id | `polaris-ems-commands` |
| `hesv2.sensor.readings` | Transformer + distribution-room sensors | sensor_id | `polaris-ems-sensors` |
| `hesv2.outage.alerts1` | Existing outage signals | dtr_id | `polaris-ems-outage` |
| `hesv2.network.health` | DCU online/offline, RSSI, retry stats | dcu_id | `polaris-ems-comms` |
| `hesv2.der.telemetry` | PV/BESS/EV per-interval output/state | asset_id | `polaris-ems-der` |
| `decoded.packets.PUSH` | Block-load / daily / monthly pushed readings (OPTIONAL — MDMS ingests primarily) | meter_serial | `polaris-ems-readings-observer` (optional) |

Each topic has DLQ `*.dlq` and per-consumer-group lag alert in Prometheus.

## Message Schemas (key fields)

### `hesv2.meter.events`
```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "meter_serial": "S123",
  "event_type": "power_failure|power_restored|cover_open|magnet_tamper|ct_bypass|reverse_energy|firmware_applied",
  "dlms_event_code": 81,
  "timestamp": "2026-04-18T12:34:56+05:30",
  "dcu_id": "DCU-03",
  "traceparent": "00-..."
}
```

### `hesv2.command.status`
```json
{
  "command_id": "uuid",
  "meter_serial": "S123",
  "status": "ACK|EXECUTED|CONFIRMED|FAILED|TIMEOUT",
  "response_payload": {...},
  "timestamp": "...",
  "retry_count": 0,
  "traceparent": "00-..."
}
```

### `hesv2.network.health`
```json
{
  "dcu_id": "DCU-03",
  "status": "ONLINE|OFFLINE|DEGRADED",
  "rssi_dbm": -78,
  "success_rate_pct": 94.2,
  "retry_count_last_hour": 12,
  "meters_connected": 120,
  "timestamp": "..."
}
```

### `hesv2.sensor.readings`
```json
{
  "sensor_id": "SEN-DTR001-OIL-TEMP",
  "dtr_id": "DTR-001",
  "type": "oil_temperature|oil_level|core_temp|load_current|room_temperature|humidity|smoke|water|door_access",
  "value": 72.4,
  "unit": "C",
  "breach_flag": false,
  "timestamp": "..."
}
```

## Persistence Side-Effects in EMS

| Topic | Persists to |
|---|---|
| `hesv2.meter.events` | `meter_event_log` + triggers `outage_correlator` |
| `hesv2.meter.alarms` | `alarm_event` |
| `hesv2.command.status` | updates `command_log`; on CONFIRMED, updates `meter.relay_state`, `meter.last_command_id` |
| `hesv2.sensor.readings` | `transformer_sensor_reading` (replaces random history) |
| `hesv2.network.health` | `dcu_health_cache` (TTL 5 min) |
| `hesv2.der.telemetry` | `der_telemetry` (time-series) |

## Error Handling

- Consumer restart resumes from last committed offset (at-least-once).
- Malformed payload → DLQ + metric `kafka_dlq_messages_total`.
- Upstream REST 5xx → retry with backoff; after N failures, circuit open and banner in UI.

## Test Fixtures

- `tests/integration/fixtures/hes/`: recorded command-status and event streams.
- `tests/integration/hes_integration/`: live HES tests against dev; marker `@pytest.mark.live_hes`.
