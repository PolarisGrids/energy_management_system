# Polaris EMS — Comprehensive Feature Roadmap

This is the target feature list for **Polaris EMS as a full-fledged production Energy Management System**, not just the Eskom demo. It enumerates every capability a utility control centre would expect to operate an AMI + DER network at scale, grouped by domain. Each item is marked:

- ✅ Implemented (at least in part, live on `vidyut360.dev.polagram.in`)
- 🟡 Partial (present in code but incomplete / mock / demo-only)
- ⬜ Not yet built

For in-flight mock/gap detail see `docs/GAPS.md`. For GIS specifics see `docs/GIS.md`.

---

## 1. Identity, Access & Session

- ✅ JWT login (`/auth/login`, `/auth/me`)
- 🟡 Three demo users (admin/supervisor/operator) with bcrypt — **no user management UI**
- ⬜ User CRUD (create/edit/disable users)
- ⬜ Role & permission management (fine-grained RBAC)
- ⬜ Frontend RBAC gating (menu + route guards per role)
- ⬜ Session timeout + refresh-token rotation
- ⬜ Password policy, rotation, reset via email
- ⬜ MFA / TOTP for supervisors + admins
- ⬜ SSO (SAML / OIDC) against Eskom AD
- ⬜ API keys for machine-to-machine callers
- ⬜ Per-user audit of sensitive reads
- ⬜ Session hijack protection (IP-change detection)

## 2. Network & Topology

- ✅ Feeder / transformer / meter list endpoints
- 🟡 Meter / transformer / feeder models (Meter file missing in working copy)
- ⬜ Substation & PSS models
- ⬜ Pole, service-line, and MV/LT cable models
- ⬜ Asset hierarchy browser (tree + drill-down)
- ⬜ Topology trace (upstream / downstream from any asset)
- ⬜ Network change log (commissioning / decommissioning)
- ⬜ Impedance model for load-flow
- ⬜ CIM (IEC 61968/61970) import/export
- ⬜ Phase identification per service
- ⬜ Transformer nameplate + impedance data
- ⬜ Protection coordination (relay settings)

## 3. AMI / HES Integration

- ✅ Mirror DCUs, command log, FOTA, firmware distribution, comm trend (all from seeded local DB)
- 🟡 `hes_client.py` stubbed; disabled by default
- ⬜ Live DCU health polling from real HES
- ⬜ Meter inventory sync (daily reconciliation with HES)
- ⬜ On-demand ad-hoc read (read billing register, load profile, events)
- ⬜ Relay connect / disconnect wired to HES (currently only mutates DB)
- ⬜ Time-sync broadcast
- ⬜ Firmware OTA job scheduling + progress tracking
- ⬜ Tamper / cover-open detection acknowledgement back to HES
- ⬜ Batch command execution with backpressure
- ⬜ Command priority queues (emergency, scheduled, bulk)
- ⬜ Response-time SLA dashboards per DCU

## 4. MDMS / Consumer Data

- ✅ VEE summary / exceptions mirror (from seeded local DB)
- ✅ Tariff schedules list
- ✅ NTL suspects list
- ✅ Power-quality zones
- 🟡 MDMS client stubbed; disabled by default
- ⬜ Consumer master import (CIS sync)
- ⬜ VEE rule editor (create/edit validation & estimation rules)
- ⬜ VEE exception triage workflow (approve/reject/bulk)
- ⬜ Consumption & billing determinants API for billing engine
- ⬜ Prepaid balance + low-balance alerts
- ⬜ Token generation pipeline (STS/DLMS) with read-back
- ⬜ Tariff switch / reclassification workflow
- ⬜ Historical reading browser (12 months, with revisions)
- ⬜ Statement of account PDF generation
- ⬜ Customer-facing portal integration

## 5. Alarms & Events

