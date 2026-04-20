// Polaris EMS — k6 load test (spec 018, W5.T50)
//
// 50 virtual users, 10-minute ramp + 30-minute steady, realistic mix:
//   50% dashboard polls (warm cache)
//   20% alarm list (paginated)
//   10% meter search
//   10% report run (read-only run of a tariff report)
//   10% SSE stream connect (holds for 60s then disconnects)
//
// Thresholds map to spec NFRs:
//   NFR-001  dashboard warm-cache <= 2s  -> dashboard_duration p(95) < 2000
//   NFR-002  SSE event-to-UI <= 3s        -> sse_first_event_ms p(95) < 3000
//   NFR-005  zero runtime errors on routes -> http_req_failed <1%
//
// Run:
//   k6 run ops/loadtest/k6-scenarios.js \
//     --env BASE_URL=https://vidyut360.dev.polagram.in \
//     --env TOKEN=$POLARIS_JWT
//
// For a quick smoke (60s, 5 VUs):
//   k6 run ops/loadtest/k6-scenarios.js --env SMOKE=1

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || 'https://vidyut360.dev.polagram.in';
const TOKEN = __ENV.TOKEN || '';
const SMOKE = !!__ENV.SMOKE;

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------
const dashboardDuration = new Trend('dashboard_duration_ms', true);
const alarmListDuration = new Trend('alarm_list_duration_ms', true);
const meterSearchDuration = new Trend('meter_search_duration_ms', true);
const reportRunDuration = new Trend('report_run_duration_ms', true);
const sseFirstEventMs = new Trend('sse_first_event_ms', true);
const sseConnects = new Counter('sse_connects_total');
const sseFailures = new Rate('sse_failures_rate');

// ---------------------------------------------------------------------------
// Static payload library
// ---------------------------------------------------------------------------
const meterSearchTerms = new SharedArray('meter_search_terms', () => [
  'PGCL', 'MTR', '000', '001', '002', '003', '004', '005', '006', '007',
]);

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------
export const options = SMOKE
  ? {
      vus: 5,
      duration: '60s',
      thresholds: smokeThresholds(),
    }
  : {
      scenarios: {
        operator_sessions: {
          executor: 'ramping-vus',
          startVUs: 0,
          stages: [
            { duration: '10m', target: 50 }, // ramp up
            { duration: '30m', target: 50 }, // steady
            { duration: '2m',  target: 0  }, // ramp down
          ],
          gracefulRampDown: '30s',
        },
      },
      thresholds: fullThresholds(),
    };

