# Dress Rehearsal Protocol — Polaris EMS Demo (spec 018 W5.T52)

**Scheduled**: 2026-04-20 (T-1 day)
**Demo date**: 2026-04-21, Megawatt Park, Johannesburg
**Environment**: dev EKS via https://vidyut360.dev.polagram.in + on-stage laptop
**Duration budget**: 90 min rehearsal + 30 min triage = 2 hours

---

## 0. Roles for rehearsal

| Role | Owner | Responsibility |
| --- | --- | --- |
| Presenter | _TBD_ | Drives UI, narrates demo |
| Scenario driver | _TBD_ | Triggers simulator presets, advances steps |
| Ops | _TBD_ | Watches Grafana dashboards, restarts pods if needed |
| Observer | _TBD_ | Logs every issue into the rehearsal log (below) |
| Timekeeper | _TBD_ | Keeps total walk-through under 60 min |

---

## 1. Pre-flight — T-24h (run on 2026-04-20 morning)

Complete every item before starting the scripted walk. Any un-ticked item
is a blocker.

### 1.1 Cluster & pod health

- [ ] `kubectl -n mdms get pods | grep -E 'CrashLoopBackOff|Error'` returns **empty** for `mdms-analytics`, `mdms-sat`, `prometheus`.
- [ ] `kubectl -n polaris-ems get pods` all `Running` with `0` restarts in the last 2h.
- [ ] `kubectl -n observability get pods` — OTel Collector DaemonSet, Tempo, Loki, Prometheus, Grafana all `Running`.
- [ ] `kubectl -n polaris-ems get cronjob polaris-ems-synthetic-probe` exists, last successful run < 10 min ago.
- [ ] Synthetic probes dashboard in Grafana shows ≥ 99% pass rate over the last 3h.
- [ ] HES routing service image is the current stage build (not the 2026-04-13 CNCF-incident rebuild).

### 1.2 Data / simulator state

- [ ] **Simulator preset locked with Ops** — written confirmation in Slack that `#smoc-demo-prep` preset won't be reseeded between rehearsal and demo.
- [ ] `solar_overvoltage`, `ev_fast_charging`, `peaking_microgrid`, `network_fault` scenarios return 200 from `GET /api/v1/simulation/scenarios`.
- [ ] Seed meters for each scenario exist in HES, MDMS CIS, and MDMS VEE (verify one meter per scenario by MDMS `/consumers/{id}` returning a row).
- [ ] VEE tab shows non-NaN totals for today (US-5 acceptance).
- [ ] Prepaid register freshness ≤ 60 s on the three demo accounts (US-10).

### 1.3 Integration readiness

- [ ] **MDMS-T7 analytics-service cutover status** checked — confirm whether EMS should consume `mdms-analytics-service` MVs or fall back to `mdms-reports`; record current `VITE_MDMS_REPORTING_URL` and backend `MDMS_BASE_URL` in rehearsal log.
- [ ] `SSOT_MODE=strict` deployable — run a 5-min strict run and watch Grafana for 5xx spikes; revert to `mirror` only if red.
- [ ] All 24 `demo_compliance/` integration tests pass 3× in a row (`pytest backend/tests/integration/demo_compliance/ -x --count=3` — the `pytest-repeat` plugin).
- [ ] All 24 Playwright specs in `frontend/tests/e2e/demo_compliance/` pass 3× in a row.
- [ ] `/security-review` checklist completed and signed off (see `security-review.md`).
- [ ] k6 smoke run green: `k6 run ops/loadtest/k6-scenarios.js --env SMOKE=1` — zero threshold breaches.

### 1.4 Hardware / logistics

- [ ] Demo laptop fully charged, backup HDMI cable in bag.
- [ ] Demo laptop has **local docker-compose** copy of Polaris EMS built and tested (disaster fallback).
- [ ] Mobile hotspot on evaluator-proof carrier (MTN + Vodacom tested).
- [ ] Evaluator score-sheet PDF on local disk + printed copies.

---

## 2. Rehearsal run order — 24 user stories (per spec §User Scenarios)

Walk in the order below. For each story record in the rehearsal log: (a)
actual data source observed, (b) UI state, (c) any deviation from expected,
(d) fallback narration used if deviation occurred.

