# Polaris EMS — k6 load test (spec 018 W5.T50)

Validates NFR-001 (dashboard warm ≤ 2 s), NFR-002 (SSE ≤ 3 s), NFR-005
(zero route errors) and SC-005 (50 concurrent operator sessions) against
a dev-EKS deployment.

## Install k6

macOS: `brew install k6`
Linux: `sudo apt-get install -y k6` (after adding Grafana apt repo)
Container: `docker run --rm grafana/k6 version`

## Run

**Production-style run** (50 VUs, ~42 min total):

```bash
export POLARIS_JWT=<operator-role jwt with read scope>

k6 run ops/loadtest/k6-scenarios.js \
  --env BASE_URL=https://vidyut360.dev.polagram.in \
  --env TOKEN=$POLARIS_JWT
```

**Smoke run** (5 VUs, 60 s — use to validate the script before a long run):

```bash
k6 run ops/loadtest/k6-scenarios.js \
  --env BASE_URL=https://vidyut360.dev.polagram.in \
  --env TOKEN=$POLARIS_JWT \
  --env SMOKE=1
```

**Export to Prometheus** (optional — requires `k6 cloud` or the k6 Prom
remote-write output):

```bash
k6 run --out experimental-prometheus-rw=http://prometheus.observability:9090/api/v1/write ...
```

A JSON summary is written to `ops/loadtest/last-summary.json` after each
run; commit artifacts only when the run is a release-candidate baseline.

## Scenario mix

| Weight | Scenario | Endpoints hit |
| --- | --- | --- |
| 50 % | dashboard poll | `/api/v1/dashboards`, `/api/v1/meters/summary` |
| 20 % | alarm list | `/api/v1/alarms?state=open&limit=50` |
| 10 % | meter search | `/api/v1/meters?q=<term>&limit=20` |
| 10 % | report run | `/api/v1/reports?category=energy&limit=5` |
| 10 % | SSE connect | `/api/v1/sse?topics=alarms,meters` (held 60 s) |

## Thresholds (automatic fail)

| Threshold | Target | Rationale |
| --- | --- | --- |
| `http_req_failed` | < 1 % | NFR-005 |
| `dashboard_duration_ms p95` | < 2000 | NFR-001 |
| `alarm_list_duration_ms p95` | < 2500 | operator responsiveness |
| `meter_search_duration_ms p95` | < 2500 | operator responsiveness |
| `report_run_duration_ms p95` | < 5000 | tolerant for heavy analytical reads |
| `sse_first_event_ms p95` | < 3000 | NFR-002 |
| `sse_failures_rate` | < 5 % | NFR-007 (SSE resilience) |

## Expected output (sample — SMOKE=1 against a healthy dev deploy)

```
     checks.........................: 100.00% ✓ 612       ✗ 0
     data_received..................: 18 MB  298 kB/s
     data_sent......................: 196 kB 3.3 kB/s
     http_req_blocked...............: avg=1.2ms  p(95)=2ms
     http_req_duration..............: avg=612ms  p(95)=1.78s
     http_req_failed................: 0.00%   ✓ 0         ✗ 612
     iterations.....................: 204    3.4/s
     dashboard_duration_ms..........: avg=1324ms p(95)=1920ms
     alarm_list_duration_ms.........: avg=710ms  p(95)=1350ms
     meter_search_duration_ms.......: avg=620ms  p(95)=1280ms
     report_run_duration_ms.........: avg=2100ms p(95)=3900ms
     sse_first_event_ms.............: avg=380ms  p(95)=820ms
     sse_failures_rate..............: 0.00%

== Polaris EMS load test summary ==
VUs max:               5
Total HTTP requests:   612
HTTP error rate:       0.00%
Dashboard duration:    1920 ms p95
Alarm list duration:   1350 ms p95
Meter search duration: 1280 ms p95
Report run duration:   3900 ms p95
SSE first event:       820 ms p95
SSE failure rate:      0.00%
```

If any threshold is breached k6 exits non-zero — CI can gate merges on it.

## Troubleshooting

- **403/401 spam** — token missing or expired; mint a new service JWT.
- **SSE threshold misses only** — check pod CPU throttling and Redis
  pub/sub latency (NFR-007 relies on the shared store); see the Service
  Overview dashboard in Grafana.
- **Single VU bursts of 5xx** — check `http_req_failed` per scenario
  tag (`--summary-trend-stats "p(95),count"`) to isolate.
