# Tasks: SMOC/EMS Full AMI Compliance (Spec 018)

**Branch**: `018-smoc-ems-full-compliance` (created from `eskom_dev`)
**Date**: 2026-04-18
**Source**: `./spec.md`, `./plan.md`

## Conventions

- **ID**: `W<wave>.T<task>`; decimal sub-task allowed (`W2.T3.1`).
- **Dep**: prerequisite task IDs or external refs (e.g. `MDMS-T4`).
- **Verify**: exactly how task is proven done.
- **Status**: tracked live in `.planning/` when execution starts.
- All tasks produce atomic commits on `018-smoc-ems-full-compliance`.
- "Commit & verify" means: `pytest <scope>` green, lint green, commit message in repo convention.

---

## Wave 0 — P0 Repo-Integrity (Day 1, **~95% already complete — see `research.md`**)

Verification (2026-04-18) confirms GAPS.md P0 items landed via today's restoration commits. Original Wave 0 is collapsed to residual tasks:

| ID | Task | Status | Dep | Verify |
|---|---|---|---|---|
| W0.T1 | Cut branch `018-smoc-ems-full-compliance` from `eskom_dev` HEAD | OPEN | — | `git branch --show-current` |
| W0.T2 | Investigate P0 file state (delivered `research.md`) | **DONE** | — | research.md committed |
| W0.T3 | `backend/app/models/meter.py` present + correct | **DONE (verified)** | — | 4153 B; all exports confirmed |
| W0.T4 | `backend/app/schemas/*` present (alarm, auth, der, meter, sensor, simulation) | **DONE (verified)** | — | pydantic v2; `/docs` renders |
| W0.T4.1 | Add schemas for later waves: `outage.py`, `report.py`, `app_builder.py`, `ntl.py` | OPEN | — | imports in new endpoints compile |
| W0.T5 | Alembic baseline + phase-b migrations present; `create_all()` removed | **DONE (verified)** | — | 5 migrations in `alembic/versions/` |
| W0.T6 | `frontend/src/App.jsx` present with 21 routes | **DONE (verified)** | — | 3815 B; React Router v6 |
| W0.T7 | `reconcilerAPI` exported from `services/api.js` | **DONE (verified)** | — | line 129 |
| W0.T8 | SSE auth via header (primary); legacy `?token=` query still accepted | **PARTIAL — close-out** | — | Deprecate: emit warn log + metric on `?token=` use; target removal Wave 1 |
| W0.T9 | `HESMirror.jsx` hardcoded fallbacks removed | **DONE (verified)** | — | grep for `183\|91.4` returns empty |
| W0.T10 | `MDMSMirror.jsx` NaN% fixed | **DONE (verified)** | — | `totalProcessed > 0 ? … : '—'` at line 35 |
| W0.T11 | `Dashboard.jsx` empty-state handling | **LIKELY DONE — verify** | — | Playwright assert no `—` when upstream live |
| W0.T12 | `EnergyMonitoring.jsx` empty-state handling | **VERIFY** | — | Playwright assert with empty data |
| W0.T13 | `components/ui/` library | **DONE (verified)** 10 components: Badge, Button, Card, ChartWrapper, EmptyState, ErrorBoundary, KPI, Modal, Skeleton, Spinner | — | ls; only `Toast` remains |
| W0.T13.1 | Add `Toast.jsx` to complete component library | OPEN | W0.T13 | import in a page |
| W0.T14 | Playwright smoke against 21 registered routes (no 404, no console errors) | OPEN | W0.T1 | CI green |
| W0.T15 | Gate A sign-off: checklist `checklists/p0-gaps.md` confirmed (not rebuilt) | OPEN | all W0 | PR review |

**Gate A** (revised): branch cut, Toast added, smoke tests green, SSE legacy path deprecated.

**Residual effort**: ~0.5 engineer-day.

---

## Wave 1 — SSOT Proxy Layer & Feature Flags (Days 3–5)