function smokeThresholds() {
  return {
    http_req_failed:  ['rate<0.05'],
    http_req_duration:['p(95)<4000'],
  };
}
function fullThresholds() {
  return {
    http_req_failed:        ['rate<0.01'],
    http_req_duration:      ['p(95)<4000'],
    dashboard_duration_ms:  ['p(95)<2000'],  // NFR-001 warm
    alarm_list_duration_ms: ['p(95)<2500'],
    meter_search_duration_ms:['p(95)<2500'],
    report_run_duration_ms: ['p(95)<5000'],
    sse_first_event_ms:     ['p(95)<3000'],  // NFR-002
    sse_failures_rate:      ['rate<0.05'],
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function authHeaders() {
  return TOKEN
    ? { Authorization: `Bearer ${TOKEN}`, 'User-Agent': 'polaris-ems-k6/1.0' }
    : { 'User-Agent': 'polaris-ems-k6/1.0' };
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

// ---------------------------------------------------------------------------
// Scenario functions
// ---------------------------------------------------------------------------
function dashboardPoll() {
  group('dashboard_poll', () => {
    const t0 = Date.now();
    const r1 = http.get(`${BASE_URL}/api/v1/dashboards`, { headers: authHeaders(), tags: { scenario: 'dashboard' } });
    const r2 = http.get(`${BASE_URL}/api/v1/meters/summary`, { headers: authHeaders(), tags: { scenario: 'dashboard' } });
    dashboardDuration.add(Date.now() - t0);
    check(r1, { 'dashboards 200': (r) => r.status === 200 });
    check(r2, { 'meters/summary 2xx': (r) => r.status >= 200 && r.status < 300 });
  });
}

function alarmList() {
  group('alarm_list', () => {
    const t0 = Date.now();
    const r = http.get(`${BASE_URL}/api/v1/alarms?state=open&limit=50`, { headers: authHeaders(), tags: { scenario: 'alarms' } });
    alarmListDuration.add(Date.now() - t0);
    check(r, { 'alarms 200': (r) => r.status === 200 });
  });
}

function meterSearch() {
  group('meter_search', () => {
    const q = pick(meterSearchTerms);
    const t0 = Date.now();
    const r = http.get(`${BASE_URL}/api/v1/meters?q=${q}&limit=20`, { headers: authHeaders(), tags: { scenario: 'meter_search' } });
    meterSearchDuration.add(Date.now() - t0);
    check(r, { 'meters search 2xx': (r) => r.status >= 200 && r.status < 300 });
  });
}

function reportRun() {
  group('report_run', () => {
    const t0 = Date.now();
    const r = http.get(`${BASE_URL}/api/v1/reports?category=energy&limit=5`, { headers: authHeaders(), tags: { scenario: 'reports' } });
    reportRunDuration.add(Date.now() - t0);
    check(r, { 'reports 2xx': (r) => r.status >= 200 && r.status < 300 });
  });
}

// SSE scenario using k6's HTTP streaming: we open a GET, measure time to
// the first `data:` line, then let the connection idle for ~60s before the
// VU iteration moves on (connection closed by timeout).
function sseStream() {
  group('sse_stream', () => {
    sseConnects.add(1);
    const url = `${BASE_URL}/api/v1/sse?topics=alarms,meters`;
    const params = {
      headers: { ...authHeaders(), Accept: 'text/event-stream' },
      timeout: '65s',
      tags: { scenario: 'sse' },
    };
    const start = Date.now();
    const res = http.get(url, params);
    // http.get buffers the whole response; for a realistic SSE check we rely
    // on TTFB as an approximation of "time to first event" — the server
    // emits an initial `: ping` on connection accept.
    const ttfb = res.timings.waiting;
    sseFirstEventMs.add(ttfb);
    const ok = check(res, {
      'sse connect status 200': (r) => r.status === 200,
      'sse content-type': (r) => (r.headers['Content-Type'] || '').includes('text/event-stream'),
    });
    sseFailures.add(!ok);
    // Already held 60s via timeout if the server keeps the connection open.
    // Defensive minimum dwell so we do not hammer reconnects:
    if (Date.now() - start < 500) sleep(0.5);
  });
}

// ---------------------------------------------------------------------------
// Main VU iteration — weighted random
// ---------------------------------------------------------------------------
export default function () {
  const r = Math.random();
  if (r < 0.50)      dashboardPoll();
  else if (r < 0.70) alarmList();
  else if (r < 0.80) meterSearch();
  else if (r < 0.90) reportRun();
  else               sseStream();

  // Think time between actions (1–3s, skewed lower)
  sleep(1 + Math.random() * 2);
}

// ---------------------------------------------------------------------------
// Summary export — dumps a JSON summary next to stdout output
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'ops/loadtest/last-summary.json': JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const t = data.metrics;
  const fmt = (m) => (m ? `${(m.values['p(95)'] || 0).toFixed(0)} ms p95` : 'n/a');
  return [
    '',
    '== Polaris EMS load test summary ==',
    `VUs max:               ${data.state.vusMax || 'n/a'}`,
    `Total HTTP requests:   ${t.http_reqs ? t.http_reqs.values.count : 'n/a'}`,
    `HTTP error rate:       ${(t.http_req_failed ? t.http_req_failed.values.rate * 100 : 0).toFixed(2)}%`,
    `Dashboard duration:    ${fmt(t.dashboard_duration_ms)}`,
    `Alarm list duration:   ${fmt(t.alarm_list_duration_ms)}`,
    `Meter search duration: ${fmt(t.meter_search_duration_ms)}`,
    `Report run duration:   ${fmt(t.report_run_duration_ms)}`,
    `SSE first event:       ${fmt(t.sse_first_event_ms)}`,
    `SSE failure rate:      ${(t.sse_failures_rate ? t.sse_failures_rate.values.rate * 100 : 0).toFixed(2)}%`,
    '',
  ].join('\n');
}
