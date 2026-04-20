# Feature Specification: SMOC/EMS Full AMI Compliance — Eskom Demo + Production

**Feature Branch**: `018-smoc-ems-full-compliance`
**Created**: 2026-04-18
**Status**: Draft
**Input**: Eskom Tender E2136DXLP demo points #4 through #27 (24 capabilities). Deliver a full-fledged production-grade EMS (not demo-prep only). Polaris EMS MUST read from MDMS as the single source of truth for all metering, billing, VEE, tariff, consumer, NTL, and report data. HES is the single source of truth for meter commands, comm health, DCU status, and raw events. All gaps currently in polaris_ems (see `docs/GAPS.md`) MUST be closed. Cross-system E2E integration test is the acceptance bar.

---

## Context & Ground Truth

- Current state captured in `docs/GAPS.md` (dated 2026-04-18) and `docs/ROADMAP.md`.
- Demo freeze on `avdhaan_v2` and `mdms-reports` since 2026-04-12. MDMS repo changes require Umesh approval (see `/home/ubuntu/.claude/.../feedback_mdms_umesh_approval.md`). All MDMS-side changes required by this spec are collected in `mdms-todos.md` for separate sign-off — this EMS spec does NOT assume them merged, and uses feature-flagged fallbacks until they land.
- Simulator changes are captured in a sibling spec: `repos/simulator/specs/001-ami-full-data-generation/spec.md`.
- Branch policy: work on `eskom_dev` for merges; this spec lives on feature branch `018-smoc-ems-full-compliance`.

## Data-Consistency Contract (load-bearing for the whole spec)

Every demo capability binds to exactly one upstream source-of-truth. EMS MUST NOT serve metering/billing/VEE/tariff/CIS data from its own seeded DB in production mode.

| Domain | System of Record | EMS Consumption Pattern |
|---|---|---|
| Meter commands (RC/DC, FOTA, read, timesync) | HES | `POST /hes/commands/*` via `hes_client`; command lifecycle via Kafka topic `hesv2.command.status` |
| Meter events / alarms (raw) | HES | Kafka consume `hesv2.meter.events`, `hesv2.meter.alarms`; persist in EMS `alarm_events` with `source_trace_id` |
| DCU status, comm health, RSSI, retry | HES | `GET /hes/dcus`, `GET /hes/comm-health`; poll 30 s; cache in EMS `dcu_health_cache` |
| Firmware distribution, FOTA progress | HES | `GET /hes/firmware-distribution`, `GET /hes/fota/:jobId`; SSE push on change |
| Interval readings (block load, daily, monthly) | MDMS (VEE-validated) | `GET /mdms/readings?meter=&from=&to=` (via `mdms-api` gateway); backed by `blockload_vee_validated`, `dailyload_vee_validated`, `monthlybilling_vee_validated` |
| Consumer master / hierarchy / CIS | MDMS (`mdms-cis-service`) | `GET /mdms/cis/consumers`, `GET /mdms/cis/hierarchy`; no EMS-side consumer table |
| Tariff schedules (TOU, CPP, inclining-block, seasonal, demand) | MDMS (`mdms-billing-engine`) | `GET /mdms/tariffs`; tariff application results via `GET /mdms/billing-determinants` |
| VEE summary / exceptions / rules | MDMS (`mdms_vee_service`) | `GET /mdms/vee/summary`, `/mdms/vee/exceptions`, `/mdms/vee/rules` |
| NTL analytics (suspicion scores, energy balance) | MDMS (`mdms-ntl-service` — see MDMS TODO) | `GET /mdms/ntl/suspects`, `/mdms/ntl/energy-balance`; EMS supplements with event correlation locally |
| EGSM Reports (6 categories, ~52 endpoints) | MDMS (`mdms-reports` + `mdms-analytics-service` MVs) | `GET /mdms/reports/*` proxied through EMS API gateway |
| Prepaid registers, credit balance, token log, ACD | MDMS (`mdms-cis-service` + `mdms-prepaid-engine`) | `GET /mdms/prepaid/*`; recharge via `POST /mdms/prepaid/recharge` |
| GIS topology (substation → PSS → feeder → DTR → pole → meter) | MDMS PostGIS (phase-b/014 — landed) | `GET /mdms/gis/layers?bbox=` (GeoJSON) |
| DER assets (PV, BESS, EV, microgrid) | EMS-native (no upstream) | EMS owns `der_asset`, `der_command`, `der_telemetry` |
| Sensor data (transformer temp, oil, current, smoke, water) | HES via DCU passthrough; EMS persists history | Kafka `hesv2.sensor.readings` → EMS `transformer_sensor_readings` |
| Outage incidents | EMS (correlates HES events + MDMS outage model) | EMS owns `outage_incident`, `outage_timeline`; reads upstream signals |
| Audit trail (user actions) | EMS → Kafka `mdms.audit.actions` → MDMS `db_cis.action_audit_log` | EMS publishes via `otel-common-py.audit()` |

