# Polaris EMS — Features

Polaris EMS is the Smart Metering Operations Centre (SMOC) control plane for Eskom tender **E2136DXLP**, covering the 27 demo evaluation items. Frontend is a React 19 + Vite SPA; backend is FastAPI + PostgreSQL.

Demo target: ≥85% score (113 of 133 pts); aspirational 90% (120 pts). Demo date: **21 April 2026, Megawatt Park, Johannesburg**.

## Application Pages

All routes live under `frontend/src/pages/`.

| Page | Route | What it does |
|---|---|---|
| Login | `/login` | JWT auth against `/api/v1/auth/login` |
| Dashboard | `/dashboard` | Single-pane ops view: fleet KPIs, live alarms, DER status, comm health |
| GIS Map | `/map` | Leaflet map of feeders, transformers, meters, DER, active events |
| Alarm Console | `/alarms` | Real-time alarm stream (SSE) with ack/resolve actions + filters |
| DER Management | `/der` | PV / BESS / EV / microgrid control (curtail, connect, set-power) |
| Energy Monitoring | `/energy` | Load profile (24h) + daily summary + meter status |
| Reports | `/reports` | Consumption, top consumers, meter-readings with download hooks |
| HES Mirror | `/hes` | DCU inventory, command log, FOTA jobs, firmware distribution, comm trend |
| MDMS Mirror | `/mdms` | VEE summary/exceptions, consumer master, TOU tariffs, NTL suspects, PQ zones |
| Sensor Monitoring | `/sensors` | Transformer sensors with live values + threshold editor + 24h history |
| Simulation | `/simulation` | Scripted DER / fault scenarios with step-through + command injection |
| Audit Log | `/audit` | Filterable operator action log |
| SMOC Showcase | `/showcase` | REQ-1 / REQ-2 scripted demo scenes |
| Reconciler | `/reconciler` | Compliance + feature-completion matrix (IEC standards) |
| AV Control | `/av-control` | Simulated control-room A/V + environmental automation |
| App Builder | `/appbuilder` | No-code (L3): rule engine + algorithm editor |

## Feature Domains

### 1. Real-time Network Operations
- Server-Sent Events feed (`/api/v1/events/stream`) — alarms, sim ticks, heartbeat every 15s
- Alarm model supports 14 types (TAMPER, OUTAGE, OVERVOLTAGE, NTS_DETECTED, REVERSE_POWER, …) and 5 severities
- Ack / resolve workflow with operator attribution written to `audit_events`

### 2. AMI / HES Integration
- Mirrored HES state (DCUs, command log, FOTA jobs, firmware distribution, comm trend)
- Remote connect / disconnect of meters via `/meters/{serial}/connect|disconnect`
- Live hook path: `services/hes_client.py` to HES routing-service REST + Kafka

### 3. MDMS Integration
- VEE daily summary + exceptions queue with approve/reject flow
- Consumer master browser with search + tariff schedule viewer
- NTL suspects with risk score ranking (Red/Amber/Green flags)
- Power-quality zone dashboard (voltage deviation, THD, flicker, compliance)

### 4. DER Management
- PV, BESS, EV charger, microgrid, wind asset types
- Per-asset telemetry (SoC for BESS, active sessions for EV, islanded flag for microgrid, reverse-power-flow detection)
- Command surface: `curtail`, `connect`, `disconnect`, `set_power`
- Revenue + generation-achievement tracking per asset per day

### 5. Transformer Asset Monitoring
- Sensor inventory: winding temp, oil temp, oil level, vibration, humidity, per-phase currents
- NORMAL / WARNING / CRITICAL / OFFLINE status based on editable thresholds
- 24h simulated history with realistic diurnal pattern for demo

### 6. Simulation Engine
Scripted scenarios executed by `services/simulation_engine.py`:
- **SOLAR_OVERVOLTAGE** — PV oversupply lifting feeder voltage
- **EV_FAST_CHARGING** — Transformer overload from EV hub
- **PEAKING_MICROGRID** — Microgrid islanding during peak
- **NETWORK_FAULT** — Fault location + isolation + restoration
- **SENSOR_ASSET** — Transformer sensor anomaly cascade

Each scenario runs step-wise; each step ships `network_state`, `alarms_triggered`, and `commands_available` to the UI.

### 7. Energy & Reporting
- 24h load profile split by tariff class (residential / commercial / prepaid)
- Daily network summary (import, export, net, peak demand, PF)
- Consumption, meter-reading, and top-consumer reports

### 8. Audit & Compliance
- Every command / ack / threshold change / login recorded to `audit_events`
- Reconciler page surfaces IEC standard compliance findings + feature completion matrix

### 9. No-Code App Builder (L3)
- Rule engine + algorithm editor for field-technician workflows
- Lives on `/appbuilder`; persisted model TBD (currently in-memory)

### 10. MS Teams Integration
- Operator alert push via `/teams/alert`
- Config surfaced via `/teams/config` (client_id, tenant_id, enabled)

## Frontend Stack

| Concern | Choice |
|---|---|
| Framework | React 19 |
| Build | Vite 8 |
| Styling | Tailwind CSS 4 |
| State | Zustand 5 (`stores/authStore.js`) |
| Routing | React Router DOM 7 |
| HTTP | Axios 1.x — `services/api.js` |
| Charts | Apache ECharts 6 + `echarts-for-react` |
| Maps | Leaflet 1.9 + `react-leaflet` 5 |
| Icons | `lucide-react` |

## Non-Goals (v1)

- No Alembic-managed schema migrations — seed script handles baseline
- No multi-tenant / multi-region support
- No SSO / SAML — local JWT only
- App Builder output does not yet persist or compile; UI scaffold only
