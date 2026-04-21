/**
 * AppBuilder — spec 018 W4.T8 + P4 (functional widgets).
 *
 * Persisted AppBuilder surface backed by the backend /apps, /app-rules,
 * /algorithms endpoints. Dashboard Builder now supports live widget
 * bindings against the backend widget-source catalog, with per-widget
 * polling and a full-screen runtime view via My Apps → Open.
 *
 * Roles
 *   Publish actions require the `app_builder_publish` role. Until Agent N
 *   wires real RBAC, the frontend forwards the caller's role hint via the
 *   X-User-Role header. Non-admins see the publish button disabled.
 */
import { useEffect, useState, useRef, useMemo, useCallback } from 'react'
import {
  BarChart2, LineChart, Gauge, Map, Bell, Cpu, Table2, Type,
  LayoutDashboard, PlusCircle, Play, Save, Trash2, Eye,
  BookOpen, Maximize2, RefreshCw, ChevronDown, ChevronUp,
  X, Settings, AlertCircle,
} from 'lucide-react'
import {
  appBuilderAPI, metersAPI, alarmsAPI, derAPI,
  consumptionAPI, ntlAPI, outagesAPI, gisAPI,
} from '@/services/api'

// ─── Constants (widget palette + form enums) ──────────────────────────────────
const WIDGET_PALETTE = [
  { id: 'kpi',   name: 'KPI Card',    icon: Gauge,     color: '#02C9A8' },
  { id: 'line',  name: 'Line Chart',  icon: LineChart, color: '#56CCF2' },
  { id: 'bar',   name: 'Bar Chart',   icon: BarChart2, color: '#3C63FF' },
  { id: 'gauge', name: 'Gauge',       icon: Gauge,     color: '#F59E0B' },
  { id: 'map',   name: 'Map View',    icon: Map,       color: '#02C9A8' },
  { id: 'alarm', name: 'Alarm Table', icon: Bell,      color: '#E94B4B' },
  { id: 'der',   name: 'DER Status',  icon: Cpu,       color: '#11ABBE' },
  { id: 'meter', name: 'Meter Table', icon: Table2,    color: '#ABC7FF' },
  { id: 'text',  name: 'Text Block',  icon: Type,      color: 'rgba(255,255,255,0.5)' },
]

const PALETTE_BY_ID = WIDGET_PALETTE.reduce((m, w) => { m[w.id] = w; return m }, {})

const TRIGGERS = ['Alarm Raised', 'Meter Offline', 'DER Curtailed', 'Voltage Violation', 'Threshold Breach']
const METRICS  = ['Voltage (pu)', 'Current (A)', 'Power (kW)', 'Meter Status', 'Tamper Event', 'Energy (kWh)']
const OPERATORS = ['>', '<', '=', '≠']
const ACTIONS  = ['Send SMS', 'Send Email', 'Send App Notification', 'Execute Command', 'Log Event']
const PRIORITIES = ['Critical', 'High', 'Medium', 'Low']

const slugify = (s) =>
  (s || '').toLowerCase().trim().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 119) || `slug-${Date.now()}`

const userRole = () => {
  try {
    const raw = localStorage.getItem('smoc_user')
    if (!raw) return null
    const u = JSON.parse(raw)
    return (u.role || '').toLowerCase() || null
  } catch { return null }
}

const canPublish = () => {
  const r = userRole()
  return r && ['admin', 'supervisor', 'app_builder_publish'].includes(r)
}

const clampRefresh = (n) => {
  const v = Number.isFinite(+n) ? +n : 30
  return Math.max(5, Math.min(600, Math.round(v)))
}

// ─── Live data fetching + metric extraction ──────────────────────────────────
// Given a binding, call the correct API and return the raw response `.data`.
async function fetchSourceData(source) {
  if (!source) throw new Error('no source')
  switch (source.api) {
    case '/meters/summary':          return (await metersAPI.summary()).data
    case '/alarms?status=active':    return (await alarmsAPI.list({ status: 'active', limit: 50 })).data
    case '/der':                     return (await derAPI.list()).data
    case '/meters/feeders':          return (await metersAPI.feeders()).data
    case '/consumption/summary':     return (await consumptionAPI.summary()).data
    case '/der/transformers/sensors': {
      if (typeof derAPI.transformerSensors === 'function') {
        return (await derAPI.transformerSensors()).data
      }
      return (await derAPI.list()).data
    }
    case '/ntl/suspects':            return (await ntlAPI.suspects({ limit: 100 })).data
    case '/outages?status=active':   return (await outagesAPI.list({ status: 'active' })).data
    case '/gis/hierarchy/tree':      return (await gisAPI.hierarchyTree()).data
    default: throw new Error(`unknown api ${source.api}`)
  }
}

// Compute a scalar metric value from an API payload based on source id.
function extractMetric(apiResponse, metricKey, sourceId) {
  if (apiResponse == null) return null
  const arr = Array.isArray(apiResponse) ? apiResponse : null
  switch (sourceId) {
    case 'meters_summary':
      return apiResponse[metricKey]
    case 'alarms_active': {
      if (!arr) return null
      if (metricKey === 'count_critical') return arr.filter(a => (a.severity || '').toLowerCase() === 'critical').length
      if (metricKey === 'count_high')     return arr.filter(a => (a.severity || '').toLowerCase() === 'high').length
      if (metricKey === 'count_medium')   return arr.filter(a => (a.severity || '').toLowerCase() === 'medium').length
      return arr.length
    }
    case 'der_list': {
      if (!arr) return null
      if (metricKey === 'pv_output_kw')     return arr.filter(a => a.asset_type === 'pv').reduce((s, a) => s + (+a.current_output_kw || 0), 0)
      if (metricKey === 'bess_soc_pct') {
        const bess = arr.filter(a => a.asset_type === 'bess')
        if (!bess.length) return 0
        return bess.reduce((s, a) => s + (+a.state_of_charge || 0), 0) / bess.length
      }
      if (metricKey === 'ev_sessions')      return arr.filter(a => a.asset_type === 'ev_charger').reduce((s, a) => s + (+a.active_sessions || 0), 0)
      if (metricKey === 'total_capacity_kw') return arr.reduce((s, a) => s + (+a.capacity_kw || +a.current_output_kw || 0), 0)
      return arr.length
    }
    case 'feeder_loading': {
      if (!arr) return null
      if (metricKey === 'loading_pct') {
        if (!arr.length) return 0
        return arr.reduce((s, f) => s + (+f.loading_pct || 0), 0) / arr.length
      }
      return null
    }
    case 'consumption_summary': {
      const d = apiResponse.data || apiResponse
      return d ? d[metricKey] : null
    }
    case 'transformer_sensors': {
      if (!arr) return null
      const vals = arr.map(s => +s[metricKey]).filter(Number.isFinite)
      if (!vals.length) return null
      return vals.reduce((a, b) => a + b, 0) / vals.length
    }
    case 'ntl_suspects': {
      if (!arr) return null
      if (metricKey === 'count') return arr.length
      if (metricKey === 'high_score') return arr.filter(s => (+s.score || 0) >= 70).length
      return null
    }
    case 'outages_active': {
      if (!arr) return null
      if (metricKey === 'count') return arr.length
      if (metricKey === 'customers_out') return arr.reduce((s, o) => s + (+o.customers_affected || 0), 0)
      return null
    }
    case 'hierarchy_overview':
      return apiResponse?.stats?.[metricKey] ?? null
    default:
      return null
  }
}

