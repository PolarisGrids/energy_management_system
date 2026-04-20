import axios from 'axios'

// Base URL is overridable via VITE_API_BASE so the app can run against a
// standalone dev pod (e.g. polaris-ems.dev.polarisgrid.co.za) without an
// nginx reverse-proxy. Default stays as the relative /api/v1 so the
// in-cluster nginx sidecar keeps working.
const api = axios.create({
  baseURL: import.meta?.env?.VITE_API_BASE || '/api/v1',
  timeout: 15000,
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('smoc_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  // Propagate a user-story id if the page set one (spec 018 observability).
  const storyId = window.__POLARIS_USER_STORY_ID__
  if (storyId) config.headers['x-user-story-id'] = storyId
  return config
})

// Handle 401 globally — but ONLY for our own auth failures. The SSOT proxy
// (/api/v1/hes/*, /api/v1/mdms/*) forwards to upstream services that use
// Cognito JWTs with a different audience, so they will legitimately 401
// even with a valid SMOC token. Those must NOT log the user out.
const PROXY_PATH_RE = /^\/?(hes|mdms)\//
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const reqUrl = err.config?.url || ''
      const isProxy = PROXY_PATH_RE.test(reqUrl)
      if (!isProxy) {
        localStorage.removeItem('smoc_token')
        localStorage.removeItem('smoc_user')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// Auth
export const authAPI = {
  login: (username, password) => api.post('/auth/login', { username, password }),
  me: () => api.get('/auth/me'),
}

// Meters
export const metersAPI = {
  list: (params) => api.get('/meters/', { params }),
  summary: () => api.get('/meters/summary'),
  get: (serial) => api.get(`/meters/${serial}`),
  connect: (serial) => api.post(`/meters/${serial}/connect`),
  disconnect: (serial) => api.post(`/meters/${serial}/disconnect`),
  feeders: () => api.get('/meters/feeders/list'),
  transformers: (feederId) => api.get('/meters/transformers/list', { params: { feeder_id: feederId } }),
}

// Alarms
export const alarmsAPI = {
  list: (params) => api.get('/alarms/', { params }),
  active: () => api.get('/alarms/active'),
  acknowledge: (id, by) => api.post(`/alarms/${id}/acknowledge`, { acknowledged_by: by }),
  resolve: (id, by) => api.post(`/alarms/${id}/resolve`, { resolved_by: by }),
}

// DER
export const derAPI = {
  list: (type) => api.get('/der/', { params: type ? { asset_type: type } : {} }),
  get: (id) => api.get(`/der/${id}`),
  command: (id, cmd) => api.post(`/der/${id}/command`, cmd),
  // Spec 018 W3.T11/T12 — telemetry reads + feeder aggregation
  telemetry: (params = {}) => api.get('/der/telemetry', { params }),
  feederAggregate: (feederId, window = '24h') =>
    api.get(`/der/feeder/${feederId}/aggregate`, { params: { window } }),
}

// Reverse-flow (spec 018 W3.T13)
export const reverseFlowAPI = {
  active: () => api.get('/reverse-flow/active'),
  forFeeder: (feederId) => api.get(`/reverse-flow/feeder/${feederId}`),
  list: (params = {}) => api.get('/reverse-flow/', { params }),
}

// Simulation proxy (spec 018 W3.T14) — calls upstream simulator via EMS backend
export const simulationProxyAPI = {
  scenarios: () => api.get('/simulation-proxy/scenarios'),
  scenarioStatus: (name) => api.get(`/simulation-proxy/scenarios/${name}/status`),
  scenarioStart: (name, payload = {}) =>
    api.post(`/simulation-proxy/scenarios/${name}/start`, payload),
  scenarioStep: (name, payload = {}) =>
    api.post(`/simulation-proxy/scenarios/${name}/step`, payload),
  scenarioStop: (name) => api.post(`/simulation-proxy/scenarios/${name}/stop`),
  sequences: () => api.get('/simulation-proxy/sequences'),
  sequenceStart: (name, payload = {}) =>
    api.post(`/simulation-proxy/sequences/${name}/start`, payload),
  sequenceStatus: (name) => api.get(`/simulation-proxy/sequences/${name}/status`),
}

// Readings
export const readingsAPI = {
  interval: (serial, hours) => api.get(`/readings/${serial}/interval`, { params: { hours } }),
  latest: (serial) => api.get(`/readings/${serial}/latest`),
}

// Sensors
export const sensorsAPI = {
  list: (params) => api.get('/sensors/', { params }),
  byTransformer: (transformerId) => api.get(`/sensors/transformer/${transformerId}`),
  history: (sensorId, hours = 24) => api.get(`/sensors/${sensorId}/history`, { params: { hours } }),
  updateThreshold: (sensorId, data) => api.post(`/sensors/${sensorId}/threshold`, data),
}

// Simulation
export const simulationAPI = {
  list: () => api.get('/simulation/'),
  get: (id) => api.get(`/simulation/${id}`),
  start: (id, params) => api.post(`/simulation/${id}/start`, { parameters: params }),
  nextStep: (id) => api.post(`/simulation/${id}/next-step`),
  command: (id, cmd) => api.post(`/simulation/${id}/command`, cmd),
  reset: (id) => api.post(`/simulation/${id}/reset`),
}

// Energy
export const energyAPI = {
  loadProfile: (params) => api.get('/energy/load-profile', { params }),
  dailySummary: (params) => api.get('/energy/daily-summary', { params }),
  meterStatus: (params) => api.get('/energy/meter-status', { params }),
}

// Reports
export const reportsAPI = {
  consumption: (params) => api.get('/reports/consumption', { params }),
  meterReadings: (params) => api.get('/reports/meter-readings', { params }),
  topConsumers: (params) => api.get('/reports/top-consumers', { params }),
}

// Audit
export const auditAPI = {
  events: (params) => api.get('/audit/events', { params }),
  summary: () => api.get('/audit/summary'),
}

// Outages (spec 018 W3)
export const outagesAPI = {
  list: (params) => api.get('/outages', { params }),
  get: (id) => api.get(`/outages/${id}`),
  acknowledge: (id, payload = {}) => api.post(`/outages/${id}/acknowledge`, payload),
  addNote: (id, note) => api.post(`/outages/${id}/note`, { note }),
  dispatchCrew: (id, payload) => api.post(`/outages/${id}/dispatch-crew`, payload),
  flisrIsolate: (id, payload = {}) => api.post(`/outages/${id}/flisr/isolate`, payload),
  flisrRestore: (id, payload = {}) => api.post(`/outages/${id}/flisr/restore`, payload),
  gisOverlay: (params) => api.get('/gis/outages', { params }),
}

// ─── MDMS + HES integration APIs ───────────────────────────────────────────
// Originally these hit /api/v1/mdms/* and /api/v1/hes/* SSOT proxies, but
// those forward to upstream HES/MDMS which use a different Cognito
// audience than SMOC's session JWT — every call 401'd, triggering the
// global logout interceptor.
//
// Repointed (2026-04-19) to the EMS-side `/hes-mirror/*`, `/mdms-mirror/*`
// and `/meters/summary` endpoints. These read from SMOC's own tables
// (synced from MDMS and HES) so the numbers are the same real data the
// proxy would return, without the cross-audience auth mismatch.

// MDMS-equivalent calls (served from /mdms-mirror/* + EMS-native fallbacks).
export const mdmsAPI = {
  // CIS
  consumers: (params) => api.get('/mdms-mirror/consumers', { params }),
  consumer: (account) => api.get('/mdms-mirror/consumers', { params: { account } }),
  hierarchy: () => api.get('/meters/summary'),  // has total_transformers + total_feeders
  // Readings
  readings: (params) => api.get('/readings', { params }),
  // VEE
  veeSummary: (params) => api.get('/mdms-mirror/vee/summary', { params }),
  veeExceptions: (params) => api.get('/mdms-mirror/vee/exceptions', { params }),
  // Tariff / Billing
  tariffs: () => api.get('/mdms-mirror/tariffs'),
  tariff: (id) => api.get('/mdms-mirror/tariffs', { params: { id } }),
  billingDeterminants: (params) => api.get('/reports/meter-readings', { params }),
  // Prepaid — kept on proxy (no mirror); caller must handle errors without logout.
  prepaidRegisters: (account) => api.get('/mdms/api/v1/prepaid/registers', { params: { account } }),
  prepaidTokenLog: (account) => api.get('/mdms/api/v1/prepaid/token-log', { params: { account } }),
  prepaidRecharge: (payload) => api.post('/mdms/api/v1/prepaid/recharge', payload),
  // NTL
  ntlSuspects: (params) => api.get('/mdms-mirror/ntl', { params }),
  ntlEnergyBalance: (dtr) => api.get('/mdms-mirror/ntl', { params: { dtr } }),
  // Analytics / reports
  loadProfile: (params) => api.get('/energy/load-profile', { params }),
  report: (category, report, params) =>
    api.get(`/reports/${report}`, { params: { ...params, category } }),
  reportDownload: (id) => api.get('/reports/download', { params: { id } }),
  // GIS — EMS-native GeoJSON layer endpoint
  gisLayers: (bbox, layers) => {
    const layer = Array.isArray(layers) ? layers[0] : layers
    return api.get('/gis/layers', { params: { bbox, layer } })
  },
  // Power quality
  powerQuality: () => api.get('/mdms-mirror/power-quality'),
}

// HES-equivalent calls (served from /hes-mirror/* + EMS-native fallbacks).
export const hesAPI = {
  dcus: () => api.get('/hes-mirror/dcus'),
  dcuHealth: (id) => api.get('/hes-mirror/dcus', { params: { id } }),
  networkHealth: () => api.get('/meters/summary'),  // same shape: online/offline/comm rate/tamper/alarms
  commands: (params) => api.get('/hes-mirror/commands', { params }),
  // Writes stay on proxy — real command dispatch must reach upstream HES.
  postCommand: (payload) => api.post('/hes/api/v1/commands', payload),
  postCommandBatch: (payload) => api.post('/hes/api/v1/commands/batch', payload),
  fota: () => api.get('/hes-mirror/fota'),
  fotaJob: (id) => api.get('/hes-mirror/fota', { params: { id } }),
  firmwareDistribution: () => api.get('/hes-mirror/firmware-distribution'),
  commTrend: (params) => api.get('/hes-mirror/comm-trend', { params }),
}

// ─── Legacy mirror DB APIs ──────────────────────────────────────────────────
// Kept for the AuditLog and any page still reading seeded rows. Will be
// retired at the end of Wave 2 when every consumer is on the proxy.
export const hesMirrorAPI = {
  dcus: () => api.get('/hes-mirror/dcus'),
  commands: (params) => api.get('/hes-mirror/commands', { params }),
  fota: () => api.get('/hes-mirror/fota'),
  firmwareDistribution: () => api.get('/hes-mirror/firmware-distribution'),
  commTrend: (params) => api.get('/hes-mirror/comm-trend', { params }),
}

export const mdmsMirrorAPI = {
  veeSummary: (params) => api.get('/mdms-mirror/vee/summary', { params }),
  veeExceptions: (params) => api.get('/mdms-mirror/vee/exceptions', { params }),
  consumers: (params) => api.get('/mdms-mirror/consumers', { params }),
  tariffs: () => api.get('/mdms-mirror/tariffs'),
  ntl: (params) => api.get('/mdms-mirror/ntl', { params }),
  powerQuality: () => api.get('/mdms-mirror/power-quality'),
}

// ─── GIS (spec 018 W3.T5/T6) — EMS-native layer endpoints backed by PostGIS ──
// These hit the EMS `/gis/*` router (distinct from the MDMS proxy
// `mdmsAPI.gisLayers` which is only used when MDMS owns the topology copy).
export const gisAPI = {
  layer: (layer, bbox, limit = 2000) =>
    api.get('/gis/layers', { params: { layer, bbox, limit } }),
  heatmapAlarms: (bbox, gridDeg = 0.1) =>
    api.get('/gis/heatmap/alarms', { params: { bbox, grid_deg: gridDeg } }),
}

// ─── NTL (spec 018 W3.T8/T9/T10) — suspects + energy-balance dashboard ───────
export const ntlAPI = {
  suspects: (params) => api.get('/ntl/suspects', { params }),
  energyBalance: (params) => api.get('/ntl/energy-balance', { params }),
  topGaps: (params) => api.get('/ntl/energy-balance/top', { params }),
  suspectsGeoJson: (bbox, minScore = 30) =>
    api.get('/ntl/suspects/geojson', { params: { bbox, min_score: minScore } }),
}

// ─── Consumption (spec 018 Wave 5 "no-mock" — real MDMS aggregates) ─────────
// Backend peer exposes /api/v1/consumption/* with envelope:
//   { ok, data, source: 'mdms'|'ems-local'|'partial', as_of }
// UI must render the envelope's `data` and surface a banner when source != 'mdms'.
// Never fall back to hardcoded numbers — if the endpoint fails, show empty state.
export const consumptionAPI = {
  summary:          (params) => api.get('/consumption/summary',          { params }),
  loadProfile:     (params) => api.get('/consumption/load-profile',     { params }),
  feederBreakdown: (params) => api.get('/consumption/feeder-breakdown', { params }),
  byClass:         (params) => api.get('/consumption/by-class',         { params }),
  monthly:         (params) => api.get('/consumption/monthly',          { params }),
}

// ─── Devices (spec 018 Wave 5) — typeahead + hierarchy lookup ───────────────
// Backend peer exposes /api/v1/devices/* with the same envelope.
export const devicesAPI = {
  search:    (params) => api.get('/devices/search',    { params }),
  hierarchy: (params) => api.get('/devices/hierarchy', { params }),
}

// ─── Health probe ──
export const healthAPI = {
  get: () => api.get('/health'),
}

// ─── Reconciler (IEC compliance, spec 002) stub so pages don't crash ──
export const reconcilerAPI = {
  summary: () => api.get('/reconciler/summary').catch(() => ({ data: {} })),
  issues: (params) => api.get('/reconciler/issues', { params }).catch(() => ({ data: [] })),
}

// ─── Saved dashboard layouts (spec 018 W4.T11) ──
export const dashboardsAPI = {
  list: () => api.get('/dashboards'),
  get: (id) => api.get(`/dashboards/${id}`),
  create: (payload) => api.post('/dashboards', payload),
  update: (id, payload) => api.patch(`/dashboards/${id}`, payload),
  remove: (id) => api.delete(`/dashboards/${id}`),
  duplicate: (id) => api.post(`/dashboards/${id}/duplicate`),
}

// ─── Data Accuracy console (spec 018 W4.T14) ──
export const dataAccuracyAPI = {
  list: (params) => api.get('/data-accuracy', { params }),
  refresh: () => api.post('/data-accuracy/refresh'),
  reconcile: (serial) => api.post(`/data-accuracy/${serial}/reconcile`),
}

// ─── AppBuilder (spec 018 W4.T6/T7/T8) ──
// Backed by /api/v1/apps, /api/v1/app-rules, /api/v1/algorithms. Publish
// endpoints pass X-User-Role when the frontend has a role hint — real RBAC
// lookup is Agent N's job (spec 018 Wave 4 RBAC track).
const _withPublishRole = (role) =>
  role ? { headers: { 'X-User-Role': role } } : {}

export const appBuilderAPI = {
  // Apps
  listApps: (params) => api.get('/apps', { params }),
  getApp: (slug) => api.get(`/apps/${slug}`),
  getAppVersions: (slug) => api.get(`/apps/${slug}/versions`),
  getAppPublished: (slug) => api.get(`/apps/${slug}/published`),
  createApp: (payload) => api.post('/apps', payload),
  updateApp: (slug, payload) => api.put(`/apps/${slug}`, payload),
  previewApp: (slug) => api.post(`/apps/${slug}/preview`),
  publishApp: (slug, payload = {}, role) =>
    api.post(`/apps/${slug}/publish`, payload, _withPublishRole(role)),
  archiveApp: (slug, role) =>
    api.post(`/apps/${slug}/archive`, {}, _withPublishRole(role)),
  deleteApp: (slug, role) => api.delete(`/apps/${slug}`, _withPublishRole(role)),

  // App-scope rules
  listRules: (params) => api.get('/app-rules', { params }),
  getRule: (slug) => api.get(`/app-rules/${slug}`),
  createRule: (payload) => api.post('/app-rules', payload),
  updateRule: (slug, payload) => api.put(`/app-rules/${slug}`, payload),
  publishRule: (slug, payload = {}, role) =>
    api.post(`/app-rules/${slug}/publish`, payload, _withPublishRole(role)),
  deleteRule: (slug, role) => api.delete(`/app-rules/${slug}`, _withPublishRole(role)),

  // Python algorithms
  listAlgorithms: () => api.get('/algorithms'),
  getAlgorithm: (slug) => api.get(`/algorithms/${slug}`),
  getAlgorithmVersions: (slug) => api.get(`/algorithms/${slug}/versions`),
  createAlgorithm: (payload) => api.post('/algorithms', payload),
  updateAlgorithm: (slug, payload) => api.put(`/algorithms/${slug}`, payload),
  runAlgorithm: (slug, payload) => api.post(`/algorithms/${slug}/run`, payload),
  previewAlgorithm: (slug) => api.post(`/algorithms/${slug}/preview`),
  publishAlgorithm: (slug, payload = {}, role) =>
    api.post(`/algorithms/${slug}/publish`, payload, _withPublishRole(role)),
  deleteAlgorithm: (slug, role) =>
    api.delete(`/algorithms/${slug}`, _withPublishRole(role)),
}

// ─── Scheduled reports (spec 018 W4.T10) ──
export const scheduledReportsAPI = {
  list: () => api.get('/reports/scheduled'),
  get: (id) => api.get(`/reports/scheduled/${id}`),
  create: (payload) => api.post('/reports/scheduled', payload),
  update: (id, payload) => api.put(`/reports/scheduled/${id}`, payload),
  remove: (id) => api.delete(`/reports/scheduled/${id}`),
  runNow: (id) => api.post(`/reports/scheduled/${id}/run-now`),
}

// ─── EGSM reports proxy (spec 018 W4.T9) ──
// /api/v1/reports/egsm/* forwards to MDMS. The catalogue endpoint is
// EMS-native (static 6-category list); per-report endpoints pass through.
export const egsmReportsAPI = {
  categories: () => api.get('/reports/categories'),
  run: (category, report, params) =>
    api.get(`/reports/egsm/${category}/${report}`, { params }),
  runPost: (category, report, payload) =>
    api.post(`/reports/egsm/${category}/${report}`, payload),
  pollDownload: (id) => api.get('/reports/download', { params: { id } }),
}

export default api
