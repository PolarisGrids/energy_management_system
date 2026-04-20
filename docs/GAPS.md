# Polaris EMS — Gaps, Mocks & Incomplete Features

Audit date: **2026-04-18**.
Scope: backend (`/backend`), frontend (`/frontend`), and live deployment at `https://vidyut360.dev.polagram.in` (authenticated as `admin / Admin@2026`, verified with headless Chromium).

Severity key:
- **P0 BLOCKER** — crashes, missing files, or endpoints returning invalid data in the default config
- **P1 CRITICAL** — production code path serves fabricated data or fails silently
- **P2 MAJOR** — fallback to mock data or stale/partial integrations
- **P3 MINOR** — demo-only surfaces, hardcoded UI constants, cosmetic

---

## 0. Repo Integrity (P0)

| # | Finding | Evidence |
|---|---|---|
| 0.1 | **`backend/app/models/meter.py` missing** — imported by `__init__.py:2`, `endpoints/meters.py:7`, `sse.py`, `simulation_engine.py`, `seed_data.py:19`. Only `__pycache__/meter.cpython-312.pyc` remains. Startup will fail on any clean container. | `backend/app/models/` (no `meter.py`); imports reference `Meter, Transformer, Feeder, MeterStatus, RelayState` |
| 0.2 | **`backend/app/schemas/` is empty** — `alarms.py:9`, `der.py:8`, `meter.py`, `simulation.py`, `sensor.py`, `auth.py` all `from app.schemas.<x> import ...`. No source files present; only `__pycache__`. | `ls backend/app/schemas/` returns only `__pycache__` |
| 0.3 | **`frontend/src/App.jsx` missing** — `main.jsx:4` imports `'./App.jsx'` but the file is not in the working copy. Dev server won't boot; only the pre-built `dist/` works. | `ls frontend/src/App.*` → only `App.css` |
| 0.4 | **No Alembic revisions** — `alembic/versions/` empty; schema is only materialised by `seed_data.py`/`create_all()`. Any schema drift in prod is unrecoverable without re-seed. | `ls backend/alembic/versions/` |
| 0.5 | **Route path mismatch** — the deployed `App.jsx` registers `/gis`, `/app-builder`, and `/reconciler` (NOT `/map`, `/appbuilder` as guessed earlier). Puppeteer `finalUrl: "/"` on the wrong paths was a `*` catch-all at work. `/reconciler` still failed because `reconcilerAPI` was undefined — fixed in Phase A (services/api.js). | `App.jsx` inspected post-restore |

---

## 1. Backend Mock / Stub Inventory

### 1.1 Synthetic data served in production

| Route | File:line | What is faked | Severity |
|---|---|---|---|
| `GET /api/v1/sensors/{id}/history` | `endpoints/sensors.py:66–117` | 24h sensor history fabricated with `random.uniform()` on diurnal load factor — no DB lookup, no historical sensor store. | **P1** |
| `POST /api/v1/simulation/{id}/next-step` | `services/simulation_engine.py` | Applies hardcoded step values from `simulation_steps` rows (seeded), mutates live meter/transformer/DER rows with synthetic voltages/currents. | P2 (by design) |
| `POST /api/v1/teams/alert` | `endpoints/teams.py:33–46`, `services/notification_service.py:59–62` | `TEAMS_ENABLED=false` by default; returns `{"success":true,"enabled":false}` and logs `[TEAMS MOCK]`. Never posts to Graph/webhook. | **P1** |
| `GET /api/v1/events/stream` | `endpoints/sse.py:16–101` | `KAFKA_ENABLED=false` by default; DB-polls every 15s and synthesises a heartbeat. No live push. | P2 |
| `GET /api/v1/reconciler/*` | `endpoints/reconciler.py:28–224` | Reads a dev-only SQLite at `~/.reconciler/history.db`; returns 503 if missing. Not a production data source. | **P1** |

### 1.2 External integrations disabled → silent fallback to local seeded DB

All of the following are **gated by `*_ENABLED=false` flags** (`backend/app/core/config.py`). When disabled the client short-circuits to `None` and callers silently read seeded PostgreSQL rows instead of the real upstream.