function formatValue(v, fmt) {
  if (v == null || Number.isNaN(v)) return '—'
  const n = +v
  if (!Number.isFinite(n)) return String(v)
  switch (fmt) {
    case 'pct':  return `${n.toFixed(1)}%`
    case 'kw':   return `${n.toFixed(1)} kW`
    case 'kwh':  return `${n.toFixed(0)} kWh`
    case 'c':    return `${n.toFixed(1)} °C`
    case 'int':  return Math.round(n).toLocaleString()
    case 'num':  return n.toFixed(2)
    default:     return String(v)
  }
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────
function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{
      display: 'flex', gap: 2, marginBottom: 20,
      background: 'rgba(10,54,144,0.2)', borderRadius: 10, padding: 4,
      border: '1px solid rgba(171,199,255,0.1)',
    }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          flex: 1, padding: '8px 16px', borderRadius: 8, border: 'none',
          fontWeight: 700, fontSize: 13, cursor: 'pointer', transition: 'all 0.2s',
          background: active === t ? 'linear-gradient(45deg, #11ABBE, #3C63FF)' : 'transparent',
          color: active === t ? '#fff' : 'rgba(255,255,255,0.5)',
        }}>{t}</button>
      ))}
    </div>
  )
}

function SectionLabel({ text }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.35)',
      textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8,
    }}>{text}</div>
  )
}

function StatusBadge({ status }) {
  const map = {
    DRAFT: { color: '#ABC7FF', bg: 'rgba(171,199,255,0.15)' },
    PREVIEW: { color: '#F59E0B', bg: 'rgba(245,158,11,0.15)' },
    PUBLISHED: { color: '#02C9A8', bg: 'rgba(2,201,168,0.15)' },
    ARCHIVED: { color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.05)' },
  }
  const s = map[status] || map.DRAFT
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
      color: s.color, background: s.bg, border: `1px solid ${s.color}44`,
    }}>{status}</span>
  )
}

function Toast({ message, type = 'info', onClose }) {
  useEffect(() => {
    if (!message) return
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [message, onClose])
  if (!message) return null
  const color = type === 'error' ? '#E94B4B' : type === 'success' ? '#02C9A8' : '#56CCF2'
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, padding: '12px 18px',
      borderRadius: 8, background: '#0A1628', border: `1px solid ${color}88`,
      color: '#fff', fontSize: 13, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
      zIndex: 2000, maxWidth: 400,
    }}>
      <span style={{ color, fontWeight: 700, marginRight: 8 }}>{type.toUpperCase()}</span>
      {message}
    </div>
  )
}

// ─── Widget Config Drawer ────────────────────────────────────────────────────
function WidgetConfigDrawer({ widget, sources, onSave, onClose }) {
  const existing = widget?.binding || {}
  const [title, setTitle] = useState(existing.title || widget?.name || '')
  const [sourceId, setSourceId] = useState(existing.source_id || '')
  const [metricKey, setMetricKey] = useState(existing.metric_key || '')
  const [refreshSeconds, setRefreshSeconds] = useState(existing.refresh_seconds || 30)

  const eligibleSources = useMemo(() => {
    if (!widget) return []
    return (sources || []).filter(s =>
      !s.widget_types || s.widget_types.length === 0 || s.widget_types.includes(widget.id)
    )
  }, [sources, widget])

  const activeSource = useMemo(
    () => (sources || []).find(s => s.id === sourceId) || null,
    [sources, sourceId],
  )

  const activeMetric = useMemo(
    () => (activeSource?.metrics || []).find(m => m.key === metricKey) || null,
    [activeSource, metricKey],
  )

  const pickSource = (nextId) => {
    setSourceId(nextId)
    const src = (sources || []).find(s => s.id === nextId)
    // Reset metric to the new source's first metric if the current one is not valid.
    if (src && !src.metrics.find(m => m.key === metricKey)) {
      setMetricKey(src.metrics[0]?.key || '')
    } else if (!src) {
      setMetricKey('')
    }
  }

  if (!widget) return null

  const thresholdHint = activeMetric
    ? (activeMetric.severity_high_threshold != null
        ? `Severity-high above ${activeMetric.severity_high_threshold}`
        : activeMetric.severity_high
          ? 'Severity-high metric'
          : '—')
    : '—'

  const save = () => {
    if (!sourceId || !metricKey) return
    onSave({
      title: title.trim() || widget.name,
      source_id: sourceId,
      metric_key: metricKey,
      refresh_seconds: clampRefresh(refreshSeconds),
    })
  }

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0, width: 340,
      zIndex: 1500, padding: 16, overflowY: 'auto',
    }} className="animate-slide-up">
      <div className="glass-card" style={{
        padding: 20, height: 'calc(100% - 16px)',
        border: '1px solid rgba(2,201,168,0.25)', boxShadow: '-6px 0 24px rgba(0,0,0,0.4)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Settings size={14} style={{ color: '#02C9A8' }} />
            <span style={{ fontSize: 13, fontWeight: 800, color: '#fff' }}>Configure Widget</span>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
            cursor: 'pointer', padding: 4,
          }}><X size={16} /></button>
        </div>

        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 14, fontFamily: 'monospace' }}>
          type: {widget.id}
        </div>

        <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Title</label>
        <input value={title} onChange={e => setTitle(e.target.value)}
          placeholder="Widget title"
          style={{
            width: '100%', padding: '8px 10px', marginBottom: 12,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 6, color: '#fff', fontSize: 12, outline: 'none', boxSizing: 'border-box',
          }} />

        <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Data Source</label>
        <select value={sourceId} onChange={e => pickSource(e.target.value)}
          style={{
            width: '100%', padding: '8px 10px', marginBottom: 12,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 6, color: '#ABC7FF', fontSize: 12, outline: 'none', boxSizing: 'border-box',
          }}>
          <option value="" style={{ background: '#0A1535' }}>— Select a source —</option>
          {eligibleSources.map(s => (
            <option key={s.id} value={s.id} style={{ background: '#0A1535' }}>{s.name}</option>
          ))}
        </select>

        <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Metric</label>
        <select value={metricKey} onChange={e => setMetricKey(e.target.value)} disabled={!activeSource}
          style={{
            width: '100%', padding: '8px 10px', marginBottom: 12,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 6, color: '#ABC7FF', fontSize: 12, outline: 'none', boxSizing: 'border-box',
          }}>
          {(activeSource?.metrics || []).map(m => (
            <option key={m.key} value={m.key} style={{ background: '#0A1535' }}>{m.label}</option>
          ))}
        </select>

        <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Refresh (seconds, 5–600)</label>
        <input type="number" min={5} max={600} value={refreshSeconds}
          onChange={e => setRefreshSeconds(e.target.value)}
          style={{
            width: '100%', padding: '8px 10px', marginBottom: 12,
            background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
            borderRadius: 6, color: '#fff', fontSize: 12, outline: 'none', boxSizing: 'border-box',
          }} />

        <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Threshold hint</label>
        <div style={{
          padding: '8px 10px', marginBottom: 16,
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 6, color: 'rgba(255,255,255,0.55)', fontSize: 11,
        }}>{thresholdHint}</div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={save} disabled={!sourceId || !metricKey}
            style={{ flex: 1, gap: 6, padding: '8px 12px', fontSize: 12,
              opacity: (!sourceId || !metricKey) ? 0.5 : 1,
              cursor: (!sourceId || !metricKey) ? 'not-allowed' : 'pointer' }}>
            <Save size={12} /> Save binding
          </button>
          <button className="btn-secondary" onClick={onClose}
            style={{ flex: 1, padding: '8px 12px', fontSize: 12 }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// Shared frame for every rendered live widget.
function WidgetFrame({ title, err, children }) {
  return (
    <div style={{ position: 'relative', padding: 10, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.55)',
          textTransform: 'uppercase', letterSpacing: '0.06em',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '85%',
        }}>{title}</span>
        {err && (
          <span title="API error" style={{
            width: 6, height: 6, borderRadius: '50%', background: '#E94B4B',
            boxShadow: '0 0 4px #E94B4B',
          }} />
        )}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  )
}

