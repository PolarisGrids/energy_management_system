# Polaris EMS Frontend — Mock-Data Audit with MDMS Mapping

**Scope:** `frontend/src/pages/*.jsx` (26 files, ~10 961 lines)
**Date:** 2026-04-18 · **Branch:** `017-egsm-reports-postgres` (018 + Wave 1–4 merged)
**MDMS base (proxy):** `/api/v1/mdms/*` → `http://mdms-api.mdms-dev.svc.cluster.local:8000`
**Note:** The 29-page list in the ask is a miscount — only 26 pages exist. `Reconciler.jsx`, `AVControl.jsx→LPUPrepayment`, `SystemManagement.jsx` are not in the repo (Reconciler is stubbed via `reconcilerAPI` in `services/api.js:249`; LPU-Prepayment / SystemManagement are future-wave). Flagged in Section 6.

Legend — **Mock indicator** values: `HARDCODED_ARRAY` · `RANDOM` · `SEEDED_LOCAL_DB` · `PLACEHOLDER_STRING` · `STATIC_MARKETING` · `REAL`.

---

## Section 1 — Page-by-page inventory

### 1.1 Dashboard (`Dashboard.jsx`, 492 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Online / Offline / Tamper meter count | `useSSOTDashboard()` → HES `/network/health` + MDMS `/cis/hierarchy` | REAL | keep | `Dashboard.jsx:146` |
| Active Alarms KPI | `useSSOTDashboard().kpis.active_alarms` | REAL | keep | |
| Comm Success gauge | `kpis.comm_success_rate` (HES) | REAL | keep | |
| Transformers / Feeders | MDMS hierarchy count | REAL | keep | |
| Network Load 24h sparkline | `energyAPI.loadProfile(hours=24)` → local `MeterReading` | SEEDED_LOCAL_DB | `GET /api/v1/mdms/api/v1/analytics/load-profile?hours=24` | `Dashboard.jsx:173`; backend `energy.py:16` groups local `meter_reading` — must come from MDMS `profile_instant_vee` / `blockload_vee_validated` in prod |
| DER Asset Status (PV / BESS / EV) | `derAPI.list()` → local EMS DB | REAL | keep (EMS-owned assets) | |
| Live Alarm Feed | SSE `liveAlarms` from outlet context | REAL | keep | |
| Saved dashboard layouts | `dashboardsAPI.list()` | REAL | keep | W4.T11 |

### 1.2 GISMap (`GISMap.jsx`, 466 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Feeder GeoJSON | `gisAPI.layer('feeder')` → EMS PostGIS | REAL | keep (GIS is EMS-owned per spec 014) | |
| DTR / Meter layers | `gisAPI.layer('dtr'\|'meter')` | REAL | keep | |
| Alarm heatmap | `gisAPI.heatmapAlarms(bbox)` | REAL | keep | `:158` lazy fetch |
| NTL suspects overlay | `ntlAPI.suspectsGeoJson(bbox)` | REAL | keep | |
| Outage overlay | `outagesAPI.gisOverlay({bbox})` | REAL | keep | |
| DER markers | `derAPI.list()` | REAL | keep | |

No mock data. Context menu correctly navigates.

### 1.3 AlarmConsole (`AlarmConsole.jsx`, 157 lines) — P1
All rows from `alarmsAPI.list/active/acknowledge/resolve` — **REAL**. No mocks.

### 1.4 DERManagement (`DERManagement.jsx`, 968 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Asset list (PV/BESS/EV/microgrid) | `derAPI.list()` | REAL | keep (EMS-owned) | |
| EV per-port occupancy chart | `portData` built from `Math.floor(Math.random()*3)+1` | **RANDOM** | `GET /api/v1/der/{id}/telemetry?window=1h` + per-port breakdown | `DERManagement.jsx:559` — unused because `portSessions` shadows it but still renders |
| EV per-port sessions (fallback) | `const portSessions = [2, 1, 0, 3, 1, 0]` | **HARDCODED_ARRAY** | same as above | `:562` |
| EV cumulative energy curve | Synthesized from `totalEnergy` via polynomial fit | RANDOM (deterministic) | derive from MDMS load-profile or simulator telemetry | `:583–587` |

