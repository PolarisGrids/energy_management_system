# MDMS Upstream TODOs for Spec 018 (SMOC/EMS Full Compliance)

**Created**: 2026-04-18
**Owner**: Umesh (approval required per `feedback_mdms_umesh_approval.md`)
**Consumer**: `polaris_ems/specs/018-smoc-ems-full-compliance`

This backlog lists every MDMS-side change the EMS compliance spec depends on. None of these are being worked on as part of the EMS branch. Each is gated behind a feature flag in EMS so work proceeds in parallel. **Ask Umesh before starting any item. Demo freeze on `mdms-reports` since 2026-04-12.**

Severity:
- **M0** — demo-critical, ideally landed by 2026-04-20
- **M1** — post-demo, 2–4 weeks
- **M2** — roadmap, quarter+

---

## MDMS-T1 — Inclining-Block + Seasonal Tariff in Billing Engine  `M1`

**Why**: EMS User Story 6 (Demo #6) narrates "complex tariff and rate engine" including inclining-block and seasonal variation. Current `mdms-billing-engine` has TOU (8 TZ registers), CPP, demand (kW, kVA) — **missing**: inclining-block tier logic, seasonal factor multiplier.

**Scope**:
- New `tariff_tier` table: tariff_id, tier_step (1..N), lower_kwh, upper_kwh, rate_per_kwh.
- New `tariff_seasonal_factor` table: tariff_id, month, factor.
- Extend billing pipeline to compute per-tier kWh breakdown + apply seasonal factor.
- `GET /mdms/tariffs/:id` returns `tiers[]`, `seasonal_factors{}` in payload.
- Billing determinants include `tier_breakdown` JSONB.

**EMS fallback while pending**: Tariff Explorer page shows "Not configured" for tier + seasonal columns.

---

## MDMS-T2 — NTL Service Implementation  `M1`

**Why**: EMS User Story 9 (Demo #4, #6) narrates tamper/theft analytics with suspicion scoring. Current `mdms-ntl-service` directory is an empty stub (submodules only, 0 LOC).

**Scope**:
- Implement NTL scoring engine: event-flag correlation (tamper, cover-open, reverse-energy, magnet), consumption-pattern anomalies (z-score, flat-line, sudden drop), energy-balance gap per DTR.
- Output: `ntl_suspect` table + `GET /mdms/ntl/suspects?dtr=&from=&to=`.
- Energy-balance MV per DTR: feeder input kWh − sum(downstream meter kWh) → loss %.
- Push suspect state changes to Kafka `mdms.ntl.suspects`.

**EMS fallback while pending**: NTL page uses local event-correlation only with a banner "Scoring unavailable (MDMS NTL service offline)".

---

## MDMS-T3 — Load Profile by Class Materialised View  `M1`

**Why**: EMS User Story 8 (Demo #6, #9) needs p10/p50/p90 half-hourly curves per customer class. Today the data exists in `blockload_vee_validated` but no aggregation surface.

**Scope**:
- Materialised view `load_profile_by_class_half_hour` with half-hour of day × class × p10/p50/p90/mean.
- Refresh nightly (or on-demand for demo).
- `GET /mdms/analytics/load-profile?class=&date_from=&date_to=` returns chart-ready payload.
- Wire into `mdms-analytics-service` (consistent with 017 cutover pattern).

**EMS fallback while pending**: Page shows raw half-hour curve with single p50 line only; banner "Percentile bands pending MDMS aggregate".

---

## MDMS-T4 — Automatic Prepaid Register Readback Post-Recharge  `M0`

**Why**: `project_prepaid_register_readback_gap.md` memory flags this. After a recharge is ACCEPTED, MDMS should auto-trigger a read-back of the 13 prepaid registers so the updated balance is available without operator polling.

**Scope**:
- `mdms-prepaid-engine`: on token ACCEPTED event, enqueue HES read for meter; on response, upsert `prepaid_registers`.
- Publish `mdms.prepaid.register_readback` event so EMS can refresh without polling.
- Fault tolerance: retry schedule, DLQ on final fail.

**EMS fallback while pending**: EMS polls `/prepaid/registers?account=` every 15 s for 2 min after recharge, per User Story 10.

---

## MDMS-T5 — Smart-Inverter Command Passthrough  `M1`

**Why**: EMS User Story 17 + Simulator User Story 6 require dispatching a curtailment command to a PV inverter or an EV fast-charger. Today command-exec supports meter RC/DC/FOTA/token commands; inverter and DER command types are absent.

**Scope**:
- Add command types `DER_CURTAIL`, `DER_SET_ACTIVE_POWER`, `DER_SET_REACTIVE_POWER`, `EV_CHARGER_SET_POWER` to `mdms-cmd-exec-service`.
- Route through HES to simulator/inverter; status lifecycle via existing Kafka pattern.
- Audit trail entry with `command.type=DER_CURTAIL`, `asset.id=pv-01`, etc.

**EMS fallback while pending**: `SMART_INVERTER_COMMANDS_ENABLED=false` in prod; dev simulator accepts direct REST.

---

## MDMS-T6 — WFM Hook for Outage-Driven Crew Dispatch  `M1`

**Why**: EMS User Story 4 outage page right-click offers "Dispatch crew". Today no WFM module integrated.

**Scope**:
- Design decision: build lightweight WFM in MDMS OR integrate with existing Eskom MDMS WFM (if any).
- If new: `GET/POST /mdms/wfm/work-orders`; create WO from outage incident payload; status lifecycle.
- If existing: adapter publishing to external system via REST/webhook.

**EMS fallback while pending**: "Dispatch crew" button disabled with tooltip "WFM integration pending".

---

## MDMS-T7 — Fix 4 Broken EGSM Report Endpoints via Analytics Service Cutover  `M0`

**Why**: `project_mdms_reports_4_broken_endpoints.md` memory: `communication-fault`, `non-communicating`, `data-availability-summary`, `changed-data-log` broken on DB schema mismatch. Fix already scoped in `polaris_ems:017-egsm-reports-postgres` branch via `mdms-analytics-service` materialised views.

**Scope**:
- Complete spec 017 cutover: MVs T168–T171 populated; `mdms-reports` swaps to analytics service via one env-var swap.
- **Current blocker**: `mdms-analytics-service` pod in CrashLoopBackOff on dev EKS (5 restarts as of 2026-04-18).

**EMS fallback while pending**: Reports page hides the 4 endpoints with a "Coming soon" state.

---

## MDMS-T8 — Bulk Consumer Import Endpoint  `M2`

**Why**: Simulator currently seeds CIS via direct DB insert. A clean REST ingress would remove simulator's DB-level coupling.

**Scope**: `POST /mdms/cis/bulk-import` accepts array of `ConsumerMasterdata`; validated + inserted in batches; response reports errors per row.

**Simulator fallback while pending**: Keep direct DB seed in `mdms_cis_db_seeder.py`.

---

## MDMS-T9 — MDMS API Gateway `x-user-story-id` Header Propagation  `M2`

**Why**: Observability contract — every EMS call carries `x-user-story-id`; MDMS should record it in traces + audit events for cross-service correlation.

**Scope**: `mdms-api` middleware: read `x-user-story-id`, set on span attribute, include in audit event publish.

---

## MDMS-T10 — VEE Estimation Algorithm Implementation  `M1`

**Why**: `mdms_vee_service/estimation-service` is a 40-LOC health-check stub. User Story 5 narrates estimation methods (interpolation, historical avg, regression); if estimation branch runs, it returns nothing sensible.

**Scope**:
- Implement linear interpolation, historical 28-day average, profile-class regression.
- Config: per rule, choose estimation method.
- Audit every estimation with method + confidence score.

**EMS fallback while pending**: Gate estimation tab behind `VEE_ESTIMATION_ENABLED=false`; show "Validation only — estimation coming soon".

---

## Summary Table

| ID | Title | Severity | Demo Relevance | EMS Fallback |
|---|---|---|---|---|
| T1 | Inclining-block + seasonal tariff | M1 | #6 US-6 | "Not configured" |
| T2 | NTL service impl | M1 | #4 #6 US-9 | Event correlation only |
| T3 | Load profile by class MV | M1 | #6 #9 US-8 | Single p50 line |
| T4 | Prepaid auto-readback | M0 | #7 US-10 | Polling fallback |
| T5 | Inverter command passthrough | M1 | #21 US-17 | Dev REST only |
| T6 | WFM hook | M1 | #4 US-4 | Button disabled |
| T7 | 4 broken EGSM endpoints (cutover) | M0 | #14 US-14 | "Coming soon" |
| T8 | Bulk CIS import endpoint | M2 | simulator only | Direct DB seed |
| T9 | `x-user-story-id` propagation | M2 | traces | Missing attribute |
| T10 | VEE estimation algorithms | M1 | #6 US-5 | Disabled tab |

**Action for Umesh**: confirm which can land by 2026-04-20 (M0 items especially), and ack fallbacks for the rest.

---

## Endpoints EMS calls via the SSOT proxy that don't exist (or aren't confirmed) in MDMS yet — spec 018 Wave 1

Logged during Wave 1 implementation. These are the MDMS-side paths the
refactored `MDMSMirror.jsx` (and `useSSOTDashboard`) now call through the
`/api/v1/mdms/*` proxy. Please confirm + ack each or nominate an alternate
path; EMS will update `frontend/src/services/api.js` `mdmsAPI` once Umesh
replies.

| EMS call | Proxied path | Status per MDMS team | Feature flag |
|---|---|---|---|
| `mdmsAPI.veeSummary({date})`            | `GET /api/v1/vee/summary?date=`            | **UNCONFIRMED** — schema {items:[{date, validated_count, estimated_count, failed_count}]} assumed | MDMS_ENABLED |
| `mdmsAPI.veeExceptions({page,page_size})` | `GET /api/v1/vee/exceptions`              | **UNCONFIRMED** — spec contract lists `rule, date, page` only | MDMS_ENABLED |
| `mdmsAPI.consumers({page,page_size})`    | `GET /api/v1/cis/consumers`                | Likely confirmed in `mdms-cis-service` — need schema stabilisation (account_number vs account) | MDMS_ENABLED |
| `mdmsAPI.hierarchy()`                    | `GET /api/v1/cis/hierarchy`                | **UNCONFIRMED** — EMS needs a dashboard-level rollup `{total_transformers, total_feeders}`, which `mdms-cis-service` may not return; see useSSOTDashboard | MDMS_ENABLED |
| `mdmsAPI.tariffs()`                      | `GET /api/v1/tariffs`                      | Confirmed list endpoint exists in `mdms-billing-engine`; field names (offpeak_rate vs offpeak) need final mapping | MDMS_ENABLED |
| `mdmsAPI.ntlSuspects()`                  | `GET /api/v1/ntl/suspects`                 | **Depends on MDMS-T2** (NTL service) — EMS gated behind `MDMS_NTL_ENABLED` | MDMS_NTL_ENABLED |
| `mdmsAPI.powerQuality()`                 | `GET /api/v1/analytics/power-quality`      | **DOES NOT EXIST** — EMS Analytics tab renders UpstreamErrorPanel noting this. Candidate: expose a derived MV from `mdms-analytics-service` (spec 017 follow-on). | MDMS_ENABLED |

Similar list for HES — covered by `contracts/hes-integration.md`; the one
callout is that `GET /api/v1/network/comm-trend?days=N` in EMS Dashboard
/ HESMirror may need to be added to HES routing-service if the DCU trend
isn't already exposed. EMS gracefully renders "No trend data yet" when
this returns 404, so it's non-blocking.