// ─── Live Widget renderer ────────────────────────────────────────────────────
// Polls the bound source on `refresh_seconds` and renders per-type.
function LiveWidget({ widget, sources, compact = true }) {
  const { binding } = widget || {}
  const source = useMemo(
    () => (sources || []).find(s => s.id === binding?.source_id) || null,
    [sources, binding?.source_id],
  )
  const metricMeta = useMemo(
    () => (source?.metrics || []).find(m => m.key === binding?.metric_key) || null,
    [source, binding?.metric_key],
  )
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [history, setHistory] = useState([])
  const histRef = useRef([])

  useEffect(() => {
    if (!source || !binding) return undefined
    let alive = true
    const load = async () => {
      try {
        const payload = await fetchSourceData(source)
        if (!alive) return
        setData(payload)
        setErr(false)
        const v = extractMetric(payload, binding.metric_key, source.id)
        if (Number.isFinite(+v)) {
          const next = [...histRef.current, +v].slice(-20)
          histRef.current = next
          setHistory(next)
        }
      } catch {
        if (!alive) return
        setErr(true)
      }
    }
    load()
    const ms = clampRefresh(binding.refresh_seconds) * 1000
    const h = setInterval(load, ms)
    return () => { alive = false; clearInterval(h) }
  }, [source, binding])

  const palette = PALETTE_BY_ID[widget?.id] || { color: '#02C9A8', icon: Gauge }

  if (!binding) {
    const Icon = palette.icon
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '100%', gap: 6, padding: 8, textAlign: 'center',
      }}>
        <Icon size={22} style={{ color: palette.color }} />
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>
          {compact ? 'Click gear to bind data' : 'No data binding — re-open in Builder to configure'}
        </span>
      </div>
    )
  }

  // Runtime: binding exists but the source catalog hasn't come back yet —
  // keep the widget visibly placeholderd instead of looking broken.
  if (!source) {
    return (
      <WidgetFrame title={binding.title || widget.name} err={false}>
        <div style={{ height: '100%', display: 'flex', alignItems: 'center',
          justifyContent: 'center', color: 'rgba(255,255,255,0.35)', fontSize: 11 }}>
          Source “{binding.source_id}” unavailable
        </div>
      </WidgetFrame>
    )
  }

  const title = binding.title || widget.name
  const value = data != null ? extractMetric(data, binding.metric_key, source?.id) : null
  const threshold = metricMeta?.severity_high_threshold
  const isHigh = metricMeta?.severity_high
    || (threshold != null && Number.isFinite(+value) && +value >= threshold)
  const valueColor = isHigh ? '#E94B4B' : palette.color

  // ── KPI
  if (widget.id === 'kpi') {
    const big = compact ? 28 : 44
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
          <div style={{ fontSize: big, fontWeight: 900, color: valueColor, lineHeight: 1 }}>
            {formatValue(value, metricMeta?.format)}
          </div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 4 }}>
            {metricMeta?.label || binding.metric_key}
          </div>
        </div>
      </WidgetFrame>
    )
  }

  // ── Gauge (0–100 ring)
  if (widget.id === 'gauge') {
    const pct = Math.max(0, Math.min(100, +value || 0))
    const r = 32, cx = 40, cy = 40
    const circ = 2 * Math.PI * r
    const off = circ * (1 - pct / 100)
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, height: '100%' }}>
          <svg width={80} height={80}>
            <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={6} />
            <circle cx={cx} cy={cy} r={r} fill="none" stroke={valueColor} strokeWidth={6}
              strokeDasharray={circ} strokeDashoffset={off} strokeLinecap="round"
              transform={`rotate(-90 ${cx} ${cy})`} />
            <text x={cx} y={cy + 4} textAnchor="middle" fill="#fff" fontSize={14} fontWeight={800}>
              {Number.isFinite(+value) ? Math.round(+value) : '—'}
            </text>
          </svg>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>{metricMeta?.label}</div>
        </div>
      </WidgetFrame>
    )
  }

  // ── Line (mini polyline, last 20)
  if (widget.id === 'line') {
    const pts = history
    const w = 200, h = 60
    let poly = ''
    if (pts.length > 1) {
      const mn = Math.min(...pts), mx = Math.max(...pts)
      const rng = mx - mn || 1
      poly = pts.map((p, i) => {
        const x = (i / (pts.length - 1)) * w
        const y = h - ((p - mn) / rng) * h
        return `${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' ')
    }
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: valueColor, marginBottom: 4 }}>
            {formatValue(value, metricMeta?.format)}
          </div>
          <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ flex: 1, width: '100%' }}>
            {poly && <polyline points={poly} fill="none" stroke={valueColor} strokeWidth={1.5} />}
          </svg>
        </div>
      </WidgetFrame>
    )
  }

  // ── Bar (bar chart from list)
  if (widget.id === 'bar') {
    const arr = Array.isArray(data) ? data : (data?.data && Array.isArray(data.data) ? data.data : [])
    const items = arr.slice(0, 8).map((a, i) => {
      let label = a.name || a.feeder_name || a.asset_type || a.title || `#${i + 1}`
      let val = 0
      if (source?.id === 'feeder_loading') val = +a.loading_pct || 0
      else if (source?.id === 'der_list') val = +a.current_output_kw || +a.capacity_kw || 0
      else if (source?.id === 'alarms_active') val = 1
      else val = +a[binding.metric_key] || 0
      return { label, val }
    })
    const mx = Math.max(1, ...items.map(i => i.val))
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, height: '100%', overflow: 'hidden' }}>
          {items.length === 0 && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }}>No data</span>}
          {items.map((it, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
              <span style={{
                flex: '0 0 40%', color: 'rgba(255,255,255,0.6)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{it.label}</span>
              <div style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 3 }}>
                <div style={{ width: `${(it.val / mx) * 100}%`, height: '100%', background: palette.color, borderRadius: 3 }} />
              </div>
              <span style={{ flex: '0 0 32px', textAlign: 'right', color: '#ABC7FF', fontFamily: 'monospace' }}>
                {Number.isFinite(it.val) ? it.val.toFixed(0) : '—'}
              </span>
            </div>
          ))}
        </div>
      </WidgetFrame>
    )
  }

  // ── Alarm (top 5 alarms)
  if (widget.id === 'alarm') {
    const arr = Array.isArray(data) ? data : []
    const sevColor = (sv) => ({
      critical: '#E94B4B', high: '#F59E0B', medium: '#56CCF2', low: '#ABC7FF',
    }[(sv || '').toLowerCase()] || '#ABC7FF')
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, height: '100%', overflow: 'hidden' }}>
          {arr.length === 0 && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }}>No active alarms</span>}
          {arr.slice(0, 5).map((a, i) => (
            <div key={a.id || i} style={{
              display: 'flex', alignItems: 'center', gap: 6, fontSize: 10,
              padding: '3px 6px', background: 'rgba(255,255,255,0.03)', borderRadius: 4,
              borderLeft: `3px solid ${sevColor(a.severity)}`,
            }}>
              <span style={{ color: sevColor(a.severity), fontWeight: 700, width: 54, textTransform: 'uppercase' }}>
                {(a.severity || '—').slice(0, 6)}
              </span>
              <span style={{
                flex: 1, color: '#fff',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{a.title || a.description || a.alarm_type || 'alarm'}</span>
            </div>
          ))}
        </div>
      </WidgetFrame>
    )
  }

  // ── Meter (mini table)
  if (widget.id === 'meter') {
    const arr = Array.isArray(data) ? data.slice(0, 6) : []
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ height: '100%', overflow: 'hidden' }}>
          {arr.length === 0 && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }}>No rows</span>}
          <table style={{ width: '100%', fontSize: 10, borderCollapse: 'collapse' }}>
            <tbody>
              {arr.map((row, i) => (
                <tr key={row.id || row.serial || i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ color: '#ABC7FF', fontFamily: 'monospace', padding: '2px 4px' }}>
                    {row.serial || row.meter_serial || row.id || `#${i + 1}`}
                  </td>
                  <td style={{ color: '#fff', textAlign: 'right', padding: '2px 4px' }}>
                    {row.score != null ? `score ${row.score}` : row.status || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetFrame>
    )
  }

  // ── DER (card list)
  if (widget.id === 'der') {
    const arr = Array.isArray(data) ? data.slice(0, 5) : []
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, height: '100%', overflow: 'hidden' }}>
          {arr.length === 0 && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }}>No DER</span>}
          {arr.map((d, i) => (
            <div key={d.id || i} style={{
              display: 'flex', alignItems: 'center', gap: 8, fontSize: 10,
              padding: '4px 6px', background: 'rgba(255,255,255,0.03)', borderRadius: 4,
            }}>
              <Cpu size={10} style={{ color: palette.color }} />
              <span style={{ color: '#fff', fontWeight: 700, width: 60 }}>{d.asset_type || '—'}</span>
              <span style={{ flex: 1, color: 'rgba(255,255,255,0.6)' }}>
                {d.current_output_kw != null ? `${(+d.current_output_kw).toFixed(1)} kW` : ''}
                {d.state_of_charge != null ? ` · SoC ${(+d.state_of_charge).toFixed(0)}%` : ''}
                {d.active_sessions != null ? ` · ${d.active_sessions} sessions` : ''}
              </span>
            </div>
          ))}
        </div>
      </WidgetFrame>
    )
  }

  // ── Map (list w/ coords)
  if (widget.id === 'map') {
    const arr = Array.isArray(data) ? data.slice(0, 5)
      : (data?.features ? data.features.slice(0, 5) : [])
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, height: '100%', overflow: 'hidden' }}>
          {arr.length === 0 && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 10 }}>No locations</span>}
          {arr.map((p, i) => {
            const lat = p.latitude ?? p.lat ?? p.geometry?.coordinates?.[1]
            const lng = p.longitude ?? p.lng ?? p.geometry?.coordinates?.[0]
            return (
              <div key={p.id || i} style={{
                display: 'flex', alignItems: 'center', gap: 6, fontSize: 10,
                padding: '3px 6px', background: 'rgba(255,255,255,0.03)', borderRadius: 4,
              }}>
                <Map size={10} style={{ color: palette.color }} />
                <span style={{ color: '#fff', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.title || p.name || p.description || `location ${i + 1}`}
                </span>
                <span style={{ color: '#ABC7FF', fontFamily: 'monospace' }}>
                  {lat != null && lng != null ? `${(+lat).toFixed(2)},${(+lng).toFixed(2)}` : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </WidgetFrame>
    )
  }

  // ── Text
  if (widget.id === 'text') {
    return (
      <WidgetFrame title={title} err={err}>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
          {binding.title || 'Text block — edit in config drawer.'}
        </div>
      </WidgetFrame>
    )
  }

  // Fallback
  return (
    <WidgetFrame title={title} err={err}>
      <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 10 }}>Unsupported widget</div>
    </WidgetFrame>
  )
}

// ─── Dashboard Builder ───────────────────────────────────────────────────────
function DashboardBuilder({ toast }) {
  const GRID_ROWS = 3, GRID_COLS = 4
  const [canvas, setCanvas] = useState(Array(GRID_ROWS * GRID_COLS).fill(null))
  const [saveName, setSaveName] = useState('')
  const [sources, setSources] = useState([])
  const [configIdx, setConfigIdx] = useState(null)   // grid idx currently being configured
  const dragRef = useRef(null)

  // Load widget-sources catalog once.
  useEffect(() => {
    let alive = true
    appBuilderAPI.listWidgetSources()
      .then(res => { if (alive) setSources(res.data?.sources || []) })
      .catch(() => { if (alive) toast.show('Failed to load widget sources', 'error') })
    return () => { alive = false }
  }, [toast])

  const handleDrop = (idx, e) => {
    e.preventDefault()
    if (!dragRef.current || canvas[idx]) return
    const next = [...canvas]
    next[idx] = { ...dragRef.current, cellId: idx, binding: null }
    setCanvas(next)
    dragRef.current = null
    // Open config drawer immediately.
    setConfigIdx(idx)
  }

  const removeWidget = (idx) => {
    const next = [...canvas]
    next[idx] = null
    setCanvas(next)
    if (configIdx === idx) setConfigIdx(null)
  }

  const saveBinding = (idx, binding) => {
    const next = [...canvas]
    if (next[idx]) next[idx] = { ...next[idx], binding }
    setCanvas(next)
    setConfigIdx(null)
  }

  const saveAsApp = async () => {
    if (!saveName.trim()) {
      toast.show('Provide an app name first', 'error'); return
    }
    const unbound = canvas.filter(w => w && !w.binding).length
    if (unbound > 0) {
      toast.show(`${unbound} widget(s) still have no data binding — open the gear and pick a source before saving.`, 'error')
      return
    }
    const widgets = canvas
      .map((w, i) => w ? {
        slot: i,
        widget: w.id,
        name: w.name,
        binding: w.binding || null,
      } : null)
      .filter(Boolean)
    const slug = slugify(saveName)
    const payload = {
      name: saveName.trim(),
      description: `Dashboard with ${widgets.length} widget(s)`,
      definition: { widgets, grid: { rows: GRID_ROWS, cols: GRID_COLS } },
    }
    // Create-or-update: POST the new slug; on 409 (slug exists) fall through
    // to PUT /apps/{slug} which bumps the version with the new definition.
    // Previously the 2nd save silently failed with 'slug already exists',
    // leaving the stale v1 widgets in the runtime view.
    try {
      await appBuilderAPI.createApp({ slug, ...payload })
      toast.show('Saved as app', 'success')
      setSaveName('')
      return
    } catch (e) {
      if (e?.response?.status !== 409) {
        toast.show(e?.response?.data?.detail || 'Save failed', 'error')
        return
      }
    }
    try {
      await appBuilderAPI.updateApp(slug, payload)
      toast.show('Updated existing app (new version)', 'success')
      setSaveName('')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Save failed', 'error')
    }
  }

  const configWidget = configIdx != null ? canvas[configIdx] : null

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 240px)' }}>
      <div className="glass-card" style={{ padding: 16, width: 160, overflowY: 'auto', flexShrink: 0 }}>
        <SectionLabel text="Widget Palette" />
        {WIDGET_PALETTE.map(w => (
          <div
            key={w.id}
            draggable
            onDragStart={() => { dragRef.current = w }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
              borderRadius: 8, marginBottom: 6, cursor: 'grab',
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <w.icon size={14} style={{ color: w.color, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{w.name}</span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{
          flex: 1, display: 'grid', gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`,
          gridTemplateRows: `repeat(${GRID_ROWS}, 1fr)`, gap: 8,
        }}>
          {canvas.map((widget, idx) => (
            <div
              key={idx}
              onDragOver={e => { if (!canvas[idx]) { e.preventDefault() } }}
              onDrop={e => handleDrop(idx, e)}
              style={{
                borderRadius: 10, minHeight: 0, minWidth: 0,
                border: `1px solid ${widget ? (widget.binding ? 'rgba(2,201,168,0.35)' : 'rgba(245,158,11,0.4)') : 'rgba(255,255,255,0.08)'}`,
                background: widget ? `${widget.color}0d` : 'rgba(255,255,255,0.03)',
                position: 'relative', display: 'flex', flexDirection: 'column',
              }}
            >
              {widget ? (
                <>
                  <LiveWidget widget={widget} sources={sources} compact />
                  <div style={{ position: 'absolute', top: 6, right: 6, display: 'flex', gap: 4 }}>
                    <button
                      onClick={e => { e.stopPropagation(); setConfigIdx(idx) }}
                      title="Configure"
                      style={{
                        width: 20, height: 20, borderRadius: '50%',
                        background: 'rgba(2,201,168,0.2)', border: '1px solid rgba(2,201,168,0.4)',
                        color: '#02C9A8', cursor: 'pointer', padding: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    ><Settings size={10} /></button>
                    <button
                      onClick={e => { e.stopPropagation(); removeWidget(idx) }}
                      title="Remove"
                      style={{
                        width: 20, height: 20, borderRadius: '50%',
                        background: 'rgba(233,75,75,0.3)', border: '1px solid rgba(233,75,75,0.5)',
                        color: '#E94B4B', cursor: 'pointer', padding: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    ><X size={10} /></button>
                  </div>
                  {!widget.binding && (
                    <div style={{
                      position: 'absolute', bottom: 6, left: 8,
                      display: 'flex', alignItems: 'center', gap: 4,
                      fontSize: 9, color: '#F59E0B', fontWeight: 700,
                    }}>
                      <AlertCircle size={9} /> Click gear to bind data
                    </div>
                  )}
                </>
              ) : (
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)' }}>Drop here</span>
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={saveName}
            onChange={e => setSaveName(e.target.value)}
            placeholder="App name to save this layout as…"
            style={{ flex: 1, padding: '8px 12px', background: 'rgba(10,54,144,0.25)',
              border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', fontSize: 13, outline: 'none' }}
          />
          <button className="btn-primary" onClick={saveAsApp} style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Save size={13} /> Save as App
          </button>
        </div>
      </div>

      {configWidget && (
        <WidgetConfigDrawer
          widget={configWidget}
          sources={sources}
          onSave={(binding) => saveBinding(configIdx, binding)}
          onClose={() => setConfigIdx(null)}
        />
      )}
    </div>
  )
}

// ─── Widget Runtime (My Apps → Open full-screen view) ────────────────────────
function WidgetRuntime({ app, onExit }) {
  const [sources, setSources] = useState([])

  useEffect(() => {
    let alive = true
    appBuilderAPI.listWidgetSources()
      .then(res => { if (alive) setSources(res.data?.sources || []) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const defn = app?.definition || {}
  const grid = defn.grid || { rows: 3, cols: 4 }
  const widgets = defn.widgets || []

  // Build cell map keyed by slot.
  const cells = Array(grid.rows * grid.cols).fill(null)
  for (const w of widgets) {
    if (w.slot != null && w.slot < cells.length) {
      const pal = PALETTE_BY_ID[w.widget] || PALETTE_BY_ID.kpi
      cells[w.slot] = { id: w.widget, name: w.name || pal?.name, color: pal?.color, cellId: w.slot, binding: w.binding || null }
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: '#0A0F1E',
      display: 'flex', flexDirection: 'column', zIndex: 1000, padding: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <LayoutDashboard size={22} style={{ color: '#02C9A8' }} />
            <h1 style={{ color: '#fff', fontSize: 22, fontWeight: 900, margin: 0 }}>{app.name}</h1>
            <StatusBadge status={app.status} />
          </div>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, margin: '4px 0 0' }}>
            v{app.version} · {widgets.length} widget(s) · live preview
          </p>
        </div>
        <button className="btn-secondary" onClick={onExit} style={{ gap: 6, padding: '8px 14px', fontSize: 12 }}>
          <X size={13} /> Exit Preview
        </button>
      </div>

      <div style={{
        flex: 1, display: 'grid',
        gridTemplateColumns: `repeat(${grid.cols}, 1fr)`,
        gridTemplateRows: `repeat(${grid.rows}, 1fr)`,
        gap: 10, minHeight: 0,
      }}>
        {cells.map((w, idx) => (
          <div key={idx} className="glass-card" style={{
            padding: 0, minHeight: 0, minWidth: 0, overflow: 'hidden',
            border: '1px solid rgba(171,199,255,0.15)',
          }}>
            {w ? (
              <LiveWidget widget={w} sources={sources} compact={false} />
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'rgba(255,255,255,0.15)', fontSize: 11 }}>empty</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── My Apps (list + create + version history) ────────────────────────────────
function MyApps({ toast }) {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newApp, setNewApp] = useState({ name: '', description: '' })
  const [openApp, setOpenApp] = useState(null)
  const [versions, setVersions] = useState([])
  const [expandedSlug, setExpandedSlug] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listApps()
      setApps(res.data || [])
    } catch (e) {
      toast.show(`Failed to load apps: ${e?.response?.data?.detail || e.message}`, 'error')
    } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { refresh() }, [refresh])

  const createApp = async () => {
    if (!newApp.name.trim()) return
    try {
      await appBuilderAPI.createApp({
        slug: slugify(newApp.name),
        name: newApp.name.trim(),
        description: newApp.description || null,
        definition: { widgets: [] },
      })
      setNewApp({ name: '', description: '' })
      setCreateOpen(false)
      await refresh()
      toast.show('App created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const publish = async (slug) => {
    if (!canPublish()) {
      toast.show('Publishing requires app_builder_publish role', 'error')
      return
    }
    try {
      await appBuilderAPI.publishApp(slug, { notes: '' }, userRole())
      await refresh()
      toast.show(`Published ${slug}`, 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const preview = async (slug) => {
    try {
      await appBuilderAPI.previewApp(slug)
      await refresh()
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Preview failed', 'error')
    }
  }

  const archive = async (slug) => {
    try {
      await appBuilderAPI.archiveApp(slug, userRole())
      await refresh()
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Archive failed', 'error')
    }
  }

  const showVersions = async (slug) => {
    if (expandedSlug === slug) { setExpandedSlug(null); return }
    try {
      const res = await appBuilderAPI.getAppVersions(slug)
      setVersions(res.data)
      setExpandedSlug(slug)
    } catch (e) {
      toast.show('Failed to load versions', 'error')
    }
  }

  const openAppLive = async (app) => {
    // Fetch the full app (to ensure fresh definition.widgets is included).
    try {
      const res = await appBuilderAPI.getApp(app.slug)
      setOpenApp(res.data || app)
    } catch {
      setOpenApp(app)
    }
  }

  const appColors = ['#02C9A8', '#56CCF2', '#3C63FF', '#F59E0B', '#E94B4B']

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <button className="btn-secondary" onClick={refresh} style={{ gap: 6, padding: '8px 14px', fontSize: 12 }}>
          <RefreshCw size={12} /> Refresh
        </button>
        <button className="btn-primary" onClick={() => setCreateOpen(true)} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
          <PlusCircle size={14} /> Create New App
        </button>
      </div>

      {loading ? (
        <p style={{ color: 'rgba(255,255,255,0.4)' }}>Loading…</p>
      ) : apps.length === 0 ? (
        <div className="glass-card" style={{ padding: 36, textAlign: 'center' }}>
          <LayoutDashboard size={32} style={{ color: 'rgba(255,255,255,0.2)', marginBottom: 10 }} />
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, margin: 0 }}>
            No apps yet. Create one to start building dashboards.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {apps.map((app, i) => (
            <div key={app.slug} className="glass-card" style={{ padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: `${appColors[i % appColors.length]}20`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: `1px solid ${appColors[i % appColors.length]}44`,
                }}>
                  <LayoutDashboard size={18} style={{ color: appColors[i % appColors.length] }} />
                </div>
                <StatusBadge status={app.status} />
              </div>
              <div style={{ fontWeight: 800, fontSize: 15, color: '#fff', marginBottom: 2 }}>{app.name}</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 8, fontFamily: 'monospace' }}>
                {app.slug} · v{app.version}
              </div>
              {app.description && (
                <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', margin: '0 0 12px' }}>{app.description}</p>
              )}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button className="btn-primary" onClick={() => openAppLive(app)} style={{ padding: '6px 12px', fontSize: 11, gap: 4 }}>
                  <Maximize2 size={11} /> Open
                </button>
                {app.status === 'DRAFT' && (
                  <button className="btn-secondary" onClick={() => preview(app.slug)} style={{ padding: '6px 12px', fontSize: 11, gap: 4 }}>
                    <Eye size={11} /> Preview
                  </button>
                )}
                {['DRAFT', 'PREVIEW'].includes(app.status) && (
                  <button
                    disabled={!canPublish()}
                    onClick={() => publish(app.slug)}
                    style={{
                      padding: '6px 12px', fontSize: 11, borderRadius: 6,
                      background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
                      border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
                      color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
                      cursor: canPublish() ? 'pointer' : 'not-allowed', fontWeight: 700,
                    }}
                    title={canPublish() ? 'Publish' : 'Requires app_builder_publish role'}
                  >
                    Publish
                  </button>
                )}
                <button onClick={() => showVersions(app.slug)} style={{
                  padding: '6px 10px', fontSize: 11, borderRadius: 6,
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
                  color: 'rgba(255,255,255,0.6)', cursor: 'pointer', fontWeight: 700,
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                }}>
                  {expandedSlug === app.slug ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  History
                </button>
                <button onClick={() => archive(app.slug)} style={{
                  padding: '6px 10px', fontSize: 11, borderRadius: 6,
                  background: 'rgba(233,75,75,0.1)', border: '1px solid rgba(233,75,75,0.25)',
                  color: '#E94B4B', cursor: 'pointer',
                }} title="Archive">
                  <Trash2 size={11} />
                </button>
              </div>
              {expandedSlug === app.slug && versions.length > 0 && (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <SectionLabel text="Version History" />
                  {versions.map(v => (
                    <div key={v.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '4px 6px', fontSize: 11,
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                    }}>
                      <span style={{ color: 'rgba(255,255,255,0.7)', fontFamily: 'monospace' }}>v{v.version}</span>
                      <StatusBadge status={v.status} />
                      <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
                        {new Date(v.updated_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      {createOpen && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div className="glass-card animate-slide-up" style={{ padding: 28, width: 420, border: '1px solid rgba(2,201,168,0.2)' }}>
            <h3 style={{ margin: '0 0 16px', color: '#fff', fontSize: 17, fontWeight: 900 }}>Create New App</h3>
            <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 5, fontWeight: 700 }}>App Name</label>
            <input
              value={newApp.name}
              onChange={e => setNewApp(p => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Substation Monitor"
              style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 8, color: '#fff', padding: '10px 12px', fontSize: 13, outline: 'none', boxSizing: 'border-box', marginBottom: 12 }}
            />
            <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 5, fontWeight: 700 }}>Description</label>
            <input
              value={newApp.description}
              onChange={e => setNewApp(p => ({ ...p, description: e.target.value }))}
              placeholder="What does this app do?"
              style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 8, color: '#fff', padding: '10px 12px', fontSize: 13, outline: 'none', boxSizing: 'border-box', marginBottom: 16 }}
            />
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn-primary" onClick={createApp} style={{ flex: 1 }}>Create</button>
              <button className="btn-secondary" onClick={() => setCreateOpen(false)} style={{ flex: 1 }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {openApp && <WidgetRuntime app={openApp} onExit={() => setOpenApp(null)} />}
    </div>
  )
}

// ─── Rule Engine (persisted via /app-rules) ───────────────────────────────────
function RuleEngine({ toast }) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const emptyForm = { name: '', trigger: TRIGGERS[0], metric: METRICS[0], op: '>', value: '', action: ACTIONS[0], priority: 'Medium' }
  const [form, setForm] = useState(emptyForm)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listRules()
      setRules(res.data || [])
    } catch (e) {
      toast.show('Failed to load rules', 'error')
    } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { refresh() }, [refresh])

  const saveRule = async () => {
    if (!form.name.trim()) return
    try {
      await appBuilderAPI.createRule({
        slug: slugify(form.name),
        name: form.name.trim(),
        definition: {
          trigger: form.trigger, metric: form.metric, op: form.op,
          value: form.value, action: form.action, priority: form.priority,
        },
      })
      setForm(emptyForm); setCreating(false)
      await refresh()
      toast.show('Rule created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const deleteRule = async (slug) => {
    try {
      await appBuilderAPI.deleteRule(slug, userRole())
      await refresh()
    } catch (e) {
      toast.show('Delete failed', 'error')
    }
  }

  const publish = async (slug) => {
    if (!canPublish()) { toast.show('Publishing requires app_builder_publish role', 'error'); return }
    try {
      await appBuilderAPI.publishRule(slug, {}, userRole())
      await refresh()
      toast.show('Published', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const pColor = { Critical: '#E94B4B', High: '#F97316', Medium: '#F59E0B', Low: '#3B82F6' }

  return (
    <div>
      {creating ? (
        <div className="glass-card animate-slide-up" style={{ padding: 20, marginBottom: 20, border: '1px solid rgba(2,201,168,0.2)' }}>
          <h3 style={{ margin: '0 0 16px', color: '#fff', fontSize: 15, fontWeight: 700 }}>Create Rule</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Rule Name</label>
              <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="e.g. High Load Alert"
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', padding: '8px 10px', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Trigger</label>
              <select value={form.trigger} onChange={e => setForm(p => ({ ...p, trigger: e.target.value }))}
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, outline: 'none', boxSizing: 'border-box' }}>
                {TRIGGERS.map(t => <option key={t} value={t} style={{ background: '#0A1535' }}>{t}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Condition</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={form.metric} onChange={e => setForm(p => ({ ...p, metric: e.target.value }))}
                  style={{ flex: 2, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13 }}>
                  {METRICS.map(m => <option key={m} value={m} style={{ background: '#0A1535' }}>{m}</option>)}
                </select>
                <select value={form.op} onChange={e => setForm(p => ({ ...p, op: e.target.value }))}
                  style={{ flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, textAlign: 'center' }}>
                  {OPERATORS.map(o => <option key={o} value={o} style={{ background: '#0A1535' }}>{o}</option>)}
                </select>
                <input value={form.value} onChange={e => setForm(p => ({ ...p, value: e.target.value }))}
                  placeholder="Value"
                  style={{ flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#fff', padding: '8px 10px', fontSize: 13 }} />
              </div>
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Action</label>
              <select value={form.action} onChange={e => setForm(p => ({ ...p, action: e.target.value }))}
                style={{ width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)', borderRadius: 6, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, boxSizing: 'border-box' }}>
                {ACTIONS.map(a => <option key={a} value={a} style={{ background: '#0A1535' }}>{a}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', display: 'block', marginBottom: 4, fontWeight: 700 }}>Priority</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {PRIORITIES.map(p => (
                  <button key={p} onClick={() => setForm(f => ({ ...f, priority: p }))} style={{
                    flex: 1, padding: '7px 4px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                    cursor: 'pointer', background: form.priority === p ? `${pColor[p]}22` : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${form.priority === p ? pColor[p] : 'rgba(255,255,255,0.08)'}`,
                    color: form.priority === p ? pColor[p] : 'rgba(255,255,255,0.4)',
                  }}>{p}</button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button className="btn-primary" onClick={saveRule} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
              <Save size={13} /> Save Rule
            </button>
            <button className="btn-secondary" onClick={() => { setCreating(false); setForm(emptyForm) }}
              style={{ padding: '9px 18px', fontSize: 13 }}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <button className="btn-secondary" onClick={refresh} style={{ gap: 6, padding: '8px 14px', fontSize: 12 }}>
            <RefreshCw size={12} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => setCreating(true)} style={{ gap: 6, padding: '9px 18px', fontSize: 13 }}>
            <PlusCircle size={14} /> Create Rule
          </button>
        </div>
      )}

      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th><th>Slug/Ver</th><th>Trigger</th><th>Condition</th>
              <th>Action</th><th>Status</th><th style={{ width: 160 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>Loading…</td></tr>
            ) : rules.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>No rules yet.</td></tr>
            ) : rules.map(rule => {
              const d = rule.definition || {}
              return (
                <tr key={rule.slug}>
                  <td style={{ fontWeight: 600, color: '#fff' }}>{rule.name}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#ABC7FF' }}>{rule.slug} v{rule.version}</td>
                  <td style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{d.trigger}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#ABC7FF' }}>
                    {d.metric} {d.op} {d.value}
                  </td>
                  <td style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{d.action}</td>
                  <td><StatusBadge status={rule.status} /></td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {['DRAFT', 'PREVIEW'].includes(rule.status) && (
                        <button onClick={() => publish(rule.slug)} disabled={!canPublish()}
                          style={{
                            padding: '4px 10px', fontSize: 11, borderRadius: 5, fontWeight: 700,
                            background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
                            border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
                            color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
                            cursor: canPublish() ? 'pointer' : 'not-allowed',
                          }} title={canPublish() ? 'Publish' : 'Role required'}>Publish</button>
                      )}
                      <button onClick={() => deleteRule(rule.slug)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#E94B4B', padding: 4 }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Algorithm Editor (persisted via /algorithms + /run sandbox) ──────────────
function AlgorithmEditor({ toast }) {
  const [algos, setAlgos] = useState([])
  const [active, setActive] = useState(null)   // { slug, name, source, version, status }
  const [loading, setLoading] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [consoleOut, setConsoleOut] = useState('')
  const [running, setRunning] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await appBuilderAPI.listAlgorithms()
      setAlgos(res.data || [])
      if (!active && res.data?.length) {
        const first = res.data[0]
        setActive(first); setCode(first.source); setName(first.name)
      }
    } catch (e) {
      toast.show('Failed to load algorithms', 'error')
    } finally { setLoading(false) }
  }, [toast, active])

  useEffect(() => { refresh() }, []) // eslint-disable-line

  const loadAlgo = (a) => {
    setActive(a)
    setCode(a.source)
    setName(a.name)
    setConsoleOut('')
  }

  const createNew = async () => {
    const nn = prompt('Algorithm name')
    if (!nn) return
    const slug = slugify(nn)
    const defaultSource = `# ${nn}\ndef main(inputs):\n    # inputs is a dict. Return any JSON-serialisable value.\n    return {"ok": True, "received": inputs}\n`
    try {
      const res = await appBuilderAPI.createAlgorithm({
        slug, name: nn, source: defaultSource, definition: {},
      })
      await refresh()
      loadAlgo(res.data)
      toast.show('Algorithm created', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Create failed', 'error')
    }
  }

  const saveAlgo = async () => {
    if (!active) return
    try {
      const res = await appBuilderAPI.updateAlgorithm(active.slug, {
        name, source: code,
      })
      setActive(res.data)
      await refresh()
      toast.show(`Saved v${res.data.version}`, 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail || 'Save failed', 'error')
    }
  }

  const runAlgo = async () => {
    if (!active) return
    setRunning(true); setConsoleOut('Running…\n')
    try {
      const res = await appBuilderAPI.runAlgorithm(active.slug, {
        inputs: {}, timeout_seconds: 5,
      })
      const d = res.data
      let out = `[${new Date().toISOString()}] ${d.status.toUpperCase()} in ${d.duration_ms}ms\n`
      if (d.stdout) out += `stdout:\n${d.stdout}\n`
      if (d.error) out += `error: ${d.error}\n`
      if (d.result !== null && d.result !== undefined) {
        out += `result: ${JSON.stringify(d.result, null, 2)}\n`
      }
      setConsoleOut(out)
    } catch (e) {
      setConsoleOut(`RUN FAILED: ${e?.response?.data?.detail || e.message}`)
    } finally { setRunning(false) }
  }

  const publishAlgo = async () => {
    if (!active) return
    if (!canPublish()) { toast.show('Publishing requires app_builder_publish role', 'error'); return }
    try {
      await appBuilderAPI.publishAlgorithm(active.slug, {}, userRole())
      await refresh()
      toast.show('Published', 'success')
    } catch (e) {
      toast.show(e?.response?.data?.detail?.error?.message || 'Publish failed', 'error')
    }
  }

  const lineNumbers = code.split('\n').map((_, i) => i + 1).join('\n')

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 240px)' }}>
      <div className="glass-card" style={{ padding: 14, width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
        <SectionLabel text="Algorithm Library" />
        <button className="btn-primary" onClick={createNew}
          style={{ padding: '6px 10px', fontSize: 11, marginBottom: 8, gap: 4 }}>
          <PlusCircle size={11} /> New
        </button>
        <button className="btn-secondary" onClick={refresh}
          style={{ padding: '6px 10px', fontSize: 11, marginBottom: 10, gap: 4 }}>
          <RefreshCw size={11} /> Refresh
        </button>
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>Loading…</p>}
          {algos.map(a => (
            <button key={a.slug} onClick={() => loadAlgo(a)} style={{
              width: '100%', padding: '8px 10px', borderRadius: 8, marginBottom: 4,
              background: active?.slug === a.slug ? 'rgba(2,201,168,0.12)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${active?.slug === a.slug ? '#02C9A8' : 'rgba(255,255,255,0.08)'}`,
              color: active?.slug === a.slug ? '#02C9A8' : 'rgba(255,255,255,0.6)',
              fontSize: 11, fontWeight: 600, cursor: 'pointer', textAlign: 'left',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <BookOpen size={11} style={{ flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{a.name}</span>
              <StatusBadge status={a.status} />
            </button>
          ))}
          {!loading && algos.length === 0 && (
            <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>No algorithms yet.</p>
          )}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn-primary" onClick={runAlgo} disabled={running || !active}
            style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Play size={13} /> {running ? 'Running…' : 'Preview / Run'}
          </button>
          <button className="btn-secondary" onClick={saveAlgo} disabled={!active}
            style={{ gap: 6, padding: '8px 16px', fontSize: 12 }}>
            <Save size={13} /> Save (new version)
          </button>
          <button onClick={publishAlgo} disabled={!active || !canPublish()}
            style={{
              padding: '8px 16px', fontSize: 12, borderRadius: 6, fontWeight: 700,
              background: canPublish() ? '#02C9A822' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.1)'}`,
              color: canPublish() ? '#02C9A8' : 'rgba(255,255,255,0.3)',
              cursor: canPublish() && active ? 'pointer' : 'not-allowed',
            }}
            title={canPublish() ? 'Publish' : 'Requires app_builder_publish role'}>
            Publish
          </button>
          {active && (
            <input
              value={name} onChange={e => setName(e.target.value)}
              placeholder="Name"
              style={{ marginLeft: 'auto', padding: '6px 10px', fontSize: 12,
                background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.15)',
                borderRadius: 6, color: '#fff', outline: 'none', width: 260 }}
            />
          )}
          {active && <StatusBadge status={active.status} />}
          {active && <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 11, fontFamily: 'monospace' }}>v{active.version}</span>}
        </div>

        <div style={{
          flex: 1, display: 'flex', borderRadius: 10, overflow: 'hidden',
          border: '1px solid rgba(2,201,168,0.2)', background: '#060B18',
        }}>
          <div style={{
            padding: '16px 12px', background: '#060B18', borderRight: '1px solid rgba(255,255,255,0.06)',
            fontFamily: "'Courier New', Courier, monospace", fontSize: 13, lineHeight: '1.7',
            color: 'rgba(255,255,255,0.2)', whiteSpace: 'pre', userSelect: 'none',
            minWidth: 40, textAlign: 'right', overflowY: 'hidden',
          }}>
            {lineNumbers}
          </div>
          <textarea
            value={code}
            onChange={e => setCode(e.target.value)}
            disabled={!active}
            spellCheck={false}
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none', resize: 'none',
              fontFamily: "'Courier New', Courier, monospace", fontSize: 13, lineHeight: '1.7',
              color: '#02C9A8', padding: '16px', caretColor: '#02C9A8',
            }}
          />
        </div>

        <div style={{
          height: 160, borderRadius: 8, background: '#030712', border: '1px solid rgba(255,255,255,0.06)',
          padding: '10px 14px', overflow: 'auto',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.25)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Sandbox Output
          </div>
          <pre style={{
            margin: 0, fontFamily: "'Courier New', Courier, monospace", fontSize: 12,
            color: consoleOut ? '#02C9A8' : 'rgba(255,255,255,0.2)', lineHeight: '1.6',
            whiteSpace: 'pre-wrap',
          }}>
            {consoleOut || '— No output yet. Press Preview / Run to execute in the sandbox. —'}
          </pre>
        </div>
      </div>
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────
const TABS = ['Dashboard Builder', 'Rule Engine', 'Algorithm Editor', 'My Apps']

export default function AppBuilder() {
  const [activeTab, setActiveTab] = useState('Dashboard Builder')
  const [toastMsg, setToastMsg] = useState({ message: '', type: 'info' })
  const toast = useMemo(() => ({
    show: (message, type = 'info') => setToastMsg({ message, type }),
  }), [])

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>No-Code App Builder</h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
          REQ-27 L3 — Custom displays · Rule engine · Algorithm editor · App creation
          {!canPublish() && (
            <span style={{ color: '#F59E0B', marginLeft: 10 }}>
              · Publish disabled (requires app_builder_publish role)
            </span>
          )}
        </p>
      </div>

      <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'Dashboard Builder' && <DashboardBuilder toast={toast} />}
      {activeTab === 'Rule Engine'       && <RuleEngine toast={toast} />}
      {activeTab === 'Algorithm Editor'  && <AlgorithmEditor toast={toast} />}
      {activeTab === 'My Apps'           && <MyApps toast={toast} />}

      <Toast message={toastMsg.message} type={toastMsg.type} onClose={() => setToastMsg({ message: '', type: 'info' })} />
    </div>
  )
}