### 1.5 DERPv / DERBess / DEREv (`DERPv.jsx`, `DERBess.jsx`, `DEREv.jsx`) — P1
All three read `derAPI.telemetry({type, window})` → backend `der_telemetry.py`. The `EV fee rate = 8 R/kWh` is a hardcoded business constant (`DEREv.jsx:48`). Otherwise **REAL**.

| Page | Hardcoded constant | Fix |
|---|---|---|
| DEREv | `rPerKwh = 8` | Read from MDMS tariff schedule (`mdmsAPI.tariffs()` filtered by EV class) |
| SolarOvervoltageRunner | `DEFAULT_CURTAIL_PCT = 70`, `THRESHOLD_PU=1.08`, `TARGET_PU=1.02` | Scenario config; acceptable |
| EvFastChargingRunner | `DEFAULT_CURTAIL_PCT = 60`, `OVERLOAD_PCT=100` | Scenario config; acceptable |

### 1.6 DistributionRoom (`DistributionRoom.jsx`, 211 lines) — P2
`sensorsAPI.list()` + `metersAPI.transformers()` → REAL. No mocks. REQ-25.

### 1.7 EnergyMonitoring (`EnergyMonitoring.jsx`, 690 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Stacked area 24h load by class | `energyAPI.loadProfile()` | SEEDED_LOCAL_DB | `/api/v1/mdms/api/v1/analytics/load-profile?group_by=tariff_class&hours=24` | backend groups local `meter_reading` by `tariff_class`, prod requires MDMS |
| "Energy by Feeder" bar chart | `const feeders = [{'Feeder A', 1842}, ...]` | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/analytics/feeder-kwh?date=today` (derive from `blockload_vee_validated` GROUP BY feeder) | `EnergyMonitoring.jsx:118–124` — 5 feeders hard-coded |
| Import / Export / Net / PF KPIs | `summary.total_import_kwh ?? 8200` etc. | **HARDCODED_ARRAY** (fallback) | `/api/v1/mdms/api/v1/analytics/energy-summary?date=today` | `:146, :157–163` — fallback values 8200, 1150, 0.94 rendered whenever summary is null |
| Monthly last-6-months bar | `const monthlyData = [4820,5130,4970,5440,5080,5320]` | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/analytics/monthly-consumption?months=6&tariff_class=…` (from `monthlybilling_vee_validated`) | `:260` |
| "Consumption by class" pie | `[Residential 65, Commercial 25, Industrial 5, Prepaid 5]` | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/analytics/consumption-by-class?period=month` | `:293–298` |
| Daily 7-day table | `energyAPI.dailySummary()` → `EnergyDailySummary` | SEEDED_LOCAL_DB | `/api/v1/mdms/api/v1/analytics/daily-summary?days=7` | backend `energy.py:60`; real-in-dev, MDMS in prod |
| Filter dropdowns (Company / Dept / Branch / Class) | hard-coded options `['Polaris Grids', 'Eskom Dist', 'City Power']` etc. | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/cis/hierarchy?level=…` | `:310–313` + note "Filters are advisory — simulation data" (`:320`) |

### 1.8 Reports (`Reports.jsx`, 781 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| `FEEDERS` dropdown | `['All Feeders', 'F01 - Soweto Main', …]` | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/cis/hierarchy?level=feeder` | `:20` |
| `CUST_CLASSES` | `['Residential','Commercial',…]` | **HARDCODED_ARRAY** | `/api/v1/mdms/api/v1/cis/lookup/tariff-classes` (new) | `:21` |
| Consumption Reports rows | `reportsAPI.consumption()` → `EnergyDailySummary` | SEEDED_LOCAL_DB | `/api/v1/mdms/api/v1/analytics/consumption?from=…&to=…&feeder=…` | backend `reports.py:16`; real-in-dev, MDMS in prod |
| Meter-readings lookup | `reportsAPI.meterReadings()` → `MeterReading` | SEEDED_LOCAL_DB | `/api/v1/mdms/api/v1/readings?serial=…&days=14` | backend `reports.py:41` |
| Audit statements "Top consumers" | `reportsAPI.topConsumers()` | SEEDED_LOCAL_DB | `/api/v1/mdms/api/v1/analytics/top-consumers?limit=10&days=30` | backend `reports.py:81` |
| EGSM proxy tab | `egsmReportsAPI.run()` → MDMS | REAL | keep | W4.T9 |
| Scheduled reports | `scheduledReportsAPI` | REAL | keep | W4.T10 |