| Integration | Config flag | Client | Caller endpoints |
|---|---|---|---|
| HES (AMI) | `HES_ENABLED=false` | `services/hes_client.py:18–32` | `/hes/*` (dcus, commands, fota, firmware-distribution, comm-trend) |
| MDMS | `MDMS_ENABLED=false` | `services/mdms_client.py:18–32` | `/mdms/*` (vee/summary, exceptions, consumers, tariffs, ntl, power-quality), `/energy/*`, `/reports/*` |
| Kafka events | `KAFKA_ENABLED=false` | `sse.py` | `/events/stream` |
| Email (SMTP) | `SMTP_ENABLED=false` | `notification_service.py:20–23` | operator alerts |
| SMS (Twilio) | `TWILIO_ENABLED=false` | `notification_service.py:43–45` | operator alerts |
| Teams webhook | `TEAMS_ENABLED=false` | `notification_service.py:59–62` | `/teams/alert` |
| Push (Firebase) | `FIREBASE_ENABLED=false` | `notification_service.py:83–85` | operator alerts |
| GIS / Mapbox | `GIS_ENABLED=false` | — | not implemented |
| WFM | `WFM_ENABLED=false` | — not implemented | — |
| CIS | `CIS_ENABLED=false` | — not implemented | — |

### 1.3 Seeded data (intentional, but reaches users)

`backend/scripts/seed_data.py` generates the entire demo dataset. Volume produced (from the script):

- Feeders / transformers: ≤20 / ≤100 (live dev shows 3 feeders, 11 transformers)
- Meters: up to 1,200 (live dev shows 107 — dev seed reduced)
- Readings: ~201k rows (diurnal curve + 10% noise)
- Alarms: ~25 recent (live dev shows 0 — none were populated or all resolved)
- DER assets: 4 hardcoded (Soweto PV, Sandton BESS, Durban EV Hub, Pretoria Microgrid)
- Scenarios / steps: 5 / 40+
- Audit events: ~180 across 3 hardcoded users (`admin/supervisor/operator`) with fixed IPs
- Tariffs: 9 hardcoded ZAR TOU tariffs
- NTL suspects: ~60 with hardcoded patterns
- PQ zones: ~75 random deviations

### 1.4 Placeholder credentials in default config

`backend/app/core/config.py` (lines 68–96):
```
TWILIO_AUTH_TOKEN   = "twilio-auth-token-placeholder-2026"
TEAMS_TENANT_ID     = "eskom-tenant-id-placeholder"
TEAMS_CLIENT_ID     = "smoc-app-client-id-placeholder"
TEAMS_CLIENT_SECRET = "smoc-app-client-secret-placeholder"
FIREBASE_SERVER_KEY = "firebase-server-key-placeholder"
WFM_API_KEY         = "wfm-api-key-placeholder"
CIS_API_KEY         = "cis-api-key-placeholder"
MAPBOX_ACCESS_TOKEN = "pk.demo_mapbox_token_not_needed_for_leaflet"
```
Flipping any `*_ENABLED=true` without rotating these will hard-fail auth against the real service.

### 1.5 Endpoint-by-endpoint verdict (mock ≠ real)

| Endpoint | DB-backed | External call | Verdict |
|---|---|---|---|
| POST `/auth/login` | yes | — | REAL (bcrypt+JWT) |
| GET `/meters/`, `/meters/summary` | yes | — | REAL (seeded data) |
| POST `/meters/{s}/(dis)connect` | yes | HES client (disabled) | LOGS ONLY — no meter actually operated |
| GET `/readings/{s}/{interval,latest}` | yes | — | REAL (seeded) |
| GET `/alarms/*`, POST ack/resolve | yes | — | REAL |
| GET `/der/*`, POST `/der/{id}/command` | yes | — | writes only to DB, no DER controller called |
| GET `/sensors/`, `/threshold` | yes | — | REAL |
| GET `/sensors/{id}/history` | no | — | **SYNTHESIZED per request** |
| `/simulation/*` | yes | engine mutates DB | DEMO ONLY |
| `/events/stream` (SSE) | yes (poll) | Kafka disabled | POLLING FALLBACK |
| `/teams/alert` | — | MS Graph disabled | LOG ONLY |
| `/energy/*`, `/reports/*` | yes | MDMS disabled | LOCAL SEEDED |
| `/hes/*` | yes | HES disabled | LOCAL SEEDED |
| `/mdms/*` | yes | MDMS disabled | LOCAL SEEDED |
| `/reconciler/*` | SQLite | — | DEV-ONLY SOURCE |
| `/audit/*` | yes | — | REAL (but seeded) |

---

## 2. Frontend Mock / Stub Inventory

### 2.1 Pages with hardcoded fallback values