**Rule of least surprise**: the EMS API gateway MUST expose a single `/api/v1/mdms/*` and `/api/v1/hes/*` namespace that proxies upstream. Existing mirror pages become thin views over proxied responses. Feature flag `SSOT_MODE=strict|mirror|disabled`:
- `strict` (production target) — upstream call or error; no seeded fallback
- `mirror` (demo fallback) — upstream call, fall back to seeded-in-EMS if upstream unavailable, with banner "Showing cached MDMS snapshot"
- `disabled` (offline dev) — seeded only

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Real-Time LV Network Operational Dashboard (Demo #4) (Priority: P1)

An operator arrives at the SMOC console and sees a live "single pane of glass" showing active meters, feeder loading, transformer health, DCU communication status, and top alarms. Every KPI tile refreshes via SSE as upstream events flow from HES and MDMS; no tile shows `—` or a hardcoded fallback in production mode.

**Why this priority**: This is the operator's primary surface. Fails item #4, #11, #19, #26 if missing or stale.

**Independent Test**: With simulator feeding HES, disconnect 10 meters. Dashboard "Offline Meters" KPI MUST tick up within 30 s. Kill MDMS API. Dashboard MUST show an explicit "MDMS unavailable" banner, not a silent fallback to 0.

**Acceptance Scenarios**:

1. **Given** SSOT_MODE=strict and MDMS online, **When** operator opens `/dashboard`, **Then** all six KPI tiles (online meters, offline meters, active alarms, feeder load %, DTR load %, DCU comm success %) show upstream-sourced numbers with source timestamp ≤ 60 s old.
2. **Given** SSOT_MODE=strict and MDMS returns 503, **When** operator opens `/dashboard`, **Then** KPIs render a red "MDMS unavailable — last refresh at HH:MM:SS" banner and NO hardcoded fallback number is shown.
3. **Given** a live HES event stream, **When** meters trip to OFFLINE, **Then** dashboard "Offline Meters" KPI increments within 30 s via SSE, not via polling.
4. **Given** operator clicks any KPI tile, **When** detail view opens, **Then** drill-down is a real query against MDMS/HES, not a static filter of EMS-cached rows.

---

### User Story 2 — Meter Commands: RC/DC, On-Demand Read, Timesync (Demo #4, #5) (Priority: P1)

Operator selects a meter, clicks "Disconnect". Command flows EMS → HES → meter; lifecycle tracked (QUEUED → SENT → ACK → EXECUTED → CONFIRMED). Relay-state returns from meter via HES push; EMS updates meter row and shows toast. Batch disconnect of 100 meters works in parallel with backpressure.

**Why this priority**: Demo item #5 core; #4 automation; #7 prepaid disconnect. Without live HES call, demo is fabricated.

**Independent Test**: Issue RC and DC on a seeded simulator meter; assert HES `hesv2.command.status` Kafka messages at each state; assert EMS meter row `relay_state` and `last_command_id` updated from the CONFIRMED event — not from the outbound request.

**Acceptance Scenarios**:

1. **Given** SSOT_MODE=strict and meter online, **When** operator clicks Disconnect on meter S123, **Then** EMS publishes a command to `mdms-cmd-exec-service` which forwards to HES; EMS stores `command_id`, awaits status via Kafka.
2. **Given** HES responds EXECUTED on Kafka, **When** the Kafka consumer processes it, **Then** EMS updates meter `relay_state=OPEN`, `last_command_status=EXECUTED`, and emits an `audit()` event.
3. **Given** HES does not respond within 60 s, **When** timeout fires, **Then** command status becomes TIMEOUT, operator sees a red toast, and a retry button appears.
4. **Given** 100 meters selected, **When** operator clicks Batch Disconnect, **Then** commands enqueue at max-concurrency=10, and a progress drawer shows live tally.
5. **Given** command is an On-Demand Read (billing register), **When** HES returns the register value, **Then** EMS persists it in `ad_hoc_read` table AND MDMS `command_execution_log` receives the same payload (verified via MDMS audit trail).

---

### User Story 3 — FOTA Firmware Distribution with Progress & Rollback (Demo #5) (Priority: P1)

Operator uploads a firmware image, selects a batch of meters or a DCU, triggers the upgrade. EMS dispatches via HES RF firmware service; progress tracked per meter (QUEUED → DOWNLOADING → VERIFYING → APPLIED → ACTIVATED), with failed meters eligible for retry or rollback.

**Why this priority**: Demo item #5 explicit. Required for the "automation" narrative.

**Independent Test**: Upload a firmware blob, target 20 simulator meters, observe FOTA progress table update in real time; kill 3 meters mid-download and verify they show FAILED with retry option.

**Acceptance Scenarios**:

1. **Given** a firmware file < 10 MB and target batch, **When** operator clicks Start, **Then** EMS creates `fota_job`, calls HES `POST /firmware-upgrade`, receives job_id, persists.
2. **Given** FOTA job in progress, **When** operator opens job detail, **Then** per-meter progress (%, state, last-error) is polled at 15 s and rendered in a sortable table.
3. **Given** a meter fails download 3× in a row, **When** retry policy triggers, **Then** EMS marks meter-job FAILED and emits an alarm event.
4. **Given** a job completes, **When** operator clicks Rollback on 5 meters, **Then** HES rollback command is dispatched and lifecycle tracked identically.

---

### User Story 4 — Outage Intelligence with GIS Pinpointing (Demo #4, #7, #24) (Priority: P1)

Multiple meters report power-failure events; EMS correlates them within a configurable time window (default 120 s) and a topology-aware scope (same DTR / feeder). An outage incident is created automatically with suspected fault location on the GIS map, affected-customer count, and an incident timeline (detected → investigating → crew dispatched → restored).

**Why this priority**: Demo items #4, #7, #24 all hang on this. Also the centre of the "intelligent layer" pitch.

**Independent Test**: Simulator fires 20 power-failure events on meters under DTR `DTR-001` within 60 s. EMS MUST auto-open an outage incident with affected_count=20, map marker on DTR-001 pole, and trigger a notification to the on-call operator.

**Acceptance Scenarios**:

1. **Given** ≥ N (config=3) meters under the same DTR report `power_failure` within window, **When** correlation runs, **Then** a new `outage_incident` row is created with status=DETECTED and GIS geometry pointing to the DTR.
2. **Given** an open outage, **When** restoration events come back (`power_restored`), **Then** the incident timeline advances to RESTORED when all affected meters are back online.
3. **Given** an open outage shown on `/map`, **When** operator right-clicks the incident marker, **Then** context menu offers "Dispatch crew" (WFM hook — creates WO in MDMS WFM), "Send broadcast" (notifications), "Mark investigated".
4. **Given** SAIDI/SAIFI query, **When** operator opens the Reliability Indices report, **Then** indices are computed from `outage_incident` + affected-meter hours, matching the MDMS `reliability_indices` materialised view ±1%.

---

### User Story 5 — VEE Pipeline Surfaced from MDMS (Demo #6) (Priority: P1)

Operator opens `/mdms` → VEE tab and sees today's validation summary sourced from MDMS: reads ingested, reads passed, reads failed (by rule), reads estimated (by method), reads manually edited. Clicking a rule opens an exceptions list with meter, timestamp, rule name, original value, validated/estimated value. No divide-by-zero `NaN%` allowed.

**Why this priority**: Demo item #6 core. Current `MDMSMirror.jsx` shows `NaN%` — P1 finding in GAPS.md.

**Independent Test**: Seed 1000 reads in MDMS VEE with 100 failures across 5 rules and 50 estimated. VEE tab MUST show 90% pass rate, 5% estimated, 5% failed, with per-rule breakdown matching MDMS DB counts.

**Acceptance Scenarios**:

1. **Given** MDMS VEE has data for today, **When** operator opens VEE tab, **Then** totals and percentages render (no `NaN%`), matching a direct query against `blockload_vee_validated` within ±1%.
2. **Given** MDMS VEE has zero data today, **When** operator opens VEE tab, **Then** the empty state displays "No VEE activity in selected window" — not `NaN%`.
3. **Given** operator clicks a rule row, **When** exceptions page opens, **Then** a paginated list of exception rows from MDMS is shown with meter link → meter detail page.
4. **Given** operator manually edits a reading via the Edit modal, **When** they submit, **Then** EMS forwards to MDMS `POST /mdms/vee/edit` and the audit trail captures user_id + old/new values.

---

### User Story 6 — Tariff Engine Results & Configuration View (Demo #6) (Priority: P2)

Operator can view MDMS tariff schedules (TOU, CPP, demand, seasonal, inclining-block) and for a selected meter + billing month see the applied tariff, ToU buckets, demand charge, inclining-block tier step-up, and seasonal multiplier. Demonstrates MDMS as the rate engine authority.

**Independent Test**: Pick a meter with 3 billing months of data; open Tariff Explorer; verify the applied rate per month matches MDMS `billing_determinants` table and shows the right seasonal multiplier.

**Acceptance Scenarios**:

1. **Given** tariff schedules exist in MDMS, **When** operator opens `/mdms/tariffs`, **Then** schedules render in a table with effective-date range, ToU TZ1–TZ8 rates, CPP events, demand charge, inclining-block tiers, seasonal factor.
2. **Given** a meter + month, **When** operator opens Billing Determinants detail, **Then** ToU consumption per register, applied demand charge, and computed invoice value render — and match the MDMS-returned payload byte-for-byte.
3. **Given** inclining-block tariff with 3 tiers, **When** consumption crosses tier threshold, **Then** per-tier kWh × rate is shown and total matches MDMS.

*(Inclining-block / seasonal support requires MDMS change — see `mdms-todos.md` item MDMS-T1; spec rendering of gaps handled by showing "Not supported by tariff" for those fields.)*

---

### User Story 7 — CIS/GIS Data Enrichment per Meter (Demo #6) (Priority: P2)

Operator searches for a meter; detail page shows consumer name, account, tariff class, premise address, substation → PSS → feeder → DTR → pole chain with coordinates, phase, transformer nameplate. All sourced from MDMS-CIS + MDMS-GIS (PostGIS from phase-b/014), not EMS-seeded.

**Independent Test**: Search meter `S123`; compare detail page to `mdms-cis-service` DB record and PostGIS geometry; assert identical.

**Acceptance Scenarios**:

1. **Given** a meter serial, **When** operator searches, **Then** detail page renders consumer, hierarchy, coordinates, tariff class from MDMS.
2. **Given** hierarchy elements, **When** operator clicks DTR, **Then** the DTR page opens with downstream meters, nameplate kVA, measured loading %, voltage profile.
3. **Given** MDMS GIS returns a geometry, **When** detail page loads, **Then** a mini-map renders the meter location within 500 ms.

---

### User Story 8 — Load Profiles by Customer Class (Demo #6, #9) (Priority: P2)

Analyst selects a customer class (residential / commercial / industrial / LPU / EV-owner / solar-prosumer) and date range; MDMS returns aggregated half-hourly load curves; EMS renders overlay chart with anomaly bands (p10/p50/p90) and export (CSV/PDF).

**Independent Test**: Pick residential, April 1–7, 2026; compare chart points to MDMS `load_profile_by_class` MV rows; export CSV and verify byte match.

**Acceptance Scenarios**:

1. **Given** date range + class, **When** operator loads the page, **Then** half-hourly load curve renders with p10/p50/p90 bands.
2. **Given** chart rendered, **When** operator clicks export CSV, **Then** the download matches the underlying MDMS payload (within rounding).

---

### User Story 9 — NTL Detection Dashboard (Demo #4, #6) (Priority: P2)

Operator opens `/ntl`; dashboard shows flagged meters with suspicion score, top event-flag correlations, energy-balance gap per DTR (feeder input vs. sum of downstream meters), and map overlay of NTL suspects.

**Why this priority**: P2 because MDMS NTL service is currently empty stub (see MDMS-T2). EMS side builds the surface and event-correlation fallback; scoring comes from MDMS when available.

**Independent Test**: Inject theft on 5 simulator meters (magnet tamper, reverse energy, CT bypass); within 15 min the NTL dashboard MUST show them with a score > 0 and the event-flag cause.

**Acceptance Scenarios**:

1. **Given** MDMS NTL service online (feature-flag `MDMS_NTL_ENABLED=true`), **When** operator opens NTL dashboard, **Then** ranked suspect list from MDMS renders with score, last event, DTR.
2. **Given** MDMS NTL disabled, **When** operator opens NTL dashboard, **Then** EMS local event-correlation view renders with a banner "Using event correlation only — scoring unavailable".
3. **Given** energy-balance query, **When** operator picks a DTR, **Then** feeder-input kWh vs downstream-sum kWh is shown, with gap % highlighted.

---

### User Story 10 — Prepaid Operations Panel (Demo #7) (Priority: P1)

Operator opens a consumer account and sees current credit balance, last recharge, pending tokens, ACD status, kWh/currency mode. Can trigger recharge (generates token via STS, dispatches to HES, gets register read-back within 60 s). All data sourced from MDMS prepaid + CIS.

**Why this priority**: Demo item #7. Current `project_prepaid_register_readback_gap.md` memo says readback missing — EMS covers by polling or subscribing.

**Independent Test**: Recharge R100 on a prepaid simulator meter; within 60 s EMS shows updated credit balance reflecting the token, sourced from MDMS prepaid registers.

**Acceptance Scenarios**:

1. **Given** a prepaid account, **When** operator opens the account page, **Then** 13 prepaid registers from MDMS render with freshness ≤ 60 s.
2. **Given** a recharge, **When** dispatched and accepted, **Then** EMS polls `/mdms/prepaid/registers?account=` every 15 s for 2 min and updates the page; MDMS-T4 (auto-readback) closes this gap on MDMS side.
3. **Given** ACD threshold crossed, **When** meter balance hits 0, **Then** MDMS disconnects and the EMS page shows ACD=ACTIVE, RELAY=OPEN; operator sees a red banner.

---

### User Story 11 — Alert Rules, Virtual Object Groups, Subscriptions (Demo #10) (Priority: P2)

User defines a "virtual object group" (e.g., all feeders in Soweto South), creates an alarm rule (e.g., "any DTR loading > 90% for 10 min"), subscribes with priority + channel (SMS, email, app-push, Teams). Notifications fire on match.

**Independent Test**: Create a rule "DTR load > 80%"; drive one DTR above; verify SMS+email+push delivered within 60 s (stubbed providers OK for unit test, real for E2E).

**Acceptance Scenarios**:

1. **Given** a virtual group and rule, **When** the rule condition fires, **Then** subscribers receive a notification via each configured channel within 60 s.
2. **Given** quiet-hours configured, **When** a P3 alarm fires during quiet hours, **Then** SMS/Push are suppressed; email queues until morning.
3. **Given** an alarm escalation rule, **When** the first tier does not ack within 5 min, **Then** escalates to tier 2.

---

### User Story 12 — Data Quality & Source Accuracy Console (Demo #11) (Priority: P2)

For every meter, show last-collection-time from HES, last-validated-read-time from MDMS, last-billing-read-time from CIS. Flag meters missing from any system and show side-by-side source status.

**Independent Test**: Take 10 meters offline for 2 hours; console MUST flag them under "HES delay > 1h" with timestamps sourced from each system, not EMS.

**Acceptance Scenarios**:

1. **Given** three source timestamps, **When** operator opens Data Accuracy tab, **Then** each meter row shows HES last-read, MDMS last-validated, CIS last-billing, with delta and "healthy/lagging/missing" badge.
2. **Given** a meter missing from MDMS, **When** rendered, **Then** badge is "missing in MDMS" and row links to raise a reconciliation task.

---

### User Story 13 — System Management: Supplier & Product Registry (Demo #12) (Priority: P3)

Admin maintains supplier registry, meter model catalog, firmware baseline per model, and sees per-supplier performance metrics (failure rate, avg install-to-first-read time, MTBF). Backed by MDMS `supplier_registry` + EMS `supplier_performance_mv`.

**Acceptance Scenarios**:

1. **Given** suppliers exist, **When** admin opens System Management, **Then** list shows each supplier with number-of-meters, failure-rate %, MTBF.
2. **Given** operator imports a CSV of new meters, **When** upload succeeds, **Then** each meter is bound to supplier + model and visible in registry.

---

### User Story 14 — Audit Statements & Consumption Queries (Demo #13, #14) (Priority: P2)

Business user queries energy consumption centrally (daily, weekly, monthly) for any meter, DTR, feeder, or customer class; includes purchase (input), sales (billed), loss. Sourced from MDMS EGSM reports.

**Acceptance Scenarios**:

1. **Given** selection filters, **When** operator clicks Run, **Then** MDMS `/egsm-reports/energy-audit/*` returns matching rows and the table + chart render.
2. **Given** large result set, **When** operator clicks Export, **Then** MDMS CSV pipeline (S3+SQS) generates, EMS polls download-log, and download appears in notifications.

---

### User Story 15 — DER Native Dashboards: PV, BESS, EV, Distribution (Demo #15, #16, #17, #18) (Priority: P1)

EMS owns DER data. Four dashboards: PV (generation curve, inverter online, achievement rate, equivalent hours); BESS (SoC%, cycles, revenue, charge/discharge profile); EV (pile status, session log, fees, energy delivered); Distribution room (temp, humidity, smoke, water, access door). Each has live telemetry via Kafka `hesv2.sensor.readings`.

**Independent Test**: Simulator drives 6 PV sites through a sunny day curve; PV dashboard MUST show aggregate generation matching simulator ±2%.

**Acceptance Scenarios**:

1. **Given** PV assets with live telemetry, **When** operator opens `/der/pv`, **Then** per-asset cards + aggregate curve render; inverter online status within 30 s of change.
2. **Given** BESS asset, **When** operator opens `/der/bess`, **Then** SoC %, cycles, today's charge/discharge kWh, revenue render; charge/discharge profile chart for last 24 h.
3. **Given** EV charging stations, **When** operator opens `/der/ev`, **Then** per-pile status, active sessions, energy delivered, fees render; fast-charging stations flagged.
4. **Given** distribution room sensors, **When** operator opens `/distribution`, **Then** temp, humidity, smoke, water-immersion, door-access statuses render; any alarm triggers notifications (User Story 11).

---

### User Story 16 — DER Situational Awareness on Feeders (Demo #20) (Priority: P1)

Operator opens a feeder; the feeder dashboard overlays DER contribution (PV export, EV draw, BESS charge/discharge) onto feeder voltage and current profile; a stacked-area chart shows net flow over 24 h.

**Independent Test**: With PV export driving the feeder above nominal voltage, the feeder page MUST display voltage above 1.05 pu AND DER-contribution band highlighted with a callout.

**Acceptance Scenarios**:

1. **Given** a feeder with DER assets, **When** operator opens feeder page, **Then** voltage profile along feeder + DER contribution overlay render.
2. **Given** reverse flow, **When** net kW < 0 for 5 min, **Then** a "Reverse flow detected" banner appears and a reverse-flow event is persisted.

---

### User Story 17 — Scenario: Solar Over-Voltage with Smart Inverter Curtailment (Demo #21) (Priority: P1)

Operator runs the `solar_overvoltage` scenario; feeder voltage climbs above 1.08 pu; EMS detects and calculates per-inverter curtailment setpoint using the documented algorithm (droop curve, 70% default); dispatches command to each smart inverter via HES; voltage returns to 1.02 pu.

**Independent Test**: Start scenario; within 7 steps, voltage stabilises ≤ 1.05 pu; each inverter receives a `curtail` command visible in HES command log.

**Acceptance Scenarios**:

1. **Given** scenario running, **When** over-voltage threshold crossed, **Then** EMS calculates curtailment %, dispatches to HES, shows algorithm panel with live inputs.
2. **Given** curtailment applied, **When** step advances, **Then** voltage trends down on the chart; algorithm explanation panel stays visible for demo narration.
3. **Given** operator acknowledges and resolves, **When** final step runs, **Then** curtailment is released, inverters return to normal.

*(Live command dispatch to inverter requires HES inverter-command endpoint; sim for demo; flagged for production in MDMS-T5.)*

---

### User Story 18 — Scenario: EV Fast-Charging Transformer Impact & Curtailment (Demo #22) (Priority: P1)

Scenario ramps EV fast-charger load on a DTR; DTR loading % crosses 100%; EMS shows forecast (next-hour load projection), displays overload alarm, dispatches a curtailment command to the charger; load decreases; forecast chart updates.

**Independent Test**: Run `ev_fast_charging`; assert overload alarm fires; curtailment reduces load ≥ 20%; forecast chart refreshes every step.

**Acceptance Scenarios**:

1. **Given** scenario running, **When** DTR loading > 100%, **Then** alarm and a forecast-vs-actual chart render.
2. **Given** operator clicks "Curtail", **When** command dispatched, **Then** charger power setpoint drops, transformer loading drops within 3 steps.
3. **Given** charging session active, **When** operator views station detail, **Then** load profile + currents per phase render.

---

### User Story 19 — Scenario: Microgrid Reverse Flow & DER Aggregation (Demo #23) (Priority: P1)

Scenario runs a peaking microgrid (PV + BESS + EV) coming online; reverse-power-flow detected on a feeder; EMS handles individual-asset + aggregate view; one DER added mid-scenario (either PV/EV/BESS) is integrated without restart.

**Independent Test**: Run `peaking_microgrid`; at step 3 add a BESS asset; verify aggregate view includes it from step 4 onward.

**Acceptance Scenarios**:

1. **Given** scenario at step 1, **When** PV + BESS + EV output ramps, **Then** aggregated kW chart renders per asset and totals.
2. **Given** reverse flow detected, **When** operator opens feeder, **Then** reverse-flow banner and direction arrow render.
3. **Given** new DER added, **When** step advances, **Then** aggregate updates to include new asset.

---

### User Story 20 — Scenario: Fault + FLISR + AMI Outage Correlation (Demo #24) (Priority: P1)

Scenario injects a fault between two meters; EMS receives outage events from AMI (User Story 4 correlation), shows fault location on map with confidence %, offers FLISR steps: identify fault → isolate section → restore adjacent; operator executes each; affected-meter count decreases.

**Independent Test**: Run `network_fault`; verify outage incident auto-opens within 90 s, FLISR recommends isolation switch, on operator approval loading redistributes.

**Acceptance Scenarios**:

1. **Given** fault injected, **When** correlation runs, **Then** outage incident opens with suspected fault span and confidence.
2. **Given** operator clicks "Isolate section", **When** command dispatched, **Then** adjacent sections re-energise and affected-meter count drops; timeline updates.
3. **Given** all affected restored, **When** incident closed, **Then** SAIDI/SAIFI/CAIDI update for the period.

---

### User Story 21 — DCU Sensor Assets & Actions (Demo #25) (Priority: P2)

Sensors hanging off DCUs (transformer monitors, environmental) stream values via HES; EMS displays per-sensor values, thresholds, and allows threshold edits that propagate to MDMS and HES. Alarms on breach.

**Acceptance Scenarios**:

1. **Given** transformer sensor, **When** operator edits threshold, **Then** EMS POSTs to MDMS + HES; new threshold applied within 60 s.
2. **Given** breach, **When** value > threshold for 30 s, **Then** alarm fires with sensor context.

---

### User Story 22 — GIS Zoom Hierarchy & Context Commands (Demo #26) (Priority: P1)

Operator zooms GIS from region → substation → feeder → DTR → pole → meter. Context menu at each level offers level-appropriate commands (region: run report; substation: view load; feeder: view profile; DTR: view downstream; meter: read/disconnect). Map shows alarms, high/low energy zones as heatmap layers.

**Independent Test**: Zoom from country-level to a single meter; verify context menu changes at each level; run "Read meter" at meter level and see command dispatched.

**Acceptance Scenarios**:

1. **Given** country-level zoom, **When** operator right-clicks, **Then** menu includes "Run regional report".
2. **Given** DTR-level zoom, **When** operator right-clicks DTR, **Then** menu includes "View downstream meters" + "View load profile".
3. **Given** meter-level zoom, **When** operator right-clicks meter, **Then** menu includes "Read register", "Disconnect", "View consumer".
4. **Given** heatmap toggle, **When** operator selects "Alarms density", **Then** heatmap layer renders from PostGIS.

---

### User Story 23 — Customisable Dashboards & Report Builder (Demo #7, #19, #27) (Priority: P2)

Operators build dashboards from a widget palette (KPI, chart, map, alarm list, report table), save layouts per user, share with roles. Report builder composes parameters (date range, meter filter, report type) and renders against MDMS EGSM endpoints; saved reports run on schedule and email PDF.

**Acceptance Scenarios**:

1. **Given** operator has a custom layout, **When** they log out and back in, **Then** layout is restored.
2. **Given** operator builds a scheduled report, **When** schedule fires, **Then** PDF emails to recipients.
3. **Given** AppBuilder has a persisted rule, **When** rule condition matches, **Then** configured action fires (notification / command / log).

---

### User Story 24 — App Development Surface: Rules, Algorithms, Apps (Demo #27) (Priority: P3)

Power user authors rules (trigger → action) and small algorithms (Python snippets, sandboxed) and publishes them as "apps" that appear in the widget palette for dashboard builders. Versioned, preview-before-publish, role-gated publish.

**Acceptance Scenarios**:

1. **Given** a rule draft, **When** user clicks Preview, **Then** sample input runs through the rule and action-simulation result shown.
2. **Given** an algorithm, **When** user publishes, **Then** algorithm becomes a widget in App Gallery and role-gated publish workflow enforced.
3. **Given** running app, **When** author edits, **Then** new version is staged; old version keeps running until Promote clicked.

---

### Edge Cases

- MDMS unavailable: every MDMS-sourced surface shows a red banner with last-refresh time; no silent fallback numbers.
- HES unavailable: commands queue in EMS with status QUEUED and a "Waiting for HES" banner.
- Kafka broker down: SSE degrades to 30 s polling; banner "Event stream degraded".
- Simulator and production coexist: `DATA_SOURCE_MODE=simulator|hybrid|production` gates which Kafka topic prefix is consumed.
- New meter appears in HES but not yet in MDMS CIS: meter detail page shows "Consumer data pending — meter registered in HES at TTTT".
- Clock skew between EMS and MDMS: reconcile on each read with `server_time` header.
- Operator has no RBAC role for a page: 403 with explicit message + "Request access" button.
- Tariff with inclining-block or seasonal when MDMS doesn't yet support them: render "Not configured" for those fields — no fake math.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: EMS MUST expose an `/api/v1/mdms/*` proxy that calls `mdms-api` and returns the upstream payload unchanged, with upstream trace-id propagated.
- **FR-002**: EMS MUST expose an `/api/v1/hes/*` proxy that calls HES routing-service and propagates W3C trace context.
- **FR-003**: EMS MUST NOT serve metering/billing/tariff/VEE/CIS/NTL/report data from its own tables in `SSOT_MODE=strict`.
- **FR-004**: EMS MUST consume Kafka topics `hesv2.meter.events`, `hesv2.meter.alarms`, `hesv2.command.status`, `hesv2.sensor.readings`, `hesv2.outage.alerts1`, and `mdms.vee.exceptions` with at-least-once semantics and a DLQ.
- **FR-005**: EMS MUST implement an outage-correlator service that opens `outage_incident` rows on N≥3 power-failure events within configurable window + same DTR.
- **FR-006**: EMS MUST render a red banner when any upstream returns 5xx or times out and MUST NOT substitute stale seeded numbers.
- **FR-007**: EMS MUST support RBAC with roles {admin, supervisor, operator, analyst, viewer}; menu + route + API gated.
- **FR-008**: EMS MUST propagate OTel trace-ids on every outbound call and every audit publish.
- **FR-009**: EMS MUST persist user actions to Kafka topic `mdms.audit.actions` via the shared `otel-common-py.audit()` helper.
- **FR-010**: EMS MUST expose a Playwright-runnable E2E test harness that covers each of the 24 user stories end-to-end (simulator → HES → MDMS → EMS).
- **FR-011**: EMS MUST have Alembic migrations committed; `create_all()` in lifespan REMOVED.
- **FR-012**: EMS MUST replace `random.uniform()` sensor history with a real `transformer_sensor_readings` table fed by Kafka.
- **FR-013**: EMS MUST route SSE JWT via `Authorization` header (not query string).
- **FR-014**: EMS MUST register `/map`, `/reconciler`, `/appbuilder` routes in the deployed `App.jsx`.
- **FR-015**: EMS MUST restore missing files: `backend/app/models/meter.py`, `backend/app/schemas/*`, `frontend/src/App.jsx`.
- **FR-016**: EMS MUST use PostGIS geometry columns on `feeder`, `dtr`, `pole`, `meter` for GIS queries; existing `geojson` columns deprecated.
- **FR-017**: EMS MUST persist AppBuilder apps/rules/algorithms in DB with versioning; hot-reload via publish.
- **FR-018**: EMS MUST support feature flags `SSOT_MODE`, `HES_ENABLED`, `MDMS_ENABLED`, `KAFKA_ENABLED`, `MDMS_NTL_ENABLED`, `TARIFF_INCLINING_ENABLED`, `SMART_INVERTER_COMMANDS_ENABLED`, `SCHEDULED_REPORTS_ENABLED` with defaults for prod=all-true, dev=HES/MDMS true and Kafka true.
- **FR-019**: Notifications MUST go live via SMTP, Twilio SMS, MS Teams webhook, Firebase push — each provider gated by its own enabled flag with rotated credentials from AWS Secrets Manager.
- **FR-020**: EMS MUST remove every hardcoded KPI fallback (`HESMirror` 183/42/15 etc.) and replace with loading-skeleton + error-state components.
- **FR-021**: EMS MUST expose `GET /api/v1/health` that aggregates health of upstream HES, MDMS, Kafka, DB, Redis; `degraded` if any upstream red.
- **FR-022**: EMS MUST implement scheduled report delivery (PDF + email) using a dedicated worker + MDMS CSV pipeline.
- **FR-023**: EMS MUST implement frontend components library `components/ui/` (Button, Card, KPI, Chart, Modal, Toast, Skeleton, ErrorBoundary) and refactor pages to use it.
- **FR-024**: EMS MUST emit per-demo-story OpenTelemetry trace samples validated by an integration test at boot-time.

### Non-Functional Requirements

- **NFR-001**: Dashboard first paint ≤ 2 s with warm cache, ≤ 4 s cold.
- **NFR-002**: SSE event-to-UI latency ≤ 3 s p95.
- **NFR-003**: Batch command dispatch ≤ 10 s for 100 meters (parallelism=10).
- **NFR-004**: Outage correlation latency ≤ 90 s from first event to incident open.
- **NFR-005**: Zero runtime errors on all 17 routes in Playwright smoke.
- **NFR-006**: All secrets fetched from AWS Parameter Store / Secrets Manager; no credentials in images or `.env` shipped.
- **NFR-007**: Horizontal scalability: backend stateless; SSE shared store via Redis pub/sub.

### Key Entities

- **OutageIncident** (EMS-owned): id, opened_at, closed_at, status, suspected_fault_point (PostGIS), affected_dtr_ids, affected_meter_count, confidence_pct, timeline (JSONB), saidi_contribution_seconds.
- **DERAsset, DERTelemetry, DERCommand** (EMS-owned): captured in detail in data-model.md.
- **TransformerSensorReading** (EMS-owned): sensor_id, ts, value, unit, breach_flag.
- **AppDef, RuleDef, AlgorithmDef** (EMS-owned): versioned author/publish workflow.
- **AlarmSubscription, VirtualObjectGroup, NotificationDelivery** (EMS-owned).
- **SourceStatus** (EMS-owned cache): per-meter HES/MDMS/CIS last-seen timestamps.
- Upstream entities (MDMS/HES) are referenced by ID only — never shadowed in EMS tables.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Playwright E2E suite runs all 24 user-story scenarios against dev EKS; ≥ 23/24 pass before demo day; 100% post-demo.
- **SC-002**: Zero P0/P1 items remaining from `docs/GAPS.md` §5 on demo day.
- **SC-003**: `SSOT_MODE=strict` deployable without any seeded-data fallback visible on the 17 routes.
- **SC-004**: Upstream dependency dashboard shows green for HES, MDMS, Kafka, DB in production profile during demo.
- **SC-005**: Load test: 10 concurrent operator sessions sustain dashboard + SSE without errors; p95 ≤ SLOs above.
- **SC-006**: Every demo story's backing data has an OTel trace-id that can be searched in Grafana/Tempo and linked to the MDMS `action_audit_log` row.
- **SC-007**: Role-gated routes: analyst role cannot access `/admin` and vice versa — verified by Playwright.
- **SC-008**: All 24 user stories have at least one automated integration test in `backend/tests/integration/demo_compliance/test_demo_*.py`.

## Assumptions

- MDMS team (Umesh) will triage `mdms-todos.md` and commit to landing MDMS-T1…T7 before demo day where feasible; otherwise feature-flagged fallbacks are used and narrated as "MDMS roadmap items".
- Simulator has equivalent spec (`repos/simulator/specs/001-ami-full-data-generation`) that seeds HES DB + publishes Kafka; EMS does not seed directly.
- AWS dev EKS cluster, Kafka on EC2, PostgreSQL on EC2 remain the target deploy surfaces.
- LGTM observability stack (already deployed per CLAUDE.md) remains available for trace/log assertions in E2E tests.
- `eskom_dev` is the integration branch; PRs from `018-smoc-ems-full-compliance` target `eskom_dev`.
- Demo repo freeze (`avdhaan_v2` + `mdms-reports` since 2026-04-12) stays in effect; this spec does not modify them.
- Playwright harness lives at `e2e/` with existing 102-test suite; new demo-compliance tests extend it (see `reference_e2e_testing.md`).
- Production rollout post-demo 21 Apr 2026 follows GSD workflow; phases tracked in `.planning/`.