### 1.9 HESMirror (`HESMirror.jsx`, 658 lines) — P1

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Network health KPIs | `hesAPI.networkHealth()` via `/api/v1/hes/*` | REAL | HES SSOT | |
| DCU table | `hesAPI.dcus()` | REAL | keep | |
| Comm trend line | `hesAPI.commTrend()` | REAL | keep | |
| Meter inventory | `metersAPI.list()` → local EMS (spec comment: "EMS-owned roll-up") | REAL | keep | `:157–171` |
| Commands / Command history | `hesAPI.commands()` / `postCommand()` | REAL | keep | |
| FOTA jobs | `hesAPI.fota()` + placeholder schedule button | PLACEHOLDER_STRING | `GET /api/v1/hes/api/v1/firmware-upgrade` + POST when Wave 2 lands | `:445` comment "placeholder until spec 018 Wave 2 FOTA service lands" |
| FW distribution bar | `hesAPI.firmwareDistribution()` | REAL | keep | |

### 1.10 MDMSMirror (`MDMSMirror.jsx`, 413 lines) — P1
**Fully SSOT.** Every panel reads `mdmsAPI.*` with per-panel `UpstreamErrorPanel`. No mocks.

Only caveat: Analytics tab embeds a fixed error banner at `:303–309` saying "Power-quality compliance and tamper-analytics endpoints are not yet exposed by MDMS" — this is *documentation*, not mock data. Leave until MDMS `mdmsAPI.powerQuality()` (`services/api.js:187`) has a backing MV.

### 1.11 SensorMonitoring (`SensorMonitoring.jsx`, 562 lines) — P2
`sensorsAPI.list/byTransformer/history` — REAL. No mocks.

### 1.12 SimulationPage (`SimulationPage.jsx`, 314 lines) — P1
All data from `simulationAPI.*` → local `simulation_scenario` table. Scenarios are **EMS-owned** by design (demo driver). Labels like `REQ-21 · Solar Overvoltage` in `TYPE_LABEL` are static UI — `STATIC_MARKETING`, acceptable. No MDMS mapping required.

### 1.13 AuditLog (`AuditLog.jsx`, 347 lines) — P2

| Data point | Current source | Mock indicator | Correct MDMS source | Notes |
|---|---|---|---|---|
| Audit event list / summary | `auditAPI.events/summary` → local `AuditEvent` table | SEEDED_LOCAL_DB (EMS-owned log) | keep — EMS captures its own operator actions | `:67` |
| Default date range `'2026-04-02'` | **HARDCODED_ARRAY** | replace with `new Date().toISOString().slice(0,10)` (today) | `:51–52` — stale default |

### 1.14 SMOCShowcase (`SMOCShowcase.jsx`, 435 lines) — P3
100 % `STATIC_MARKETING`. Hardware specs, marketing copy. Leave as-is; it's the tender collateral page.

### 1.15 AVControl (`AVControl.jsx`, 589 lines) — P3
Control-room A/V surface (video wall, HVAC, lighting, Teams meetings). Contains:
- `MEETINGS`, `PARTICIPANTS`, `BLIND_ZONES`, `PRESET_LAYOUTS` — **HARDCODED_ARRAY** (`:8–30`)
- `(Math.random()-0.5)*0.2` temperature drift — **RANDOM** (`:129`)

Acceptable as a showcase page. Not MDMS-backed. If it were to become real, it would need a separate BMS / Crestron integration — out of scope.