- ✅ 14 alarm types, 5 severities, ack/resolve
- ✅ Active alarm list + history
- 🟡 Only local DB — no AMI/SCADA event bus
- ⬜ Alarm routing rules (escalation by severity/time)
- ⬜ Alarm grouping (correlate related events)
- ⬜ Root-cause inference (e.g., upstream outage → cluster of meter comm losses)
- ⬜ Suppression windows (maintenance mode)
- ⬜ On-call roster & paging
- ⬜ SMS / Teams / email notification on alarm
- ⬜ Alarm-to-ticket conversion (WFM hook)
- ⬜ Post-incident review (PIR) templates

## 6. Readings, Load & Energy Accounting

- ✅ Interval / latest meter readings endpoints
- ✅ 24h load profile by tariff class
- ✅ Daily network summary
- ✅ Consumption, top-consumer reports
- 🟡 Dataset synthesised by seed script
- ⬜ Real-time load aggregation per feeder / substation
- ⬜ Energy audit — energy sent vs energy billed (loss %)
- ⬜ Technical-loss calculation (line I²R estimation)
- ⬜ Non-technical-loss analytics (theft patterns, NTS)
- ⬜ Max-demand tracking and KVA billing
- ⬜ Reactive power + PF analysis
- ⬜ Forecast engine (ML-based load & solar forecast)
- ⬜ Peak-shaving / load-shifting recommendations

## 7. DER Management

- ✅ DER list (PV, BESS, EV, microgrid) with current output
- ✅ DER commands: curtail / connect / disconnect / set-power (writes to DB only)
- 🟡 State-of-charge / island flags in model — not visualised
- ⬜ DER live dispatch from ADMS
- ⬜ Curtailment schedule (by DER group, by time)
- ⬜ Volt-VAR optimisation (Volt-VAR Control)
- ⬜ Reactive-power dispatch
- ⬜ BESS charge/discharge schedule
- ⬜ EV charging station management (reservation, billing)
- ⬜ Microgrid islanding detection + re-sync
- ⬜ DER interconnection application workflow
- ⬜ Revenue / PPA tracking per DER asset
- ⬜ Generation achievement rate scoring

## 8. Power Quality & Sensors

- ✅ Transformer sensor list + threshold update
- 🟡 Sensor history is synthesized per request (random)
- ⬜ Historical sensor store (`transformer_sensor_readings` table)
- ⬜ Anomaly detection (z-score, seasonal decomposition)
- ⬜ Predictive maintenance (RUL for transformers based on oil + winding trends)
- ⬜ Sag / swell / flicker events from PQ meters
- ⬜ Harmonic spectrum viewer
- ⬜ IEC 61000-4-30 / EN 50160 compliance reports
- ⬜ Condition-based inspection scheduling

## 9. Outage Management

- ⬜ Outage incident object with lifecycle (detected / confirmed / dispatched / restored)
- ⬜ Affected-customer count derivation from topology
- ⬜ Outage polygon drawn from impacted DTRs
- ⬜ FLISR (Fault Location, Isolation, Service Restoration)
- ⬜ Auto-call lists for affected customers
- ⬜ Public outage map
- ⬜ ETR (Estimated Time to Restore) tracking
- ⬜ SAIDI / SAIFI / CAIDI / MAIFI reliability indices
- ⬜ Storm mode (elevated thresholds, crew surge)
- ⬜ Momentary outage / blink detection

## 10. GIS (see `docs/GIS.md` for full list)

- ✅ Leaflet map with meter / alarm / DER clusters
- 🟡 15% of production GIS feature set present
- ⬜ Route `/map` not registered in deployed build (P0)
- ⬜ PostGIS, GeoJSON endpoints, MVT tiles
- ⬜ MapLibre migration
- ⬜ Network topology lines, outage polygons, heatmaps
- ⬜ Draw / geofence / measurement tools
- ⬜ Search, geocoding, time-slider, export

## 11. Workforce Management

- ⬜ Crew roster & skills matrix
- ⬜ Work-order object (create, assign, dispatch, close)
- ⬜ Mobile app for crews (photos, digital forms, e-sign)
- ⬜ Real-time crew GPS
- ⬜ Route optimisation
- ⬜ SLA tracking & timer alerts
- ⬜ Auto-create WO from alarms / outages
- ⬜ Inventory / truck stock
- ⬜ Time & materials capture
- ⬜ Integration with HR (payroll)

