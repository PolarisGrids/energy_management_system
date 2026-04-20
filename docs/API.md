# Polaris EMS — API

FastAPI application (`app/main.py`) mounted at `/api/v1`. Interactive docs at `/api/docs` (Swagger) and `/api/redoc`.

- **Title**: SMOC EMS API
- **Version**: 1.0.0
- **Base URL (dev)**: `https://vidyut360.dev.polagram.in/api/v1`
- **Auth**: JWT bearer (`POST /auth/login` → `Authorization: Bearer <jwt>`)
- **Real-time**: Server-Sent Events on `/api/v1/events/stream`
- **Health**: `GET /health`

## Router Map

| Router | Prefix | File |
|---|---|---|
| auth | `/auth` | `app/api/v1/endpoints/auth.py` |
| meters | `/meters` | `.../meters.py` |
| readings | `/readings` | `.../readings.py` |
| alarms | `/alarms` | `.../alarms.py` |
| der | `/der` | `.../der.py` |
| sensors | `/sensors` | `.../sensors.py` |
| simulation | `/simulation` | `.../simulation.py` |
| events (SSE) | `/events` | `.../sse.py` |
| teams | `/teams` | `.../teams.py` |
| energy | `/energy` | `.../energy.py` |
| reports | `/reports` | `.../reports.py` |
| audit | `/audit` | `.../audit.py` |
| hes (mirror) | `/hes` | `.../hes_mirror.py` |
| mdms (mirror) | `/mdms` | `.../mdms_mirror.py` |
| reconciler | `/reconciler` | `.../reconciler.py` |

## Endpoints

### Auth — `/auth`
| Method | Path | Purpose |
|---|---|---|
| POST | `/login` | Exchange credentials for JWT |
| GET | `/me` | Profile of the current bearer |

### Meters — `/meters`
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Paginated list; filter by status / transformer / feeder |
| GET | `/summary` | Fleet KPIs (online, tamper, disconnected, comm rate) |
| GET | `/{serial}` | Meter detail |
| POST | `/{serial}/connect` | Dispatch relay connect via HES |
| POST | `/{serial}/disconnect` | Dispatch relay disconnect via HES |
| GET | `/transformers/list` | List transformers (optional `feeder_id`) |
| GET | `/feeders/list` | List feeders |

### Readings — `/readings`
| Method | Path | Purpose |
|---|---|---|
| GET | `/{serial}/interval` | Interval readings (24–168h) |
| GET | `/{serial}/latest` | Latest reading |

### Alarms — `/alarms`
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Paginated list with filters |
| GET | `/active` | Up to 100 active alarms |
| POST | `/{alarm_id}/acknowledge` | Operator ack |
| POST | `/{alarm_id}/resolve` | Operator resolve |

### DER — `/der`
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | List DER assets (filter by `asset_type`) |
| GET | `/{asset_id}` | Asset detail |
| POST | `/{asset_id}/command` | `curtail`, `connect`, `disconnect`, `set_power` |

### Sensors — `/sensors`
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | List sensors (filter by transformer/type/status) |
| GET | `/transformer/{transformer_id}` | All sensors on a transformer |
| GET | `/{sensor_id}/history` | 24h history (30-min bins, diurnal pattern) |
| POST | `/{sensor_id}/threshold` | Update warning / critical thresholds |

### Simulation — `/simulation`
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | List scenarios |
| GET | `/{scenario_id}` | Scenario detail |
| POST | `/{scenario_id}/start` | Begin run |
| POST | `/{scenario_id}/next-step` | Advance one step |
| POST | `/{scenario_id}/command` | Issue command mid-run |
| POST | `/{scenario_id}/reset` | Reset to IDLE |

### Events (SSE) — `/events`
| Method | Path | Purpose |
|---|---|---|
| GET | `/stream` | SSE channel: alarms, network-health, sim-updates, heartbeat (15s) |

### Teams — `/teams`
| Method | Path | Purpose |
|---|---|---|
| GET | `/config` | Returns Teams client/tenant IDs + enabled flag |
| POST | `/alert` | Push operator alert to Teams channel |

### Energy — `/energy`
| Method | Path | Purpose |
|---|---|---|
| GET | `/load-profile` | 24h profile by tariff class |
| GET | `/daily-summary` | 7–30 day rollup |
| GET | `/meter-status` | Paginated meter status list |

### Reports — `/reports`
| Method | Path | Purpose |
|---|---|---|
| GET | `/consumption` | By date range / feeder / tariff class |
| GET | `/meter-readings` | Cumulative + daily breakdown |
| GET | `/top-consumers` | Top N by consumption |

### Audit — `/audit`
| Method | Path | Purpose |
|---|---|---|
| GET | `/events` | Filter by type/user/date (paginated) |
| GET | `/summary` | Distinct types + user list |

### HES Mirror — `/hes`
| Method | Path | Purpose |
|---|---|---|
| GET | `/dcus` | DCU inventory + health |
| GET | `/commands` | Command log (paginated) |
| GET | `/fota` | FOTA job list |
| GET | `/firmware-distribution` | Firmware version histogram |
| GET | `/comm-trend` | 7–14 day comm success trend |

### MDMS Mirror — `/mdms`
| Method | Path | Purpose |
|---|---|---|
| GET | `/vee/summary` | Daily VEE counts |
| GET | `/vee/exceptions` | Pending exceptions |
| GET | `/consumers` | Consumer master (search by name/serial) |
| GET | `/tariffs` | TOU schedules |
| GET | `/ntl` | NTL suspects (filter by flag) |
| GET | `/power-quality` | PQ zones |

### Reconciler — `/reconciler`
| Method | Path | Purpose |
|---|---|---|
| GET | `/summary` | Combined compliance + feature status |
| GET | `/compliance` | Compliance audit results |
| GET | `/compliance/matrix` | Aggregated matrix across standards |
| GET | `/features` | Feature completion status |
| GET | `/reconciliation` | Run history (paginated) |
| GET | `/reconciliation/{run_id}/findings` | Findings per run |
| GET | `/standards` | Indexed IEC standard docs |
| GET | `/history` | Combined run history |

## Middleware & Cross-cutting

- **CORS**: dev origins (`http://localhost:5173`, `:3000`, `:3001`, `frontend:80`); override via `ALLOWED_ORIGINS`
- **OpenTelemetry**: initialised in lifespan via `otel_common` — traces + metrics to OTel Collector (`OTEL_COLLECTOR_ENDPOINT`)
- **Structured logging**: `structlog` with OTel trace/span injection
- **Audit**: operator actions persisted to `audit_events`; also published to Kafka `mdms.audit.actions` where configured

## Schemas

Pydantic request/response models are defined inline in each endpoint module (no `app/schemas/` package). Examples: `LoginRequest`, `TokenResponse`, `AlarmAcknowledge`, `ScenarioCommand`, `SensorThresholdUpdate`.

## Services Layer — `app/services/`

| File | Responsibility |
|---|---|
| `simulation_engine.py` | Physics-based scenario stepping (voltage/power flow, DER curtailment) |
| `hes_client.py` | HTTP client for HES routing-service (commands, inventory) |
| `mdms_client.py` | HTTP client for MDMS (VEE, CIS, prepaid) |
| `notification_service.py` | Teams / email / SMS fan-out |