### 1.16 AppBuilder (`AppBuilder.jsx`, 917 lines) — P2
`appBuilderAPI` → EMS `/apps`, `/app-rules`, `/algorithms`. **REAL.** Widget palette and dropdowns (`WIDGET_PALETTE`, `TRIGGERS`, `METRICS`, `OPERATORS`, `ACTIONS`, `PRIORITIES`) at `:22–38` are UI enums, not data — acceptable.

### 1.17 NTL (`NTL.jsx`, 286 lines) — P1
`ntlAPI.suspects / topGaps` → backed by `ntl.py` with MDMS fallback. REAL. Banner at `:107` when `scoring_available=false` is acceptance-scenario ② of US-9. No mocks.

### 1.18 OutageManagement (`OutageManagement.jsx`, 227 lines) — P1
`outagesAPI.list()` → REAL. No mocks.

### 1.19 OutageDetail (`OutageDetail.jsx`, 319 lines) — P1
`outagesAPI.get / acknowledge / addNote / dispatchCrew / flisrIsolate / flisrRestore` → REAL. Role gates are hard-coded (`:36–38`) — acceptable until RBAC lookup lands.

### 1.20 DataAccuracy (`DataAccuracy.jsx`, 236 lines) — P1
`api.get('/data-accuracy')` → REAL. Uses `Math.random()` only to generate toast IDs (`:49`) — cosmetic.

### 1.21 SolarOvervoltageRunner (`SolarOvervoltageRunner.jsx`, 350 lines) — P1
Simulator-driven (`simulationProxyAPI.scenarioStatus`, `derAPI.telemetry`). **Fallback voltage_pu at `:46`** synthesizes voltage from `achievement_rate_pct` when the simulator doesn't emit it — flagged as demo fallback. Acceptable for scenario runner; simulator should always emit.

### 1.22 EvFastChargingRunner (`EvFastChargingRunner.jsx`, 347 lines) — P1
Same pattern — simulator-driven + linear extrapolation forecast (`:53–58`). Forecast is derived from live telemetry, not mock.

### 1.23 Login (`Login.jsx`, 125 lines) — P1
`authAPI.login` — REAL. No mocks.

### 1.24 Placeholder (`Placeholder.jsx`, 13 lines) — P3
Empty placeholder component for routes without implementation.

---

## Section 2 — Missing backend proxies

All MDMS consumer endpoints currently reach MDMS via the catch-all `/api/v1/mdms/{path:path}` proxy (`mdms_proxy.py:21`), so no new proxy wiring is strictly required. However these **EMS-native endpoints** currently serve seeded local rows and should be updated to forward / aggregate from MDMS before production:

| EMS path | Current (seeded-local) | Proposed upstream MDMS path |
|---|---|---|
| `GET /api/v1/energy/load-profile` | `energy.py:16` groups local `meter_reading` | `/api/v1/analytics/load-profile` |
| `GET /api/v1/energy/daily-summary` | `energy.py:60` reads `energy_daily_summary` | `/api/v1/analytics/daily-summary` |
| `GET /api/v1/reports/consumption` | `reports.py:16` | `/api/v1/analytics/consumption` |
| `GET /api/v1/reports/meter-readings` | `reports.py:41` | `/api/v1/readings` (existing mdmsAPI.readings) |
| `GET /api/v1/reports/top-consumers` | `reports.py:81` | `/api/v1/analytics/top-consumers` |
| `GET /api/v1/reports/feeder-kwh` | **DOES NOT EXIST** | `/api/v1/analytics/feeder-kwh` |
| `GET /api/v1/reports/monthly-consumption` | **DOES NOT EXIST** | `/api/v1/analytics/monthly-consumption` |
| `GET /api/v1/reports/consumption-by-class` | **DOES NOT EXIST** | `/api/v1/analytics/consumption-by-class` |
| `GET /api/v1/cis/lookup/feeders` | hard-coded `FEEDERS` array | `/api/v1/cis/hierarchy?level=feeder` |
| `GET /api/v1/cis/lookup/tariff-classes` | hard-coded `CUST_CLASSES` | `/api/v1/cis/lookup/tariff-classes` (or derive from `/tariffs`) |