| ID | Task | Dep | Verify |
|---|---|---|---|
| W1.T1 | Add `SSOT_MODE` enum (strict/mirror/disabled) to `backend/app/core/config.py`; plus per-integration flags | W0 | unit test: config loads with correct defaults per env |
| W1.T2 | Implement AWS Parameter Store / Secrets Manager loader `backend/app/core/secrets.py`; remove placeholder creds from `config.py` | W1.T1 | startup reads real secrets; local dev falls back to `.env` |
| W1.T3 | Build `backend/app/api/v1/endpoints/mdms_proxy.py` pass-through using httpx.AsyncClient with trace propagation | W1.T1 | `GET /api/v1/mdms/tariffs` returns MDMS payload; integration test against dev `mdms-api` |
| W1.T4 | Build `backend/app/api/v1/endpoints/hes_proxy.py` pass-through | W1.T1 | `GET /api/v1/hes/dcus` returns HES payload |
| W1.T5 | Rewrite `services/hes_client.py` with real URLs, 3-retry backoff, circuit breaker (`pybreaker`), trace-context header | W1.T2 | unit test: 500 triggers retry then open breaker |
| W1.T6 | Rewrite `services/mdms_client.py` similarly | W1.T2 | same |
| W1.T7 | Refactor `MDMSMirror.jsx` to consume `/api/v1/mdms/*` proxy; remove local-DB lookups | W1.T3, W0.T10 | Playwright: MDMS down → banner; live MDMS → data matches `mdms-api` direct |
| W1.T8 | Refactor `HESMirror.jsx` similarly | W1.T4, W0.T9 | Playwright |
| W1.T9 | Refactor `Dashboard.jsx` to source KPIs from proxy endpoints | W1.T3, W1.T4 | Playwright |
| W1.T10 | Implement `GET /api/v1/health` aggregating upstream health | W1.T5, W1.T6 | curl returns `{hes: ok, mdms: ok, kafka: ok, db: ok}` |
| W1.T11 | Frontend banner component: detects degraded `/health` and shows persistent red bar | W1.T10 | Playwright: simulate 503 |
| W1.T12 | Gate B dress rehearsal: `SSOT_MODE=mirror` deploys to dev EKS, HES/MDMS reachable, no hardcoded fallback visible | all W1 | `/e2e-test` skill baseline green |

**Gate B**: `SSOT_MODE=mirror` with real upstream, zero hardcoded numbers on 17 routes.

---

## Wave 2 — Live HES Command & Event Plumbing (Days 5–8)

| ID | Task | Dep | Verify |
|---|---|---|---|
| W2.T1 | Implement `services/kafka_consumer.py` base: aiokafka, SASL/SCRAM, DLQ topics, at-least-once | W1 | unit test against testcontainers Kafka |
| W2.T2 | Consumer for `hesv2.meter.events` → persist `meter_event_log` + feed outage correlator | W2.T1 | int test: publish event → row appears |
| W2.T3 | Consumer for `hesv2.meter.alarms` → `alarm_event` | W2.T1 | int test |
| W2.T4 | Consumer for `hesv2.command.status` → update `command_log` + meter row on CONFIRMED | W2.T1 | int test: command lifecycle updates meter.relay_state |
| W2.T5 | Consumer for `hesv2.sensor.readings` → `transformer_sensor_reading` table | W2.T1 | int test |
| W2.T6 | Consumer for `hesv2.network.health` → `dcu_health_cache` | W2.T1 | int test |
| W2.T7 | Consumer for `hesv2.der.telemetry` → `der_telemetry` table | W2.T1 | int test |
| W2.T8 | Refactor `POST /api/v1/meters/{s}/disconnect` to publish via HES routing; persist command_id; wait for CONFIRMED status via Kafka | W2.T4 | Playwright: disconnect flow end-to-end |
| W2.T9 | Batch disconnect endpoint with semaphore concurrency=10 | W2.T8 | int test: 100 meters in ≤ 10 s |
| W2.T10 | FOTA service: S3 image upload, HES job create, progress poller, `fota_job_meter_status` table | W1, W2.T1 | Playwright: FOTA 20 meters |
| W2.T11 | Replace `endpoints/sensors.py` `random.uniform` history with DB query | W2.T5 | unit test fails if random call path hit |
| W2.T12 | DER command path: `POST /api/v1/der/{id}/command` → HES inverter command (feature-flag `SMART_INVERTER_COMMANDS_ENABLED`); persist `der_command` | W2.T4, W2.T7 | int test |
| W2.T13 | Backend `audit()` wiring for every write endpoint using `otel-common-py` | W1 | audit events visible in MDMS `action_audit_log` |
| W2.T14 | Demo-compliance test `test_us02_rc_dc.py` passing end-to-end | W2.T8 | CI green |

