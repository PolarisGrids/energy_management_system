# Demo-Day Go/No-Go Checklist — Polaris EMS (spec 018 W5.T53)

**Date**: 2026-04-21 (Tuesday)
**Venue**: Megawatt Park, Johannesburg
**Call time**: 06:00 SAST on-site / 09:30 SAST IST-origin Ops stand-by
**Demo slot**: TBD — Ops will set T-0 in the rehearsal log

This is the last gate before the demo; every item must be ticked or
explicitly waived with a written fallback narration.

---

## 0. Roles (mirrors rehearsal)

| Role | Owner | On-site? | Responsibility |
| --- | --- | --- | --- |
| Presenter | _TBD_ | Yes | Drives UI + narration; owns the story |
| Scenario driver | _TBD_ | Yes | Triggers simulator presets on cue |
| Ops | _TBD_ | No (remote IST) | Watches Grafana, restarts pods, drives bail-outs |
| Observer | _TBD_ | Yes | Takes notes, times each story |

The pattern mirrors the evaluator sheet structure (presenter + scorer +
note-taker + ops).

---

## 1. Morning-of steps (T-2h to T-0)

### 1.1 Smoke suite — 8 fastest tests (< 5 min)

Cherry-picked from `backend/tests/integration/demo_compliance/`; these
validate the demo-critical paths without the long scenario timers.

```bash
cd backend
pytest tests/integration/demo_compliance/ -q -k \
  "test_us01_dashboard or \
   test_us02_meter_command_rc_dc or \
   test_us04_outage_correlation or \
   test_us05_vee_totals_not_nan or \
   test_us07_cis_gis_enrichment or \
   test_us10_prepaid_registers or \
   test_us11_alert_rule_fires or \
   test_us21_dcu_sensor_read"
```

- [ ] Smoke suite: 8/8 pass in < 5 min.
- [ ] Playwright smoke (same 8 stories): `npx playwright test tests/e2e/demo_compliance/ --grep "@smoke"` green.

### 1.2 Final deploy verification

- [ ] `kubectl -n polaris-ems get pods` — every pod Running, restart count 0 in last 2h.
- [ ] `kubectl -n polaris-ems get cronjob polaris-ems-synthetic-probe` — last successful run < 10 min; last 12 runs green.
- [ ] `GET https://vidyut360.dev.polagram.in/api/v1/health` returns `{"status":"ok"}` AND all upstream sub-keys `ok`.
- [ ] Grafana **Polaris EMS — Synthetic Probes** dashboard: pass rate ≥ 99.5% over last 2h.
- [ ] Grafana **Service Overview**: no red service map edges; Kafka consumer lag < 1000 on all topics.
- [ ] `SSOT_MODE` in deployed ConfigMap is the value agreed in rehearsal (default: `strict`; fallback: `mirror`).
- [ ] Simulator preset confirmed not reseeded overnight (Slack confirmation in `#smoc-demo-prep`).

### 1.3 On-stage setup

- [ ] Laptop connected to venue network AND hotspot as standby; DNS resolves `vidyut360.dev.polagram.in`.
- [ ] Demo browser profile cleared of stale localStorage, JWT freshly minted (valid for ≥ 6 h).
- [ ] Evaluator score sheet open in separate window.
- [ ] Local docker-compose stack built and spot-checked (`docker compose up` then hit `/api/v1/health`).

### 1.4 Backup talking points for any red test

For each user story that went red in rehearsal, a written fallback must
be pinned here before 08:00. Template:

```markdown
### US-<n> fallback — <title>
- What broke: ...
- What we show instead: ...
- Exact words: "..."
- How long this adds: ...
```

_Paste from `changelogs/2026-04-20-rehearsal.md` findings with P1 severity
and fix status != `fixed`._

---

## 2. Go / No-go decision (T-30 min)

Tick every criterion before calling "go". If ≥ 1 is red, escalate to
engineering lead for an override decision (in writing).