## 12. Simulation & Training

- ✅ 5 scripted scenarios (solar over-voltage, EV charging, peaking microgrid, fault, sensor)
- ✅ Step-through + command injection UI
- ⬜ Operator training sandbox (isolated DB)
- ⬜ Scenario builder (drag-and-drop steps)
- ⬜ Scoring + debrief reports
- ⬜ Replay from real historical outages
- ⬜ Digital-twin mode with load-flow engine

## 13. Reports & Analytics

- ✅ Consumption, meter-readings, top-consumers
- ✅ Audit event log
- ⬜ Scheduled reports (daily/weekly/monthly email/PDF)
- ⬜ Saved report configurations per user
- ⬜ Drill-down pivot tables
- ⬜ Compliance reports (NERSA, IEC, ISO 50001)
- ⬜ Revenue-protection dashboard (NTL losses)
- ⬜ KPI dashboard (SAIDI / SAIFI / CAIDI, NTL %, comm success %)
- ⬜ Executive summary (board-ready)
- ⬜ Regulator submission bundle

## 14. Audit & Compliance

- ✅ Local `audit_events` table + `/audit/*` endpoints
- ⬜ End-to-end correlation with OTel trace IDs
- ⬜ Tamper-evident audit log (hash chain / WORM)
- ⬜ Role-based access audit
- ⬜ Data retention policy enforcement
- ⬜ GDPR / PoPIA subject access requests
- ⬜ IEC 62443 / ISO 27001 control mapping
- ⬜ Automated compliance scanning (Reconciler module)

## 15. Notifications & Integrations

- 🟡 Email / SMS / Teams / Push — all disabled by default, log-only
- ⬜ SMTP (SES / Exchange) delivery
- ⬜ Twilio / Clickatell SMS
- ⬜ MS Teams channel & chat integration
- ⬜ Firebase / APNS push
- ⬜ Slack integration
- ⬜ Webhook fan-out for 3rd-party consumers
- ⬜ Notification templates (per language, per locale)
- ⬜ Notification preferences per user

## 16. Observability

- 🟡 OTel wiring present (`otel_common`); default collector endpoint set
- ⬜ Service dashboards (Grafana) imported into repo
- ⬜ Alerting rules (Prometheus Alertmanager)
- ⬜ SLO definitions + error-budget tracking
- ⬜ Correlated logs + traces + metrics in one view
- ⬜ Business KPI dashboards
- ⬜ Synthetic probe suite (Playwright canaries)

## 17. Control-Room / Visualisation

- ✅ Dashboard with KPI tiles
- ✅ Energy monitoring, sensors, DER, HES/MDMS mirror
- 🟡 A/V Control Room page — static UI only
- 🟡 SMOC Showcase — static marketing
- ⬜ Video-wall layout manager (multi-screen)
- ⬜ Screen routing (push view to wall)
- ⬜ "Focus mode" (highlight active incident across all screens)
- ⬜ Environmental controls (HVAC, lighting) via BMS
- ⬜ Teams call integration from operator console
- ⬜ CCTV integration in a tile

## 18. App Builder (L3 No-Code)

- 🟡 `AppBuilder.jsx` shell with sample widgets, rules, algorithms (not persisted)
- ⬜ Backend store for apps / rules / algorithms
- ⬜ Rule engine execution runtime
- ⬜ Algorithm editor with Python sandbox (Pyodide / remote)
- ⬜ Per-app publish/preview with versioning
- ⬜ Role-based publish approval
- ⬜ Marketplace / library of reusable algorithms
- ⬜ Hot-reload deploy to operator dashboards

## 19. Security