---

## Wave 3 — Outage, NTL, GIS, DER, Scenarios (Days 8–12)

| ID | Task | Dep | Verify |
|---|---|---|---|
| W3.T1 | `services/outage_correlator.py`: N≥3 power-failure / same DTR / 120s window → open `outage_incident` | W2.T2 | int test: simulator network_fault scenario opens incident |
| W3.T2 | Restoration detection: close incident when all affected meters emit `power_restored` | W3.T1 | int test |
| W3.T3 | SAIDI/SAIFI/CAIDI materialised view (refresh nightly) | W3.T1 | verify against known test data |
| W3.T4 | `endpoints/outage.py`: list, detail, acknowledge, dispatch-crew (MDMS-T6 hook) | W3.T1 | Playwright |
| W3.T5 | GIS GeoJSON endpoints `/api/v1/gis/layers?layer=&bbox=` sourced from PostGIS (phase-b/014 tables) | W1 | visual: Leaflet renders feeder geometry |
| W3.T6 | `GISMap.jsx` refactor: feeder/DTR/pole/meter layers + per-zoom context menus | W3.T5 | Playwright: zoom levels + context menu |
| W3.T7 | Outage overlay layer on GIS: red circle per affected DTR + confidence label | W3.T4, W3.T5 | Playwright |
| W3.T8 | `endpoints/ntl.py`: list suspects (MDMS proxy when `MDMS_NTL_ENABLED`, else local event-correlation) | W1, W2.T2 | int test: theft injection scenario flags meter |
| W3.T9 | `NTL.jsx` dashboard page + map overlay; banner when scoring unavailable | W3.T8 | Playwright |
| W3.T10 | Energy-balance per DTR: feeder input vs downstream-sum; EMS computes from MDMS readings + consumer totals | W1 | int test |
| W3.T11 | DER pages: `DERPv.jsx`, `DERBess.jsx`, `DEREv.jsx`, `DistributionRoom.jsx` with live telemetry via SSE | W2.T7 | Playwright |
| W3.T12 | DER aggregation view per feeder (stacked area chart) | W3.T11 | Playwright |
| W3.T13 | Reverse-flow detection + banner | W2.T7 | int test |
| W3.T14 | Scenario proxy endpoints `/api/v1/simulation/*` → simulator REST | — | int test: start scenario |
| W3.T15 | Inverter curtailment round-trip: scenario calc → EMS → HES → simulator ACK | W2.T12, W3.T14 | int test: `test_us17_solar_overvoltage.py` |
| W3.T16 | EV fast-charging curtail round-trip | W2.T12, W3.T14 | int test: `test_us18_ev_fast_charge.py` |
| W3.T17 | FLISR actions: isolate, restore → HES commands; updates outage incident | W3.T1, W2.T8 | int test: `test_us20_fault_flisr.py` |
| W3.T18 | Bulk import endpoint `POST /api/v1/der/bulk-import` for simulator bootstrap | W1 | contract test with simulator |

---

## Wave 4 — Alerts, AppBuilder, Reports, RBAC, Notifications (Days 12–16)

