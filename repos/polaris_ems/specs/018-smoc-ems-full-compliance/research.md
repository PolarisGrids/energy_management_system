# Research: Spec 018 Pre-Flight

**Date**: 2026-04-18
**Purpose**: Establish actual codebase state before execution so plan.md + tasks.md reflect reality (not the pre-restoration GAPS.md snapshot).

## Finding 1 — Wave 0 P0 Restorations Are Already Landed

GAPS.md (dated 2026-04-18) was captured before today's restoration commits. Direct inspection on branch `017-egsm-reports-postgres` shows:

| GAPS.md claim | Actual state (2026-04-18 16:49) | Action in Wave 0 |
|---|---|---|
| `backend/app/models/meter.py` missing | **Present** (4153 B). Exports `Meter`, `Transformer`, `Feeder`, `MeterStatus`, `RelayState`, `MeterType`, `MeterClass`. 26 meter columns including relationships to Supplier, TransformerSensor | Skip W0.T3 — verified |
| `backend/app/schemas/*` empty | **Present**: alarm.py, auth.py, der.py, meter.py, sensor.py, simulation.py (Pydantic v2, `from_attributes=True`) | Skip W0.T4 — verified; minor extension needed for outage/report/app_builder schemas in later waves |
| `frontend/src/App.jsx` missing | **Present** (3815 B). React Router v6 with 21 routes; `AppLayout`, `PrivateRoute`, `ProtectedRoute` wrappers | Skip W0.T6 — verified |
| `alembic/versions/` empty | **5 migrations present**: `20260418_0001_baseline`, `0002_metrology_tables`, `01_postgis_gis`, `02_outage_notifications`, `03_align_phase_a_015` | Skip W0.T5 — verified; `create_all()` no longer in `main.py` lifespan |
| `/map`, `/reconciler`, `/appbuilder` routes unreachable | Routes registered as `/gis`, `/reconciler`, `/app-builder` (hyphen). Previously-cited paths were guesses. | Accept route names as-is; update spec references |
| `reconcilerAPI` undefined | **Defined** line 129 of `services/api.js` | Skip W0.T7 — verified |
| `HESMirror.jsx` hard-wired 183/42/15/91.4% | **Not found** on current file — fallbacks removed | Skip W0.T9 — verified |
| `MDMSMirror.jsx` NaN% | **Fixed** — `totalProcessed > 0 ? … : '—'` at line 35 | Skip W0.T10 — verified |
| No `components/ui/` | **Present**: 10 components (Badge, Button, Card, ChartWrapper, EmptyState, ErrorBoundary, KPI, Modal, Skeleton, Spinner) | Skip W0.T13 — verified; Toast is the one remaining to add |
| SSE `?token=` | **Partial** — header path added; legacy `?token=` retained as backward-compat fallback in sse.py line 22 | W0.T8: deprecate `?token=` with warn-log, target removal Wave 1 |

**Net impact**: Wave 0 collapses from 15 tasks to ~3 residual tasks. Start date effectively = today; Wave 1 can begin immediately.

## Residual Wave 0 Work

- **W0.T8 (revised)**: Emit deprecation warning when `?token=` used; metric `sse_query_token_requests_total`. Hard-remove in Wave 1 once no-one calls it.
- **W0.T9 (revised)**: Add `Toast` component to `components/ui/` (the one component still missing).
- **W0.T14**: Playwright smoke against all 21 registered routes — confirm no 404s, no console errors on a clean deploy.
- **W0.T15**: Gate A checklist sign-off (`checklists/p0-gaps.md`) now a confirmation pass rather than a work list.

## Finding 2 — Uncommitted Work On Current Branch

`git status` on branch `017-egsm-reports-postgres` shows uncommitted modifications:
- `backend/app/api/v1/endpoints/mdms_mirror.py`
- `frontend/src/pages/AuditLog.jsx`
- `frontend/src/pages/MDMSMirror.jsx`
- `frontend/src/services/api.js`

These relate to spec 017 egsm-reports-postgres work-in-progress; do NOT touch them. Branch `018-smoc-ems-full-compliance` must be cut from `eskom_dev` (not from the in-flight 017 working tree) to avoid entanglement.

## Finding 3 — Phase-B Completion State

Recent merge commit `9234686 merge: Phase B (013/014/015/016)` confirms these four phase-b tracks are landed:
- 013 metrology ingest
- 014 GIS PostGIS
- 015 RBAC + UI lib
- 016 notifications + outage

Spec 018 builds on top of these. In particular:
- PostGIS is ready for GIS refactor (Wave 3).
- RBAC framework exists; Wave 4 RBAC tasks become refinement rather than greenfield.
- Notifications framework partially in place; Wave 4 provider wiring remains.
- Outage model likely has baseline; need to confirm correlator design.

## Finding 4 — MDMS Reachability from Dev EKS

Previous compliance exploration confirmed `mdms-api`, `mdms-cis`, `mdms-vee`, `mdms-reports`, `mdms-prepaid`, `mdms-billing`, `mdms-cmd-exec` all 1/1 Ready on dev-cluster. Two concerning pods:
- `mdms-analytics-service` CrashLoopBackOff (5 restarts)
- `mdms-sat-backend` CrashLoopBackOff (876 restarts/3d — missing `otel-common-js/src/setup` module)

