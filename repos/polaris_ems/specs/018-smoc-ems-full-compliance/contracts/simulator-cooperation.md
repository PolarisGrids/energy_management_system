# Contract: EMS ↔ Simulator Cooperation

**Principle**: EMS never consumes directly from simulator. Simulator → HES → EMS is the only data path for metering/events. Two narrow exceptions:

1. **DER bulk-import at bootstrap** — simulator calls EMS once to populate DER asset list.
2. **Scenario control passthrough** — EMS frontend calls simulator REST API (via EMS backend proxy `/api/v1/simulation/*`) to start/step/stop scenarios.

## DER Bulk Import

| Aspect | Detail |
|---|---|
| Direction | Simulator → EMS |
| Endpoint | `POST /api/v1/der/bulk-import` |
| Auth | Machine token from Secrets Manager (`SIMULATOR_API_KEY`) |
| Payload | `{assets: [{id, type: "pv|bess|ev|microgrid", name, dtr_id, capacity_kw, lat, lon, metadata}]}` |
| Idempotency | `id` is primary key; upsert semantics |
| Called by | Simulator bootstrap on preset load |
| EMS action | Inserts/updates `der_asset`; emits `audit()` event |

## Scenario API Proxy

| Aspect | Detail |
|---|---|
| Direction | EMS → Simulator |
| EMS path | `/api/v1/simulation/:name/:action` (action ∈ start/step/stop/status) |
| Simulator path | `/scenarios/:name/:action` |
| Trace | EMS forwards traceparent |
| Response | Simulator returns step result as-is; EMS adds `ems_correlation_id` header |
| Sequences | `/api/v1/simulation/sequences/:name/start` and `/status` mirror simulator `/sequences/:name/*` |

## Command Passthrough (reverse direction for scenarios)

Smart-inverter and EV curtailment commands from EMS do NOT go direct to simulator. They go through HES routing → HES pull-backend → simulator TCP endpoint. Simulator MUST respond via Kafka `hesv2.command.status` and reflect in subsequent telemetry on `hesv2.der.telemetry`.

## Demo Preset Lock

- `demo-21-apr-2026` preset in simulator is the canonical demo topology.
- EMS test fixtures and Playwright selectors reference exact meter/DTR/feeder IDs from this preset.
- Preset frozen 2026-04-19 17:00 IST. Any change requires joint sign-off (EMS + Simulator + Ops).

## Environment Matrix

| Env | EMS SSOT_MODE | Simulator preset | Kafka cluster |
|---|---|---|---|
| Local dev (laptop) | disabled | small | docker-compose Kafka |
| dev EKS | strict | medium or demo-21-apr-2026 | dev-cluster Kafka (SASL/SCRAM) |
| Demo laptop (21 Apr) | strict with mirror fallback | demo-21-apr-2026 | dev-cluster Kafka |

## Failure Modes

- Simulator down mid-demo: EMS keeps showing last-known state with a "Simulator offline — showing last refresh at HH:MM:SS" banner; scenarios return 503.
- Kafka partition down: EMS consumer lag alert; degraded banner; polling fallback for critical KPIs only (configurable in `config.py`).
- DER bulk-import payload too large: simulator chunks into 100-asset batches.