- ⬜ TLS everywhere (ALB terminates; verify mTLS to internal services)
- ⬜ CSRF protection on mutating endpoints
- ⬜ Rate limiting per user / IP / endpoint
- ⬜ Secrets in AWS SSM / Secrets Manager (no `.env` in image)
- ⬜ Helmet-style HTTP security headers on frontend
- ⬜ Content Security Policy + SRI
- ⬜ SAST + dependency scanning in CI
- ⬜ Penetration test & remediation log
- ⬜ SSE token in header (not query string — P1 finding in `docs/GAPS.md`)
- ⬜ Zero-trust network policies in Kubernetes

## 20. Data Platform

- ⬜ Alembic migrations committed (no more `create_all()`)
- ⬜ Partitioning on `meter_readings` (monthly)
- ⬜ Continuous aggregates (TimescaleDB) for load profiles
- ⬜ Archive / cold-storage to S3 (Glacier) with lifecycle
- ⬜ Replay / point-in-time recovery
- ⬜ Schema registry for Kafka topics
- ⬜ Change-data-capture (Debezium) into a warehouse
- ⬜ Lakehouse / Athena for analytics (already standard in the project)

## 21. DevEx & CI/CD

- ✅ Docker Compose for local dev
- ✅ Jenkinsfile → ECR → ArgoCD GitOps
- ⬜ Pre-commit hooks (ruff, black, eslint, prettier)
- ⬜ Unit test coverage > 70%
- ⬜ Integration test harness (pytest + Playwright)
- ⬜ Contract tests against HES / MDMS mocks
- ⬜ Staging environment (`vidyut360.stag.polagram.in`)
- ⬜ Blue/green or canary deploy
- ⬜ Auto rollback on SLO breach
- ⬜ Feature flags (Unleash / GrowthBook)

## 22. Reliability

- ⬜ Multi-AZ RDS / DB with read replica
- ⬜ SSE server horizontal scaling (sticky or shared state)
- ⬜ Circuit breakers on HES / MDMS calls
- ⬜ Dead-letter queues on all async topics
- ⬜ Backup / restore drills (quarterly)
- ⬜ Disaster-recovery runbook
- ⬜ Chaos tests (kill pod, drop network)

## 23. Public APIs & Extensibility

- ⬜ OpenAPI spec publishing + versioning
- ⬜ Public developer portal (`developers.polaris-ems.com`)
- ⬜ SDKs (Python, TS) for partners
- ⬜ Webhook subscriptions for 3rd-party consumers
- ⬜ GraphQL facade (optional)
- ⬜ Plugin architecture for custom VEE rules / algorithms

## 24. Internationalisation & Accessibility

- ⬜ i18n (English, isiZulu, Sesotho, Afrikaans for the Eskom market)
- ⬜ Number, date, currency localisation
- ⬜ RTL support (future-proof)
- ⬜ WCAG 2.1 AA compliance
- ⬜ Keyboard-only navigation across all pages
- ⬜ Screen-reader labels on charts

---

## Immediate next 10 days (suggested)

1. **Restore P0 blockers** from `docs/GAPS.md §0` — commit `meter.py`, schema files, `App.jsx`, and register `/map`, `/reconciler`, `/appbuilder` routes.
2. **Fix P1 data bugs**: `MDMSMirror NaN%`, `HESMirror` hardcoded fallbacks, `reconcilerAPI` definition, SSE-token-in-URL → `Authorization` header.
3. **Commit Alembic baseline** and stop `create_all()` from the lifespan.
4. **Seed realistic demo data** in dev (populate alarms / audit events / VEE exceptions so pages don't render empty).
5. **Enable HES + MDMS integration** in a staging profile, even against a mock service, to prove the client path.
6. **Begin PostGIS migration** (§ GIS P1) — add `postgis` extension and one geometry column to `feeders`.
7. **Extract shared UI components** (Button, Card, KPI, Chart, Modal, Toast, Skeleton) into `components/ui/`.
8. **Add RBAC menu gating** in `AppLayout`.
9. **Standup Alertmanager + Grafana dashboards** (already shared infra).
10. **Define SLOs** for the top 5 endpoints (dashboard summary, SSE stream, alarms list, meter list, login).