Both are MDMS-owned and require Umesh approval to fix. Tracked under MDMS-T7 (analytics cutover) in `mdms-todos.md`.

## Finding 5 — HES Readiness

10 HES-v2 pods Running: routing, command-dispatcher, command-execution, data-acquisition, parsing (DLMS + others), RF firmware upgrade, pull-backend. Multi-HES support claims in memory are not backed by code (per earlier HES audit). For spec 018 assume single HES instance.

Kafka topic naming mismatch: HES code uses generic `meter-events`, `meter-data-raw`, `meter-commands`. `hesv2.*` prefix is a new convention introduced by spec 018 contracts and simulator spec 001. **Decision**: request HES team to dual-publish (old + new topic names) during transition, OR EMS consumer subscribes to existing topic names. This is a crossteam coordination item before Wave 2.

## Finding 6 — Kafka Auth Baseline

SASL/SCRAM credentials documented in memory `feedback_hes_pipeline_policy.md` and the CNCF Linkerd incident postmortem. Creds live in AWS Secrets Manager. Simulator spec 001 Wave 0 hardens the path; EMS Wave 2 follows the same pattern.

## Finding 7 — Existing Seed Data is Rich Enough for Demo

`scripts/seed_data.py` already generates 201k meter readings, 9 ZAR TOU tariffs, 60 NTL suspects, 75 PQ zones, 180 audit events across 3 users, 5 scenarios + 40 steps, 4 hardcoded DER assets, 3 feeders, 11 transformers, 107 meters.

For demo day the plan is: simulator takes over data generation, seed_data.py reduced to DER bootstrap + scenario fixtures only (per spec §Seeding Contract). However, during Wave 1–2 development, keeping seed_data.py functional makes local dev fast. Decision: keep seed_data.py operational through Wave 3; remove metering/tariff/VEE/NTL seeding in Wave 4 alongside SSOT_MODE=strict rollout.

## Finding 8 — Observability Shape

OTel wiring already present (`otel_common`); LGTM stack on dev EKS (observability namespace). Prometheus CrashLoop (1067 restarts/12d) is the one gap. Wave 5 covers pre-demo remediation.

## Decisions Locked

1. **Branch creation**: `git checkout eskom_dev && git pull && git checkout -b 018-smoc-ems-full-compliance` — do NOT branch from `017-egsm-reports-postgres`.
2. **Wave 0 collapses to ~3 residual tasks**; update tasks.md accordingly.
3. **Route names**: spec internal references updated — use `/gis` (not `/map`), `/app-builder` (not `/appbuilder`). Spec 018 already refers to these with hyphens in integration-test-matrix.md Playwright paths.
4. **HES Kafka topic naming**: coordinate with HES team; dual-publish period during transition. Captured as task W2.T0 prerequisite.
5. **MDMS-T7 (analytics-service CrashLoop)**: escalate to Umesh today — unblocks 4 broken EGSM report endpoints needed for User Story 14.
6. **No changes to `avdhaan_v2` or `mdms-reports`** — demo freeze respected.

## Unknowns To Resolve Before Wave 2

- [ ] HES Kafka topic naming negotiation (EMS team ↔ HES team).
- [ ] AWS Secrets Manager paths for SMTP/Twilio/Teams/Firebase — ops provisioning.
- [ ] Prometheus CrashLoop root-cause fix (12-day regression).
- [ ] Outage model schema from phase-b/016 — needs inspection before Wave 3 correlator wiring.
- [ ] RBAC role matrix from phase-b/015 — needs inspection before Wave 4 role-gating tests.
- [ ] Algorithm sandbox decision (Pyodide in browser vs remote worker) — research item for Wave 4.

## Appendix — Route Inventory (Current)

From `frontend/src/App.jsx`:

| Route | Component | Guard |
|---|---|---|
| `/login` | Login | Public |
| `/` (layout) | AppLayout + nested | PrivateRoute |
| `/gis` | GISMap | Private |
| `/alarms` | AlarmConsole | Private |
| `/der` | DERManagement | Private |
| `/energy` | EnergyMonitoring | Private |
| `/hes` | HESMirror | Private |
| `/mdms` | MDMSMirror | Private |
| `/reports` | Reports | Private |
| `/av-control` | AVControl | Private |
| `/app-builder` | AppBuilder | Private |
| `/showcase` | SMOCShowcase | Private |
| `/sensors` | SensorMonitoring | Private |
| `/lpu` | LPUPrepayment | Private |
| `/reconciler` | Reconciler | Private |
| `/audit` | AuditLog | ProtectedRoute(perm) |
| `/simulation` | SimulationPage | ProtectedRoute(perm) |
| `/system-management` | SystemManagement | ProtectedRoute(perm) |
| `/admin/users` | AdminUsers | ProtectedRoute(admin) |
| `/outages` | OutageManagement | ProtectedRoute(perm) |
| `/outages/:id` | OutageDetail | ProtectedRoute(perm) |
| `*` | Redirect `/` | — |

Spec 018 requires registering additional routes in later waves: `/ntl` (Wave 3), `/distribution` (Wave 3), `/data-accuracy` (Wave 4).
