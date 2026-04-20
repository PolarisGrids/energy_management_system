# Integration Test Matrix — 24 Demo Stories E2E

**Acceptance bar for Spec 018**: every user story below has one pytest integration test (`backend/tests/integration/demo_compliance/`) and one Playwright E2E test (`frontend/tests/e2e/demo_compliance/`). A green run is demo day go.

Harness: Playwright existing 102-test suite (`reference_e2e_testing.md`) + TOTP MFA login + HTTPS report server on :9323. Pytest integration uses real dev EKS services plus simulator preset `demo-21-apr-2026`.

## Data Flow Legend

```
simulator → HES Kafka topic → HES DB → MDMS ingest → MDMS DB → MDMS API → EMS proxy → EMS UI
         ↘                                                                          ↗
           HES DB                                                            EMS Kafka consumer
                  ↘ EMS command (out) → HES routing → HES Kafka (status) → EMS state → EMS UI
```

## Matrix

| # | Story (demo point) | Simulator trigger | Observation point (E2E assertion) | Data source for assertion |
|---|---|---|---|---|
| 1 | Real-time dashboard (#4) | preset bootstrap; 10 meters flipped offline | `/dashboard` KPI "Offline Meters" = 10 within 30 s; banner hidden; timestamp ≤ 60 s | HES Kafka `hesv2.meter.events` → EMS cache; MDMS `meter_status_mv` cross-check |
| 2 | RC/DC command (#4, #5) | simulator listens for commands | Dispatch disconnect on meter S123; Playwright waits for meter row `relay_state=OPEN`; Kafka `hesv2.command.status` shows CONFIRMED | EMS `command_log` + HES Kafka + MDMS `command_execution_log` audit |
| 3 | FOTA progress (#5) | simulator accepts firmware job | Upload firmware, target 20 meters; per-meter progress table populates; 18+ APPLIED within 3 min | EMS `fota_job_meter_status` + HES `firmware-distribution` |
| 4 | Outage correlation (#4, #7, #24) | scenario `network_fault` | `/map` shows new outage incident within 90 s; affected_count = 20; timeline opens | EMS `outage_incident`; HES Kafka `hesv2.outage.alerts1`; compared to MDMS NFMS if online |
| 5 | VEE pipeline view (#6) | preset generates 1000 reads with 5% fail, 5% estimated | `/mdms` VEE tab shows 90%/5%/5% split; no `NaN%`; per-rule breakdown | MDMS `blockload_vee_validated` direct query + EMS proxy match |
| 6 | Tariff engine view (#6) | tariff config with TOU + (MDMS-T1 if landed) inclining | `/mdms/tariffs` renders schedules; meter billing determinants match MDMS payload | MDMS `/tariffs`, `/billing-determinants` proxied |
| 7 | CIS/GIS enrichment (#6) | preset seeds CIS + GIS | Search meter S123; detail page shows consumer + hierarchy + coords | MDMS `/cis/consumers`, `/gis/layers` |
| 8 | Load profiles by class (#6, #9) | preset generates typical-day curves | `/energy` load-profile chart shows p50 (p10/p90 if MDMS-T3) | MDMS `load_profile_by_class_half_hour` MV |
| 9 | NTL dashboard (#4, #6) | inject 5 theft cases per type | `/ntl` shows them within 15 min with correct cause | EMS event-correlator + MDMS NTL (if MDMS-T2) |
| 10 | Prepaid panel (#7) | recharge R100 on prepaid meter | Within 60 s EMS shows updated 13-register values | MDMS `/prepaid/registers` (readback from MDMS-T4 or EMS polling) |
| 11 | Alert rules & subscriptions (#10) | rule "DTR load > 80%" created; DTR driven above | SMS + email + push delivered within 60 s | EMS `notification_delivery` + stub providers' receipts |
| 12 | Data accuracy console (#11) | 10 meters offline 2 h | Data Accuracy tab flags them with "HES delay > 1h" badge | EMS `source_status` computed from HES/MDMS/CIS timestamps |
| 13 | System mgmt (#12) | seeded suppliers | `/system-mgmt` shows per-supplier performance | EMS `supplier_performance_mv` |
| 14 | Consumption queries & reports (#13, #14) | preset data for April | `/reports` Run Energy Audit Monthly; rows match MDMS | MDMS `/egsm-reports/energy-audit/monthly-consumption` |
| 15 | PV / BESS / EV / Distribution dashboards (#15–#18) | preset + sunny-day curve | Aggregate + per-asset numbers match simulator emissions ±2% | EMS `der_telemetry` via `hesv2.der.telemetry` |
| 16 | DER situational awareness (#20) | scenario ramps PV + EV | Feeder view shows voltage profile + DER overlay; reverse flow banner when net < 0 | EMS feeder view + Kafka-fed telemetry |
| 17 | Solar over-voltage curtailment (#21) | scenario `solar_overvoltage` | Voltage ≤ 1.05 pu within 7 steps; each inverter gets `curtail` command visible in HES command log | EMS sim panel + HES Kafka + simulator telemetry |
| 18 | EV fast-charging + curtail (#22) | scenario `ev_fast_charging` | Overload alarm fires; curtail reduces load ≥ 20%; forecast chart refreshes each step | EMS + HES + simulator |
| 19 | Microgrid reverse flow + DER aggregation (#23) | scenario `peaking_microgrid`; add asset mid-run | Aggregate updates from step 4; reverse flow banner | EMS DER aggregation view |
| 20 | Fault + FLISR + AMI correlation (#24) | scenario `network_fault` | Outage opens ≤ 90 s; isolation button dispatches; affected_count drops | EMS outage + simulator + HES |
| 21 | DCU sensor actions (#25) | simulator sensor stream; breach injected | Alarm fires; threshold edit round-trips through HES + MDMS | EMS `transformer_sensor_readings` + HES + MDMS |
| 22 | GIS zoom + context commands (#26) | preset topology | Zoom country → meter; each level context menu correct; "Read meter" dispatches | EMS GIS proxy + PostGIS + HES command |
| 23 | Custom dashboards + report builder (#7, #19, #27) | user saves layout; schedules report | Layout persists across logout; scheduled report email sent | EMS `dashboard_layout` + `scheduled_report` |
| 24 | App dev — rules, algorithms, apps (#27) | user publishes a rule; trigger fires | Rule action dispatched; version history + role-gated publish enforced | EMS `app_def`, `rule_def`, `algorithm_def` tables |

## Global E2E Checks

Each test run MUST also assert:

- **Trace continuity**: a single W3C trace covers simulator → HES → MDMS → EMS for each data-path test. Use Tempo API to query `traceparent` from Kafka header and find it in EMS render span.
- **Audit coverage**: every user-triggered story emits ≥ 1 row in MDMS `action_audit_log` with `service_name=polaris-ems`.
- **RBAC**: `viewer` cannot hit mutating endpoints (403); `operator` cannot hit admin-only pages.
- **No seeded fallback visible**: in `SSOT_MODE=strict`, shutting down mdms-api causes banner "MDMS unavailable"; no numbers shown.
- **OTel completeness**: every HTTP endpoint has a `http.route` span attribute; every Kafka publish has `messaging.destination`.

## Test Organisation

```
backend/tests/integration/demo_compliance/
├── conftest.py                 # fixtures: simulator API, HES, MDMS clients, trace utils
├── test_us01_dashboard.py
├── test_us02_rc_dc.py
├── test_us03_fota.py
├── test_us04_outage.py
├── test_us05_vee.py
├── test_us06_tariff.py
├── test_us07_cis_gis.py
├── test_us08_load_profile.py
├── test_us09_ntl.py
├── test_us10_prepaid.py
├── test_us11_alerts.py
├── test_us12_data_accuracy.py
├── test_us13_system_mgmt.py
├── test_us14_reports.py
├── test_us15_der_dashboards.py
├── test_us16_der_situational.py
├── test_us17_solar_overvoltage.py
├── test_us18_ev_fast_charge.py
├── test_us19_microgrid.py
├── test_us20_fault_flisr.py
├── test_us21_dcu_sensors.py
├── test_us22_gis_zoom.py
├── test_us23_custom_dashboards.py
└── test_us24_app_dev.py

frontend/tests/e2e/demo_compliance/
└── (parallel 24 Playwright specs)
```

## CI wiring

- Runs nightly against dev EKS using `/e2e-test` skill.
- PR to `eskom_dev` gates on 22/24 demo compliance tests passing (stabilises while waves deploy); target 24/24 before merge to `main`.
- Flaky test quarantine: tests marked `@pytest.mark.quarantine` logged but don't block.

## Demo-Day Dry Run Protocol

2026-04-20, full E2E suite run 3×. Record any flake to hotfix list. 2026-04-21 morning: smoke-only (5-min subset of fastest 8 tests) before go-live.
