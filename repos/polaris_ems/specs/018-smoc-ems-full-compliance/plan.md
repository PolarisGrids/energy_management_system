# Implementation Plan: SMOC/EMS Full AMI Compliance

**Branch**: `018-smoc-ems-full-compliance` | **Date**: 2026-04-18 | **Spec**: `./spec.md`

## Summary

Deliver a production-grade Polaris EMS that satisfies all 24 Eskom demo capabilities (#4–#27) and the post-demo production roadmap. EMS reads MDMS as SSOT for metering/billing/VEE/tariff/CIS/NTL/reports; HES as SSOT for commands/DCU/comm-health/raw events; EMS owns DER, outage incidents, sensor history, audit, AppBuilder. Simulator feeds HES only — EMS does not consume from simulator directly.

Six waves of work. Each wave independently deployable to dev EKS. P0 repo-integrity fixes in Wave 0 gate everything else.

## Technical Context

**Language/Version**: Python 3.12 (backend, FastAPI), Node.js 20 (none yet — possible for AppBuilder runtime), TypeScript 5 + React 18 (frontend, Vite)
**Primary Dependencies**: FastAPI, SQLAlchemy 2 + Alembic, asyncpg, aiokafka, httpx, OpenTelemetry SDK, `otel-common-py`, Leaflet + MapLibre (post-Wave 4), shadcn-style component library (net-new)
**Storage**: PostgreSQL (EMS DB on EC2, shared with phase-b additions). PostGIS extension enabled in phase-b/014. Redis (SSE fanout, rate-limit, cache). MDMS/HES Postgres are upstream-only from EMS's perspective.
**Testing**: pytest for backend unit/integration; Playwright for frontend E2E; `testcontainers-python` for Kafka integration; MDMS/HES mocked with `respx` for unit, real for integration.
**Target Platform**: Linux container on AWS EKS (ap-south-1 `dev-cluster`); CodePipeline build → ECR → ArgoCD / Helm. IPv6-primary pod network (see commit 2495bb6).
**Project Type**: Web application — `backend/` (FastAPI) + `frontend/` (Vite+React)
**Performance Goals**: Dashboard first paint ≤ 2 s warm / ≤ 4 s cold. SSE event-to-UI ≤ 3 s p95. Batch 100 RC/DC ≤ 10 s. Outage correlation ≤ 90 s. Support 50 operator sessions concurrent in dev; 200 in prod.
**Constraints**: No seeded-data fallback in `SSOT_MODE=strict`. All secrets from AWS Parameter Store / Secrets Manager. All outbound calls trace-propagated. RBAC enforced in backend + frontend.
**Scale/Scope**: 3000 meters, 200 DTRs, 20 feeders, 5 substations, 50 DER assets, 10 sensor types × 20 DTRs in the demo dataset; 1M meters, 50k DTRs production target.

## Constitution Check

(No Polaris EMS constitution file yet — will inherit the simulator `.specify/memory/constitution.md` principles: no seeded fallbacks in production, trace-everything, feature-flag new integrations, real upstream over mock.)

Gates to pass:
- **Gate A** (end of Wave 0): clean `docker compose up` starts backend + frontend with `SSOT_MODE=disabled` on a blank Postgres — smoke: all 17 routes render no-error.
- **Gate B** (end of Wave 2): `SSOT_MODE=mirror` deploys to dev EKS with HES + MDMS clients enabled against real upstreams; zero hardcoded fallback numbers visible.
- **Gate C** (end of Wave 4): `SSOT_MODE=strict` passes 23/24 E2E user-story tests.
- **Gate D** (end of Wave 5): `SSOT_MODE=strict` 24/24 pass; load test green; security review clean.

## Project Structure

### Documentation (this feature)

```text
specs/018-smoc-ems-full-compliance/
├── plan.md                             # This file
├── spec.md                             # Feature spec (already created)
├── research.md                         # Upstream API shape, MDMS DB schema, Kafka topic schemas
├── data-model.md                       # EMS-owned entities + ER diagram
├── quickstart.md                       # Dev bring-up, SSOT_MODE toggles
├── mdms-todos.md                       # MDMS-side changes (Umesh approval)
├── integration-test-matrix.md          # 24 demo stories × E2E trace
├── contracts/
│   ├── mdms-integration.md             # MDMS API proxy contract
│   ├── hes-integration.md              # HES commands + Kafka consumer contract
│   ├── simulator-cooperation.md        # EMS DER bulk-import + scenario API calls
│   └── observability.md                # Required spans + audit events per user story
├── checklists/
│   ├── requirements.md                 # Full FR/NFR sign-off list
│   ├── p0-gaps.md                      # Derived from docs/GAPS.md §0+§1.1
│   └── demo-day.md                     # 21 Apr go/no-go checklist
└── tasks.md                            # /speckit.tasks output (generated later)
```

### Source Code (repository root — changes)

```text
backend/
├── app/
│   ├── api/v1/endpoints/
│   │   ├── mdms_proxy.py               # NEW — pass-through to mdms-api
│   │   ├── hes_proxy.py                # NEW — pass-through to hes routing-service
│   │   ├── mdms_mirror.py              # REFACTOR — thin view over proxy; drops seeded fallback
│   │   ├── hes_mirror.py               # REFACTOR — same
│   │   ├── outage.py                   # NEW — outage incident CRUD + correlator trigger
│   │   ├── der.py                      # EXTEND — commands routed through HES (not DB-only)
│   │   ├── sensors.py                  # REFACTOR — replace random history with DB reads
│   │   ├── app_builder.py              # NEW — persist apps/rules/algorithms
│   │   ├── reports.py                  # REFACTOR — proxy to MDMS EGSM reports
│   │   └── (existing)
│   ├── services/
│   │   ├── hes_client.py               # FIX — enable by default; real calls; retry + circuit breaker
│   │   ├── mdms_client.py              # FIX — enable by default; real calls
│   │   ├── kafka_consumer.py           # NEW — hesv2.* + mdms.* topic consumers
│   │   ├── outage_correlator.py        # NEW — N-of-M power-failure → incident
│   │   ├── fota_service.py             # NEW — FOTA job orchestration via HES
│   │   ├── notification_service.py     # FIX — real SMTP/Twilio/Teams/Firebase paths
│   │   ├── rule_engine.py              # NEW — AppBuilder rule runtime
│   │   └── (existing)
│   ├── models/
│   │   ├── meter.py                    # RESTORE (P0, missing)
│   │   ├── outage.py                   # NEW
│   │   ├── transformer_sensor_reading.py  # NEW
│   │   ├── app_builder.py              # NEW
│   │   ├── der.py                      # EXTEND (schedules, command lifecycle)
│   │   └── (existing)
│   ├── schemas/                        # RESTORE ALL (P0, missing)
│   └── core/
│       ├── config.py                   # add SSOT_MODE and per-integration flags
│       └── secrets.py                  # NEW — AWS Parameter Store / Secrets Manager loader
├── alembic/
│   └── versions/                       # commit baseline + 018 migrations
├── tests/
│   ├── integration/demo_compliance/    # NEW — 24 stories × 1 test each
│   ├── integration/mdms_integration/
│   ├── integration/hes_integration/
│   └── unit/
└── scripts/
    └── seed_data.py                    # REDUCE — DER/scenario/audit only; meters come via HES

frontend/
├── src/
│   ├── App.jsx                         # RESTORE (P0)
│   ├── components/ui/                  # NEW — Button/Card/KPI/Chart/Modal/Toast/Skeleton/ErrorBoundary
│   ├── components/charts/              # EXTRACT from pages
│   ├── components/map/                 # EXTRACT from GISMap.jsx
│   ├── pages/
│   │   ├── AppBuilder.jsx              # REFACTOR — persist via API
│   │   ├── GISMap.jsx                  # REFACTOR — GeoJSON endpoints, PostGIS layers, context menus per level
│   │   ├── Dashboard.jsx               # REFACTOR — loading + error states
│   │   ├── MDMSMirror.jsx              # REFACTOR — proxy; no NaN%
│   │   ├── HESMirror.jsx               # REFACTOR — remove hard-coded fallback
│   │   ├── Reports.jsx                 # REFACTOR — MDMS EGSM proxy + scheduled reports
│   │   ├── OutageManagement.jsx        # EXTEND — real incident list from correlator
│   │   └── (existing)
│   ├── services/api.js                 # FIX — SSE auth header, axios baseURL via env, reconcilerAPI define
│   ├── auth/                           # add RBAC-aware route + menu guards
│   └── routes.tsx                      # register /map /reconciler /appbuilder
└── tests/
    └── e2e/demo_compliance/            # NEW Playwright tests mirroring backend tests
```

**Structure Decision**: Two projects, `backend/` + `frontend/`. Existing layout preserved. New modules slot under existing directories; no top-level package moves. Alembic migrations live under `backend/alembic/versions/`.

## Phased Implementation Plan

### Wave 0 — P0 Repo-Integrity (Days 1–2)

Gate A. Everything depends on this.

1. Restore `backend/app/models/meter.py` (recover from `.pyc` or git history or rewrite from seed references). Commit Alembic baseline that matches current dev DB schema (no data loss).
2. Restore `backend/app/schemas/*` (alarms, der, meter, simulation, sensor, auth, outage, report) — rewritten from endpoint imports.
3. Restore `frontend/src/App.jsx` with routes `/dashboard /map /alarms /der /energy /reports /hes /mdms /sensors /simulation /audit /showcase /reconciler /av-control /appbuilder /settings`.
4. Remove `create_all()` from backend lifespan; migrations only.
5. Define `reconcilerAPI` in `services/api.js`.
6. Move SSE JWT from query string to `Authorization` header.

Acceptance: a fresh container boots, Playwright smoke suite passes on all routes, no missing-file import errors.

### Wave 1 — SSOT Proxy Layer + Feature Flags (Days 3–5)

1. Add `SSOT_MODE` flag (strict/mirror/disabled) in config; gate every fallback.
2. Build `mdms_proxy.py` endpoints: `/api/v1/mdms/*` pass-through with httpx.AsyncClient; trace-context propagated.
3. Build `hes_proxy.py` for `/api/v1/hes/*` pass-through.
4. Rewrite `hes_client.py` and `mdms_client.py` with real URLs from env; httpx with 5 s timeout, 3 retries, circuit breaker.
5. Refactor `MDMSMirror.jsx`, `HESMirror.jsx`, `Dashboard.jsx` to consume proxy. Remove NaN%, remove hard-coded fallbacks, add skeleton/error components.
6. Add `GET /health` aggregating upstream status.
7. Secret loader for AWS Parameter Store / Secrets Manager (all placeholder credentials removed from `config.py`).

Acceptance: strict mode returns 502 on MDMS outage with banner; mirror mode falls back cleanly. No hardcoded numbers visible.

### Wave 2 — Live HES Command & Event Plumbing (Days 5–8)

1. Kafka consumer service: topics `hesv2.meter.events`, `hesv2.meter.alarms`, `hesv2.command.status`, `hesv2.sensor.readings`, `hesv2.outage.alerts1`, `hesv2.network.health`, `hesv2.der.telemetry`. DLQ topics per consumer.
2. Outbound commands: `POST /api/v1/meters/{s}/disconnect` forwards through HES, persists `command_id`, awaits Kafka status, updates meter row only on CONFIRMED.
3. FOTA job orchestration: upload image to S3, create HES job, poll progress, persist `fota_job_meter_status` rows.
4. Sensor history: drop `random.uniform`; read from `transformer_sensor_reading` fed by Kafka.
5. DER commands similarly routed through HES inverter-command endpoint (feature-flag `SMART_INVERTER_COMMANDS_ENABLED` default off outside dev).

Acceptance: Playwright test "disconnect 1 meter end-to-end" passes with real HES + simulator.

### Wave 3 — Outage + NTL + GIS + DER + Scenarios (Days 8–12)

1. Outage correlator service: N≥3 power-failure events, same DTR, window=120s → open `outage_incident`; restoration detection; SAIDI/SAIFI/CAIDI materialised view.
2. Outage map: incident markers, polygon for affected DTRs, right-click dispatch-crew → WFM hook (MDMS-T6 feature flag).
3. GIS refactor: GeoJSON endpoints for feeder lines, DTR points, pole points, meter points from PostGIS. MapLibre switch optional; Leaflet + vector overlays OK for now. Context menus per zoom level.
4. NTL page: MDMS NTL when enabled, else event-correlation fallback; suspicion score column; energy-balance gap per DTR.
5. DER dashboards: PV, BESS, EV, distribution-room — proper pages with aggregate + per-asset; live telemetry via SSE.
6. Scenarios: wire `/api/v1/simulation/:name/start` → simulator REST; step UI; ensure smart-inverter curtail, EV curtail, FLISR isolation buttons round-trip through HES.

Acceptance: Playwright demo-compliance tests pass for User Stories 4, 9, 15, 16, 17, 18, 19, 20.

### Wave 4 — Alerts, AppBuilder, Reports, RBAC, Notifications (Days 12–16)

1. Notification providers live (SMTP/SES, Twilio, MS Teams webhook, Firebase). Credentials via Secrets Manager. Per-user + per-alarm-subscription preferences. Quiet hours, escalation.
2. Virtual object groups + rule engine: persisted rules evaluated against event stream; firing → notifications + action dispatch.
3. AppBuilder: persistent apps/rules/algorithms with versioning + preview + publish workflow. Python-sandbox algorithm runner (Pyodide in frontend or remote worker; decide in research.md).
4. Reports: proxy to MDMS EGSM endpoints; scheduled reports worker (Celery or APScheduler) emailing PDFs; saved configurations per user.
5. RBAC gating: menu + route guards in frontend; FastAPI dependency per endpoint; per-role test matrix.
6. Data Accuracy console: aggregates HES + MDMS + CIS last-seen-timestamps per meter.

Acceptance: User Stories 11, 13, 23, 24 green; RBAC Playwright tests green.

### Wave 5 — E2E Integration Tests + Demo Polish + Load Test (Days 16–19)

1. Write one integration test per user story under `backend/tests/integration/demo_compliance/`.
2. Write one Playwright test per user story under `frontend/tests/e2e/demo_compliance/`.
3. Synthetic probe suite running every 5 min on dev.
4. Load test with k6 / Locust: 50 concurrent sessions, SSE stability.
5. Security review (/security-review skill) on PR bundle before demo.
6. Demo dress rehearsal 2026-04-20; triage findings into Wave 5.5 hotfixes.

Acceptance: 24/24 E2E pass; SC-001 through SC-008 satisfied.

### Wave 6 — Post-Demo Hardening (Days 19+)

Out-of-scope for demo-day but committed to same branch:
- Multi-AZ Postgres + read replica.
- Full i18n pass (en, zu, st, af).
- Pen test remediation backlog.
- Video-wall layout manager.
- Full IEC 61968/61970 CIM import.

## Upstream Dependencies on MDMS (tracked in `mdms-todos.md`)

- MDMS-T1: Inclining-block + seasonal tariff in billing engine.
- MDMS-T2: NTL service — implement from empty stub.
- MDMS-T3: Load profile by class MV.
- MDMS-T4: Auto register readback after token accepted.
- MDMS-T5: Inverter command passthrough (via HES) — MDMS command-exec routing.
- MDMS-T6: WFM hook for dispatch-crew from outage.
- MDMS-T7: 4 broken EGSM endpoints — replace via mdms-analytics-service cutover (already speced as 017).

EMS ships with feature flags so each MDMS TODO lands independently.

## Observability Contract

Every user story maps to:

- An `x-user-story-id` HTTP header propagated through spans (e.g. `018.US-4`).
- An `audit()` event published with `action_type`, `action_name`, `user_id`, `trace_id`.
- Grafana saved views per story linking trace → audit row → MDMS source rows.

## Risk Register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | MDMS TODOs not landed in time | Feature gaps on demo day | Feature flags; narrate roadmap items; mirror-mode fallback for MDMS-T2/T5 |
| 2 | HES Kafka auth instability (SASL/SCRAM from CNCF incident) | Event consumption blocked | Use mirror mode; pre-test with real creds; run-book for kafka auth |
| 3 | PostGIS migration data loss | GIS regressions | Migration in Wave 3 has dry-run step; rollback plan in data-model.md |
| 4 | E2E flakes against dev simulator | False red before demo | Playwright retries ×2; dev preset frozen 2 days before |
| 5 | Repo freeze violation on `avdhaan_v2` / `mdms-reports` | Breaks policy | This spec touches neither; guard CI to fail on any attempt to modify |
| 6 | Prometheus CrashLoop in dev | Observability blind | Fixed in Wave 5 pre-flight; rollback to vendor Prom if needed |
| 7 | Scope creep during Wave 5 | Demo slip | Feature freeze at Wave 4 end; Wave 5 is tests + polish only |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| SSOT_MODE feature flag with 3 values | Demo day needs fallback ability while production wants strict | Binary flag insufficient — dev needs a fully-offline option too |
| Per-integration feature flag in addition to SSOT_MODE | Integrations mature at different rates | Single flag would force all-or-nothing rollout |
| EMS-owned outage correlator (not MDMS) | MDMS NFMS integration exists but has its own roadmap | Tight coupling to MDMS NFMS would couple two release cadences |