| Page | File:line | Problem |
|---|---|---|
| `HESMirror.jsx` | `60–63`, `88–93` | KPI cards fall back to hard-wired "183 online / 42 offline / 15 tamper / 91.4% comm" when API returns null — masks real outages. **P1** |
| `Dashboard.jsx` | `101–106`, `70` | Fallback to `'—'` for every KPI; load profile defaults to empty arrays without a loading / error state. **P2** |
| `EnergyMonitoring.jsx` | `62–66` | All four load-profile series default to `[]`; charts render blank instead of surfacing the error. **P2** |
| `MDMSMirror.jsx` | (live) | Division-by-zero produces `NaN%` for "Passed Validation" / "Estimated Readings" when seed table is empty — confirmed on live site (`/mdms` → `NaN%`). **P1** |

### 2.2 Pages that are pure UI shells with no persistence

| Page | File | Issue |
|---|---|---|
| `AppBuilder.jsx` | `10–127` | `INITIAL_RULES`, `INITIAL_APPS`, `SAMPLE_ALGORITHMS`, `ALGORITHM_CODE`, `CONSOLE_OUTPUT` — all hardcoded. No backend persistence; refresh loses all work. Route itself is **unreachable** in the deployed build. **P1** |
| `AVControl.jsx` | `8–23`, `96–143` | `MEETINGS`, `PARTICIPANTS`, `SOURCES`, `BLIND_ZONES`, `PRESET_LAYOUTS` all hardcoded; no AV controller or Teams API integration. **P2** |
| `SMOCShowcase.jsx` | `7–279` | Hardware specs, floor plan SVG — entirely static marketing content. **P3** |
| `Placeholder.jsx` | whole file | Stub page shown for routes "under construction". |

### 2.3 Broken API wiring

| Page | Call | Issue |
|---|---|---|
| `Reconciler.jsx:7,134–135` | `reconcilerAPI.getSummary()`, `reconcilerAPI.getComplianceMatrix()` | `reconcilerAPI` **is not exported** from `services/api.js`. Would crash on mount — but the route is also unreachable in the deployed build. **P1** |

### 2.4 Missing frontend infrastructure

- `src/components/ui/` — **empty** (no reusable button/modal/card library; all inline in pages)
- `src/components/alarms/` — empty
- `src/components/charts/` — empty (ECharts options duplicated in every page)
- `src/components/map/` — empty (GISMap is a single ~413-line monolith)
- No RBAC gating anywhere in the UI — Admin / Supervisor / Operator all see identical menus
- No `VITE_USE_MOCK` mode flag — cannot run frontend standalone
- No error boundaries, loading skeletons, empty-state components, or toast notification system

---

## 3. GIS Gap Analysis

Covered in detail in `docs/GIS.md`. Summary: **11 of 73 standard utility-GIS features present (~15%)**. Demo-grade Leaflet visualisation with clustered meter/alarm/DER pins, but no:

- Feeder / LT line geometries (Feeder model has unused `geojson` field)
- Multi-basemap toggle (only CartoDB Dark)
- Outage polygons, FLISR, load-flow heatmap, voltage colouring
- Draw tools, measurement, geofencing
- Search, geocoding, address lookup
- Export (KML / GeoJSON / PNG), print, PDF
- Crew / WFM dispatch pins, route planning
- Offline tiles, time-slider / playback, 3D
- PostGIS geometry columns (shapely + geojson are in `requirements.txt` but **unused**)
- GeoJSON FeatureCollection endpoints — frontend fetches raw JSON and renders circles

**And crucially**: the `/map` route is **not registered in the deployed build** (puppeteer redirects to `/`), so the page doesn't even render in production.

---

## 4. Live Verification (Puppeteer, 2026-04-18)

Authenticated as `admin / Admin@2026` (token seeded via `localStorage`), visited 15 routes on `https://vidyut360.dev.polagram.in`.

### 4.1 Routes (state)