- [ ] Smoke suite 8/8 green.
- [ ] Synthetic-probe dashboard pass rate ≥ 99.5% for last 2h.
- [ ] Zero P0 items on the rehearsal issue log.
- [ ] Every P1 rehearsal item has either (a) a deployed fix verified in smoke, or (b) a written fallback approved by the presenter.
- [ ] Security review sign-off on file — no P0/P1 findings.
- [ ] k6 smoke run this morning: no threshold breaches.
- [ ] Ops on call and reachable on the shared channel.
- [ ] Laptop battery ≥ 80%; charger plugged in.
- [ ] Backup network path tested (hotspot swap drill in < 30 s).

**Go / No-go decision**: ________  **Signed**: ________  **Time**: ________

---

## 3. Bail-out procedures (if something breaks during demo)

Triggered by the Ops observer calling a **code word** over the comms
channel. The presenter acknowledges verbally ("let's switch the view
here…") and executes the matching fallback.

### 3.1 Simulator fails (scenarios endpoint 5xx or stuck)

- **Code word**: *"preset"*
- **Action**: Switch the narration from live-scenario to MDMS cached data.
  - Open `/mdms` tabs — VEE, Tariff, EGSM reports — as live read sources.
  - Skip the three scenario-driven stories (US-17, US-18, US-19, US-20) and
    narrate them from the rehearsal recording shown as a pre-captured
    screen-capture on a second browser tab.
- **Recovery**: Ops runs `kubectl -n polaris-ems rollout restart deploy/simulator` and pings presenter when green.

### 3.2 MDMS proxy fails (mdms-api 5xx or upstream timeouts)

- **Code word**: *"mirror"*
- **Action**: Ops flips `SSOT_MODE=mirror` via Helm values rollout:
  ```bash
  helm -n polaris-ems upgrade polaris-ems charts/polaris-ems \
      -f charts/polaris-ems/values-dev.yaml \
      --set backend.env.SSOT_MODE=mirror --reuse-values
  ```
  Rollout ~60 s. In the meantime the presenter stays on HES/DER/GIS/AppBuilder
  stories (US-3, 15, 16, 21, 22, 23, 24) which do not depend on MDMS.
- **Recovery**: Once `strict` upstream returns, flip back via same mechanism
  between sessions — not mid-demo.

### 3.3 Dev EKS cluster fails (ingress 5xx / node pressure / total outage)

- **Code word**: *"hotspot-local"*
- **Action**: Presenter swaps the browser tab to `http://localhost:5173`
  (frontend) + `http://localhost:8000` (backend), both running from the
  pre-built docker-compose stack on the laptop. Narrate:
  *"Let me show you the same screen running locally on this machine so we
  stay in the flow."* Demo continues on local seeded data; all 24 routes
  render, some with `SSOT_MODE=disabled` fallback banners which we
  explicitly call out as expected during isolation.
- **Recovery**: Ops triages EKS in parallel; not time-critical to swap back during this demo slot.

### 3.4 Single pod crash (e.g., backend OOM)

- **Code word**: *"bounce"*
- **Action**: Presenter pivots to a GIS / map story (US-22) which is
  front-end-heavy. Ops runs `kubectl -n polaris-ems rollout restart deploy/polaris-ems-backend`;
  recovery ~30 s.

### 3.5 Network drops (venue Wi-Fi)

- **Code word**: *"hotspot"*
- **Action**: Presenter pauses ("let me pull up the map while the network
  reshuffles"), swaps to mobile hotspot within 30 s, resumes.

---

## 4. Post-demo (immediate)

- [ ] Observer's log saved to `changelogs/2026-04-21-demo.md`.
- [ ] Evaluator score sheet photographed and archived in `.planning/specs/018/demo-day-scores.pdf`.
- [ ] Any P0/P1 regressions filed as spec 018 Wave 5.5 hotfix items.
- [ ] SSOT mode restored to the agreed post-demo value.
- [ ] Synthetic probe CronJob left running (continuous monitoring).

---

## 5. Sign-off

- Presenter: _________________________  Time: __________
- Ops: _____________________________  Time: __________
- Observer: _________________________  Time: __________
- Outcome: [ ] Demo successful  [ ] Demo with issues (see log)  [ ] Demo aborted