Five of these don't exist upstream either — `mdms-todos.md` already tracks feeder-loss / power-quality MVs (MDMS-T3/T4). This audit adds feeder-kwh, monthly-consumption, consumption-by-class as net-new MDMS asks.

---

## Section 3 — Consumption calculation gaps

Where the UI displays consumption/demand/TOU values MDMS may not return as a single tidy row, these derivations are required:

1. **Daily kWh delta per meter** — Reports → Meter Readings lookup. Compute: `max(reading) - min(reading)` per day per `meter_serial` from `blockload_vee_validated` (half-hourly) or `dailyload_vee_validated` (daily). Current EMS logic (`reports.py:66–77`) sums `energy_import_kwh` cumulatively — use `dailyload_vee_validated.total_import_kwh` directly.

2. **Top-consumer ranking (30d)** — EnergyMonitoring / Audit Statements. `SELECT meter_serial, SUM(total_import_kwh) FROM monthlybilling_vee_validated WHERE billing_month BETWEEN … ORDER BY 2 DESC LIMIT 10`. Join CIS `ConsumerMasterdata` for customer name.

3. **24h stacked load by tariff_class** — Dashboard + EnergyMonitoring. For each hour `h`: `SUM(demand_kw) FROM profile_instant_vee WHERE ts BETWEEN now-24h AND now GROUP BY hour(ts), tariff_class`. Join CIS for `tariff_class`.

4. **TOU split (off-peak / standard / peak)** — Reports → Billing tab. Read `monthlybilling_vee_validated.tod_kwh` (JSON with register-wise values per tariff slot). No EMS derivation needed — MDMS already has it.

