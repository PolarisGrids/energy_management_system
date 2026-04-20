# Contract: EMS ↔ MDMS Integration

**EMS as consumer.** MDMS owns the data; EMS reads and proxies.

## Transport

- HTTP/1.1 or HTTP/2 over TLS 1.2+ via internal EKS service DNS
- Primary upstream: `http://mdms-api.mdms.svc.cluster.local:8080`
- Gateway in EMS: `/api/v1/mdms/*` pass-through with W3C trace-context
- Timeouts: 5 s connect, 10 s read; 3 retries with 100 ms exponential backoff; circuit breaker opens after 5 consecutive failures for 30 s
- Headers EMS MUST propagate: `traceparent`, `tracestate`, `x-user-story-id`, `x-user-id`, `x-operator-ip`
- Headers EMS MUST set: `x-forwarded-for`, `user-agent: polaris-ems/<version>`

## Endpoints EMS Consumes

| EMS Path | MDMS Backing | Purpose | Feature flag |
|---|---|---|---|
| `GET /api/v1/mdms/cis/consumers` | `mdms-cis-service` | Consumer master query (filters: search, hierarchy) | `MDMS_ENABLED` |
| `GET /api/v1/mdms/cis/consumers/:account` | `mdms-cis-service` | Consumer detail incl. hierarchy, tariff class | `MDMS_ENABLED` |
| `GET /api/v1/mdms/cis/hierarchy?node=` | `mdms-cis-service` | Substation → pole tree | `MDMS_ENABLED` |
| `GET /api/v1/mdms/readings?meter=&from=&to=&interval=` | `mdms-db-service` (joined MV) | Interval / daily / monthly reads | `MDMS_ENABLED` |
| `GET /api/v1/mdms/vee/summary?date=` | `mdms_vee_service` | Today's VEE counts by rule/method | `MDMS_ENABLED` |
| `GET /api/v1/mdms/vee/exceptions?rule=&date=&page=` | `mdms_vee_service` | Paginated exceptions | `MDMS_ENABLED` |
| `POST /api/v1/mdms/vee/edit` | `mdms_vee_service` | Manual read override (audited) | `MDMS_ENABLED` |
| `GET /api/v1/mdms/tariffs` | `mdms-billing-engine` | Tariff schedules | `MDMS_ENABLED` |
| `GET /api/v1/mdms/tariffs/:id` | `mdms-billing-engine` | Tariff detail incl. tiers (MDMS-T1) + seasonal (MDMS-T1) | `TARIFF_INCLINING_ENABLED` for tier fields |
| `GET /api/v1/mdms/billing-determinants?account=&month=` | `mdms-billing-engine` | Applied tariff per account-month | `MDMS_ENABLED` |
| `GET /api/v1/mdms/prepaid/registers?account=` | `mdms-prepaid-engine` | 13 prepaid registers | `MDMS_ENABLED` |
| `GET /api/v1/mdms/prepaid/token-log?account=` | `mdms-cis-service` | Token history | `MDMS_ENABLED` |
| `POST /api/v1/mdms/prepaid/recharge` | `mdms-prepaid-engine` | Issue recharge token | `MDMS_ENABLED` |
| `GET /api/v1/mdms/ntl/suspects?dtr=&from=` | `mdms-ntl-service` (MDMS-T2) | Suspicion list | `MDMS_NTL_ENABLED` |
| `GET /api/v1/mdms/ntl/energy-balance?dtr=` | `mdms-ntl-service` | Feeder balance gap | `MDMS_NTL_ENABLED` |
| `GET /api/v1/mdms/analytics/load-profile?class=&from=&to=` | `mdms-analytics-service` (MDMS-T3) | p10/p50/p90 half-hour curves | `MDMS_ENABLED` (degraded without T3) |
| `GET /api/v1/mdms/reports/egsm/:category/:report?*` | `mdms-reports` + `mdms-analytics-service` | 6 categories, ~52 endpoints | `MDMS_ENABLED` |
| `GET /api/v1/mdms/reports/download?id=` | `mdms-reports` CSV pipeline (S3+SQS) | Download CSV link | `MDMS_ENABLED` |
| `GET /api/v1/mdms/gis/layers?bbox=&layers=` | `mdms-cis-service` PostGIS (phase-b/014) | GeoJSON feeder/DTR/pole/meter | `MDMS_ENABLED` |
| `GET /api/v1/mdms/cmd-exec/history?*` | `mdms-cmd-exec-service` | Command execution log | `MDMS_ENABLED` |
| `GET /api/v1/mdms/audit/events?*` | `mdms-cis-service` `action_audit_log` | Cross-service audit trail | `MDMS_ENABLED` |
| `POST /api/v1/mdms/wfm/work-orders` | `mdms-wfm` (MDMS-T6) | Dispatch from outage | `WFM_ENABLED` |

## Payload Conventions

- Timestamps: ISO 8601 with `Asia/Kolkata` offset (existing MDMS convention).
- IDs: MDMS-canonical meter_serial, account_no, consumer_id.
- Pagination: `?page=&page_size=` with `Link` header for next/prev.
- Error envelope: `{error: {code, message, trace_id, details?}}` with HTTP status.

## EMS Circuit-Breaker Behaviour

- On open breaker, `/api/v1/mdms/*` returns `503` with `{error:{code:"UPSTREAM_MDMS_UNAVAILABLE"}}`. Frontend renders red banner with `last_successful_refresh_ts` and auto-retries every 30 s.
- In `SSOT_MODE=mirror`, EMS may return last-cached response for reads with `x-from-cache: true`; write endpoints never serve from cache.
- In `SSOT_MODE=strict`, no cache fallback.

## Trace & Audit

- EMS forwards `traceparent`/`tracestate` unchanged.
- On every request, EMS emits `audit()` with `service_name=polaris-ems`, `action_type=READ` (or WRITE), `entity_type=<domain>`, `method`, `path`, `response_status`, `duration_ms`.

## Test Fixtures

- `tests/integration/fixtures/mdms/`: recorded responses for each endpoint using `respx` or real dev calls.
- `tests/integration/mdms_integration/`: tests against a dev mdms-api pod; marker `@pytest.mark.live_mdms` gates in CI.