| Route | Served page | API calls (200 OK) | Issues seen |
|---|---|---|---|
| `/dashboard` | Dashboard | `meters/summary`, `der/`, `energy/load-profile`, SSE | 107 Online / 0 Offline / 0 Active Alarms — unrealistically clean dataset |
| `/map` | → Dashboard | — | **Route missing (P0)** |
| `/alarms` | Alarm Console | `alarms/`, `meters/summary`, SSE | `No alarms found` — empty dataset |
| `/der` | DER Management | `der/`, SSE | 6 PV + 2 BESS + 2 EV + 0 Microgrid rendered; Curtail/Connect/Disconnect buttons visible |
| `/energy` | Energy Monitoring | 5× API + SSE | Load Profile chart renders; "0 kW" banner suggests empty readings |
| `/reports` | Reports & Audit | `meters/summary`, SSE | Feeder dropdown populated; "Generate Report" UI only |
| `/hes` | HES Mirror | `hes/commands`, `hes/dcus`, `hes/fota`, `meters/summary`, SSE | Renders but metrics all at 100% (no real outage data) |
| `/mdms` | MDMS Mirror | `vee/*`, `power-quality`, `tariffs`, `ntl`, SSE | **`NaN%` for Passed Validation & Estimated Readings (P1)** |
| `/sensors` | Sensor Monitoring | `sensors/`, SSE | 10 sensors across transformers, all NORMAL — clean but real |
| `/simulation` | DER Simulations | `simulation/`, SSE | 5 scenarios listed |
| `/audit` | Audit Log | `audit/events`, `audit/summary`, SSE | 0 Total Events — dev DB not seeded with audit events |
| `/showcase` | SMOC Showcase | SSE only | Static marketing content only |
| `/reconciler` | → Dashboard | — | **Route missing (P0)** |
| `/av-control` | Control Room A/V | SSE only | Fully hardcoded UI, no API |
| `/appbuilder` | → Dashboard | — | **Route missing (P0)** |

### 4.2 API traffic observations

- Every page subscribes to `GET /api/v1/events/stream?token=<jwt>` — JWT passed as **query string** (exposed in logs and browser history). **P1 SECURITY.**
- Dev environment has 107 meters / 11 transformers / 3 feeders / 0 alarms / 0 audit events — the seed script volumes were clearly trimmed for dev but no negative scenarios (alarms, outages) are populated, so most dashboards look empty.
- No 4xx / 5xx responses observed on the 15 tested routes.
- No console errors thrown.

---

## 5. Summary Table — Incomplete or Mocked

| # | Area | Severity | Item |
|---|---|---|---|
| 1 | Backend | P0 | `app/models/meter.py` missing |
| 2 | Backend | P0 | `app/schemas/*` missing |
| 3 | Backend | P0 | Alembic migrations absent |
| 4 | Frontend | P0 | `src/App.jsx` missing from working copy |
| 5 | Frontend | P0 | `/map`, `/reconciler`, `/appbuilder` routes unreachable |
| 6 | Backend | P1 | `/sensors/{id}/history` generates random data |
| 7 | Backend | P1 | `/teams/alert` logs only — no Teams integration |
| 8 | Backend | P1 | `/reconciler/*` reads dev SQLite only |
| 9 | Backend | P1 | JWT passed as query string to SSE (`?token=`) |
| 10 | Backend | P1 | Meter relay connect/disconnect never calls HES |
| 11 | Frontend | P1 | `MDMSMirror.jsx` shows `NaN%` on empty data |
| 12 | Frontend | P1 | `HESMirror.jsx` hard-wires 183/42/15 fallback values |
| 13 | Frontend | P1 | `Reconciler.jsx` imports undefined `reconcilerAPI` |
| 14 | Frontend | P1 | `AppBuilder.jsx` — no persistence, pure UI shell |
| 15 | Backend | P2 | HES/MDMS/Kafka/SMTP/Twilio/Firebase all disabled-by-default fallback to local DB |
| 16 | Backend | P2 | DER commands only mutate local DB, no device control |
| 17 | Backend | P2 | SSE is polling, not event-driven |
| 18 | Frontend | P2 | `Dashboard.jsx`, `EnergyMonitoring.jsx` empty-array fallbacks hide errors |
| 19 | Frontend | P2 | `AVControl.jsx` fully hardcoded |
| 20 | Frontend | P2 | No RBAC in UI (all roles see same menus) |
| 21 | Frontend | P2 | No error boundary / toast / skeleton components |
| 22 | GIS | P2 | Leaflet monolith, 15% of production feature set |
| 23 | GIS | P2 | No PostGIS, no GeoJSON endpoints, shapely/geojson unused |
| 24 | GIS | P2 | No feeder/line geometries, no outage polygons, no heatmaps |
| 25 | Frontend | P2 | `components/ui,alarms,charts,map/` all empty |
| 26 | Backend | P3 | Placeholder `*_API_KEY` strings in `config.py` |
| 27 | Backend | P3 | Faker-generated customer names + SA addresses |
| 28 | Backend | P3 | 9 hardcoded ZAR tariffs, not sourced from Eskom |
| 29 | Backend | P3 | Fixed 3 audit users with 3 fixed IPs |
| 30 | Frontend | P3 | `SMOCShowcase.jsx` static marketing content |

For the target state (production EMS) see `docs/ROADMAP.md` and `docs/GIS.md`.