5. **Feeder-level kWh rollup** — EnergyMonitoring bar chart. `SELECT feeder_id, SUM(total_import_kwh) FROM blockload_vee_validated JOIN consumer_masterdata USING(meter_serial) WHERE ts::date = :date GROUP BY feeder_id`. Must be an MV (current pure aggregation won't finish under demo latency targets).

6. **Net balance (import − export)** — EnergyMonitoring KPI. Both fields live on `monthlybilling_vee_validated` as `total_import_kwh` / `total_export_kwh` (reverse-register). Just subtract.

7. **Power factor weighted avg** — EnergyMonitoring KPI. `SUM(power_factor × demand_kw) / SUM(demand_kw)` from `profile_instant_vee` window — **NOT** a simple AVG.

8. **DTR energy balance gap %** — NTL page. `(feeder_input_kwh - SUM(downstream meter kWh)) / feeder_input_kwh * 100`. Already implemented server-side in `ntl.py`.

---

## Section 4 — Common filter controls

### Device search (meter serial / consumer account / account number / DTR / feeder)

Pages that **already have** search: HESMirror (`:201`, meter/customer), MDMSMirror (`:169`, account/name), Reports (`:229`, serial), DataAccuracy (`:117`, serial), NTL (`:124`, DTR id), EnergyMonitoring (`:528`, serial/customer), GISMap (context-menu driven).

Pages **missing** device search:
- **Dashboard** — needs hierarchy pick (division → feeder → DTR) to filter KPIs
- **AlarmConsole** — needs meter_serial / DTR filter beyond status+severity
- **DERManagement** — needs DTR filter for fleet view
- **OutageManagement** — has status filter only; needs DTR / feeder / date
- **AuditLog** — needs trace_id / resource search (search exists but `:198` is client-only)

### Date-range picker (today / 7d / 30d / custom from–to)

Pages with a date picker: Reports (`:67–68`, from/to), AuditLog (`:51–52`, from/to — default stale at `2026-04-02`), MDMSMirror (hard-coded to today).

Pages **missing** a date picker:
- Dashboard — shows "today" implicitly; add 24h/7d/30d toggle
- EnergyMonitoring — has Company/Dept filters but no date range
- AlarmConsole — no date range at all
- OutageManagement — would benefit from 7d/30d window
- NTL — should let operators choose 24h/7d windows for scoring

DER pages already have `WINDOWS=[1h,24h,7d]` — keep pattern.

---

## Section 5 — Priority ranking (demo-blocking)

Against the 24 SMOC demo points.

### P1 — demo-blocking (12 pages)

1. **EnergyMonitoring** — hardcoded feeder bar + monthly + pie + KPI fallback `?? 8200` is the most visible mock (`:146, :118–124, :260, :293–298`)
2. **Reports** — hardcoded FEEDERS + CUST_CLASSES dropdowns on every tab (`:20–21`)
3. **Dashboard** — energy sparkline still uses seeded local DB
4. **HESMirror** — FOTA schedule button is a placeholder (`:445`)
5. **MDMSMirror** — SSOT-clean ✓
6. **DERManagement** — EV per-port `Math.random()` + hardcoded fallback array (`:559, :562`)
7. **DERPv / DERBess / DEREv** — rate `R8/kWh` in DEREv (`:48`); otherwise clean
8. **GISMap** — clean
9. **AlarmConsole** — clean
10. **OutageManagement / OutageDetail** — clean
11. **NTL** — clean (fallback banner is a feature)
12. **DataAccuracy** — clean

### P2 — visible but tolerable (7 pages)

13. **SimulationPage** — EMS-owned, OK
14. **SensorMonitoring / DistributionRoom** — REAL
15. **AuditLog** — stale default date `2026-04-02`
16. **AppBuilder** — REAL
17. **SolarOvervoltageRunner / EvFastChargingRunner** — simulator-driven, fallback is intentional

### P3 — cosmetic (3 pages)

18. **SMOCShowcase** — marketing, keep
19. **AVControl** — showcase, keep
20. **Placeholder / Login** — trivial

---

## Section 6 — Notes on access / missing pages

- The instruction listed `Reconciler`, `LPUPrepayment`, `SystemManagement`, `DataAccuracy`, `NTL`, `OutageManagement`, `OutageDetail`, `SolarOvervoltageRunner`, `EvFastChargingRunner` as 29 items. **Reconciler**, **LPUPrepayment**, and **SystemManagement** do not exist in `frontend/src/pages/`; only a stub `reconcilerAPI` exists in `services/api.js:249` (IEC compliance spec 002). If they are planned for 018-compliance, they are pre-implementation and have zero mock data to audit.
- `AppBuilder.jsx` comment at `:5` notes: *"Replaces the earlier hardcoded prototype which held rules/apps/algorithms in component state only"* — confirming the old `INITIAL_RULES` / `SAMPLE_ALGORITHMS` constants have already been removed.
- All files were accessible; no read failures encountered.

---

## Quick-reference — Top 10 most severe findings

| # | File:line | Finding |
|---|---|---|
| 1 | `EnergyMonitoring.jsx:118–124` | `feeders` bar chart hardcoded to 5 feeders with fixed kWh |
| 2 | `EnergyMonitoring.jsx:146, :157–163` | KPI fallback values 8200 / 1150 / 0.94 |
| 3 | `EnergyMonitoring.jsx:260` | `monthlyData=[4820,5130,4970,5440,5080,5320]` |
| 4 | `EnergyMonitoring.jsx:293–298` | Customer-class pie 65/25/5/5 hardcoded |
| 5 | `EnergyMonitoring.jsx:310–320` | Filter options + "advisory — simulation data" label |
| 6 | `Reports.jsx:20–21` | `FEEDERS` + `CUST_CLASSES` hardcoded everywhere |
| 7 | `DERManagement.jsx:559, :562` | EV per-port `Math.random()` + fallback `[2,1,0,3,1,0]` |
| 8 | `DEREv.jsx:48` | `const rPerKwh = 8` hardcoded tariff rate |
| 9 | `AuditLog.jsx:51–52` | Default date range stuck on `'2026-04-02'` |
| 10 | `HESMirror.jsx:445` | FOTA schedule is a placeholder action |