| # | Demo item | User Story | Route | Data source expected | UI state expected | Fallback narration if red |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | #4 | US-1 Real-time dashboard | `/dashboard` | MDMS + HES via proxies, SSE live | Six KPI tiles populated, source timestamp ≤ 60s | "We'd normally see live SSE here; let's switch to the detail view." |
| 2 | #4 #5 | US-2 Meter commands | `/meters/<id>` | HES cmd via mdms-cmd-exec | Disconnect → EXECUTED toast in ≤ 60s | Queue visible, "command queued in EMS, HES ack deferred" |
| 3 | #5 | US-3 FOTA | `/fota` | HES firmware service | Per-meter progress table ticking | Show pre-recorded progression |
| 4 | #4 #7 #24 | US-4 Outage + GIS | `/outages` + `/map` | Outage correlator | Incident auto-opens with GIS pin in ≤ 90s | Manually open incident with known id |
| 5 | #6 | US-5 VEE | `/mdms` VEE tab | MDMS VEE DB | Non-NaN totals, rule breakdown | "VEE service present, pipeline ran at HH:MM" |
| 6 | #6 | US-6 Tariff | `/mdms/tariffs` | MDMS tariff schedules | Schedule table + ToU | Show 2-month cached view |
| 7 | #6 | US-7 CIS/GIS enrichment | `/meters/<id>` | MDMS CIS + GIS | Consumer, hierarchy, coordinates | Last-known snapshot |
| 8 | #6 #9 | US-8 Load profiles | `/analytics/load-profiles` | MDMS load curves | p10/p50/p90 bands | Static PNG export |
| 9 | #4 #6 | US-9 NTL | `/ntl` | MDMS NTL or EMS correlation fallback | Suspect list with score | Banner "event correlation only" |
| 10 | #7 | US-10 Prepaid | `/prepaid/<account>` | MDMS prepaid registers | 13 registers, recharge flow | Show token log, narrate readback |
| 11 | #10 | US-11 Alert rules | `/alarms/rules` | EMS rules + notifications | Rule fires in ≤ 60s, channel delivered | Fire rule manually from test harness |
| 12 | #11 | US-12 Data quality | `/data-accuracy` | HES, MDMS, CIS timestamps | Per-meter badges | Static CSV export |
| 13 | #12 | US-13 Supplier registry | `/admin/suppliers` | MDMS supplier_registry | Failure-rate %, MTBF | Skip if admin role unavailable |
| 14 | #13 #14 | US-14 Audit / consumption | `/reports/energy-audit` | MDMS EGSM reports | Table + chart + CSV export | Show pre-generated CSV |
| 15 | #15–18 | US-15 DER dashboards | `/der/pv`, `/der/bess`, `/der/ev`, `/distribution` | HES sensor readings | Live curves, aggregate | Static preset (sunny day) |
| 16 | #20 | US-16 Feeder DER overlay | `/feeders/<id>` | EMS + HES | Voltage + DER overlay | Reverse-flow banner |
| 17 | #21 | US-17 Solar overvoltage | `/simulation/solar_overvoltage` | Simulator + algorithm | Curtailment dispatched in ≤ 7 steps | Step-through manually |
| 18 | #22 | US-18 EV fast charging | `/simulation/ev_fast_charging` | Simulator | Overload + curtailment | Narrate forecast |
| 19 | #23 | US-19 Microgrid reverse flow | `/simulation/peaking_microgrid` | Simulator | Add BESS mid-run integrated | Pre-added BESS preset |
| 20 | #24 | US-20 Fault FLISR | `/simulation/network_fault` | Simulator + outage correlator | Incident in ≤ 90s, FLISR steps | Canned incident walkthrough |
| 21 | #25 | US-21 DCU sensors | `/sensors` | HES sensor readings | Threshold edit propagates | Read-only view |
| 22 | #26 | US-22 GIS zoom | `/map` | PostGIS | Context menu per level | Skip to DTR-level |
| 23 | #7 #19 #27 | US-23 Custom dashboards | `/dashboards/builder` | EMS AppBuilder | Saved layout, scheduled report | Show saved layout only |
| 24 | #27 | US-24 App/rule authoring | `/appbuilder` | EMS rules + sandbox | Draft → preview → publish | Show a published rule only |

Each story budgeted at ~2 min on demo day; rehearsal allows 3 min to
collect evidence.

---

## 3. Smoke assertions (run once before the walk)

```bash
# Backend integration tests (24 stories)
cd backend && pytest tests/integration/demo_compliance/ -q

# Playwright (24 stories)
cd frontend && npx playwright test tests/e2e/demo_compliance/ --reporter=line

# k6 smoke
k6 run ops/loadtest/k6-scenarios.js --env SMOKE=1 \
  --env BASE_URL=https://vidyut360.dev.polagram.in --env TOKEN=$POLARIS_JWT

# Probe dashboard
open "https://grafana.dev.polagram.in/d/polaris-ems-probes"
```

---

## 4. Observed-issue log template

Copy this into a fresh file `changelogs/2026-04-20-rehearsal.md` during the
rehearsal. One row per issue.

```markdown
| Time  | US   | Severity | Observed | Expected | Root cause | Fix / workaround | Owner |
| ----- | ---- | -------- | -------- | -------- | ---------- | ---------------- | ----- |
| 10:07 | US-5 | P1       | NaN% ... | %age     | ...        | ...              | ...   |
```

Severity:
- **P0** — blocks demo day entirely, must fix or script around before 20:00.
- **P1** — visible failure, must fix before demo or have a confident fallback narration.
- **P2** — cosmetic, can ship as-is.
- **P3** — post-demo backlog.

---

## 5. Rehearsal exit criteria

The rehearsal is signed off **only when all are true**:

- [ ] 24/24 user stories walked end-to-end with live data (no skips).
- [ ] Zero P0 items open.
- [ ] ≤ 2 P1 items open, each with a written fallback narration approved by the presenter.
- [ ] `/security-review` checklist has zero P0/P1 findings.
- [ ] Grafana synthetic-probe dashboard green ≥ 99% for the 1h spanning the rehearsal.
- [ ] k6 smoke finished with no threshold breaches.
- [ ] All P1 findings have an owner + planned fix window before 21:00 on 2026-04-20.

Failure to meet these triggers a second rehearsal slot on the morning of
2026-04-21 — timebox 45 min, only the failing stories re-walked.

---

## 6. Rehearsal sign-off

- Presenter: _________________________  Date: __________
- Ops: _____________________________  Date: __________
- Observer (captain's log writer): _____________  Date: __________
- Go / No-go decision logged in `demo-day.md`.