| ID | Task | Dep | Verify |
|---|---|---|---|
| W4.T1 | Notification providers: SMTP (SES), Twilio SMS, MS Teams webhook, Firebase push; real creds via Secrets Manager | W1.T2 | integration: send each channel to test recipient |
| W4.T2 | `notification_delivery` table + audit event per send | W4.T1 | int test |
| W4.T3 | Virtual object group CRUD `/api/v1/groups` | — | Playwright |
| W4.T4 | Alarm rule engine: persisted rules evaluated against event stream; firing → notifications + actions | W4.T2, W2.T2 | int test: create rule, drive DTR > 80%, SMS received |
| W4.T5 | Quiet hours + escalation tiers | W4.T4 | int test |
| W4.T6 | AppBuilder backend: `app_def`, `rule_def`, `algorithm_def` tables + CRUD; versioning + preview + publish workflow | W1 | Playwright: create → preview → publish |
| W4.T7 | Python algorithm sandbox runner (decision doc in research.md: Pyodide vs remote worker) | W4.T6 | int test: publish algorithm, run, see output |
| W4.T8 | `AppBuilder.jsx` refactor: persisted apps/rules/algorithms; role-gated publish | W4.T6 | Playwright |
| W4.T9 | Reports: proxy all MDMS EGSM endpoints via `/api/v1/mdms/reports/*` | W1.T3 | Playwright: run any report, results match MDMS |
| W4.T10 | Scheduled report worker (APScheduler): `scheduled_report` table; email PDF | W4.T9 | int test: cron fires, email delivered |
| W4.T11 | Saved dashboard layouts `dashboard_layout` table; `Dashboard.jsx` loads per-user layout | — | Playwright |
| W4.T12 | RBAC frontend: menu + route guards per role | — | Playwright: viewer cannot see /admin |
| W4.T13 | RBAC backend: FastAPI dependency per endpoint | — | unit test matrix |
| W4.T14 | Data Accuracy console: `source_status` refresher job + page | W1 | Playwright |

---

## Wave 5 — E2E Tests & Demo Polish (Days 16–19)

| ID | Task | Dep | Verify |
|---|---|---|---|
| W5.T1..T24 | Write one integration test per user story under `backend/tests/integration/demo_compliance/test_us{01..24}_*.py` | all above | CI matrix runs |
| W5.T25..T48 | Write one Playwright test per user story under `frontend/tests/e2e/demo_compliance/us{01..24}_*.spec.ts` | all above | CI matrix runs |
| W5.T49 | Synthetic probe suite deploy (every 5 min on dev) | W5 | Grafana alert rule green |
| W5.T50 | Load test k6: 50 concurrent operator sessions | W5 | SLOs met in report |
| W5.T51 | Security review (/security-review skill) on PR bundle | W5 | no P1 findings |
| W5.T52 | Dress rehearsal 2026-04-20 full E2E 3× | W5 | all flake logged |
| W5.T53 | Demo-day go/no-go checklist `checklists/demo-day.md` filled | W5.T52 | ticked |

---

## Wave 6 — Post-Demo Hardening (Days 19+)

Out-of-scope for demo day. Continues in same branch or cuts spec 019.

| ID | Task | Verify |
|---|---|---|
| W6.T1 | Multi-AZ Postgres + read replica | load test |
| W6.T2 | i18n pass (en/zu/st/af) | manual review |
| W6.T3 | Pen-test remediation backlog | security-review green |
| W6.T4 | Video-wall layout manager | Playwright |
| W6.T5 | IEC 61968/61970 CIM import | contract test |

---

## Parallelisation Hints

- Wave 0 is sequential on W0.T2 (research); the rest parallelise by file ownership.
- Wave 1 T3+T4+T5+T6 parallel; refactors T7+T8+T9 parallel after.
- Wave 2 consumers T2..T7 parallel; commands T8+T10+T12 parallel after the consumers.
- Wave 3 Outage, GIS, NTL, DER run as 4 parallel tracks.
- Wave 4 Notifications, AppBuilder, Reports, RBAC as 4 parallel tracks.

## Estimated Effort (engineer-days)

- W0: 2 d (1 eng)
- W1: 3 d (2 engs)
- W2: 4 d (2 engs)
- W3: 5 d (3 engs)
- W4: 5 d (3 engs)
- W5: 4 d (2 engs)
- Total: ~23 eng-days. With 3 engineers in parallel: ~8–10 elapsed days.

## Cross-Spec Dependencies

- Requires simulator W0..W3 complete → DER bulk import + scenario API + Kafka topics up.
- Requires MDMS-T4, T7 landed (M0) by 2026-04-20 per `mdms-todos.md`.
- Requires phase-b/014 GIS PostGIS tables (already merged).
