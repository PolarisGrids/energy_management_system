import { useOutletContext, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  Wifi, WifiOff, AlertTriangle, CheckCircle, Zap,
  Activity, MapPin, Battery, Car, RefreshCw, LayoutGrid,
  FileText, CalendarDays, Clock, PlugZap, Power,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, dashboardsAPI, slaAPI, mdmsDashboardAPI } from '@/services/api'
import { UpstreamErrorPanel } from '@/components/ui'
import LayoutManager from '@/components/dashboard/LayoutManager'

// ─── Loading + error primitives (local; keeps this page self-contained) ─────

const Skeleton = ({ className = '', style = {} }) => (
  <div
    className={`skeleton rounded ${className}`}
    style={{
      background:
        'linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.04) 100%)',
      backgroundSize: '200% 100%',
      animation: 'skeleton-pulse 1.6s ease-in-out infinite',
      ...style,
    }}
  />
)

const SkeletonMetricCard = () => (
  <div className="metric-card">
    <Skeleton style={{ width: 40, height: 40, borderRadius: 12 }} />
    <div className="mt-3 space-y-2">
      <Skeleton style={{ height: 24, width: '60%' }} />
      <Skeleton style={{ height: 12, width: '80%' }} />
    </div>
  </div>
)

// FastAPI 422 responses return `detail` as an array of {msg, loc, ...} objects;
// other errors return a plain string. Coerce anything stringy into a readable
// message so the banner never shows "[object Object]".
const formatApiError = (err, fallback = 'Unavailable') => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'string' ? d : d?.msg || JSON.stringify(d)))
      .join('; ')
  }
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return err?.message ?? fallback
}

const ErrorBanner = ({ message, onRetry }) => (
  <div
    role="alert"
    className="glass-card p-4 flex items-center gap-3"
    style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}
  >
    <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
    <div className="flex-1">
      <div className="text-white font-bold" style={{ fontSize: 13 }}>
        Dashboard data unavailable
      </div>
      <div className="text-white/70 mt-0.5" style={{ fontSize: 12 }}>
        {message || 'Upstream services are not reachable. Retry or wait for recovery.'}
      </div>
    </div>
    {onRetry && (
      <button
        onClick={onRetry}
        className="btn-secondary flex items-center gap-2"
        style={{ padding: '6px 12px', fontSize: 12 }}
      >
        <RefreshCw size={12} /> Retry
      </button>
    )}
  </div>
)

// ─── Card ──────────────────────────────────────────────────────────────────

const MetricCard = ({ icon: Icon, label, value, sub, color = '#02C9A8', trend }) => (
  <div className="metric-card">
    <div className="flex items-start justify-between">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}
      >
        <Icon size={18} style={{ color }} />
      </div>
      {trend !== undefined && (
        <span style={{ fontSize: 11, color: trend >= 0 ? '#02C9A8' : '#E94B4B' }}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
        </span>
      )}
    </div>
    <div className="mt-3">
      <div className="text-white font-black" style={{ fontSize: 28 }}>{value}</div>
      <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>{label}</div>
      {sub && <div style={{ color, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  </div>
)

const GAUGE_OPTION = (value, label) => ({
  backgroundColor: 'transparent',
  series: [{
    type: 'gauge',
    startAngle: 200, endAngle: -20,
    min: 0, max: 100,
    radius: '88%',
    itemStyle: { color: value > 90 ? '#02C9A8' : value > 70 ? '#F59E0B' : '#E94B4B' },
    progress: { show: true, width: 14 },
    pointer: { show: false },
    axisLine: { lineStyle: { width: 14, color: [[1, 'rgba(171,199,255,0.1)']] } },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
    detail: {
      valueAnimation: true,
      formatter: value == null ? '—' : `{value}%`,
      color: '#fff',
      fontSize: 22,
      fontWeight: 900,
      fontFamily: 'Satoshi',
      offsetCenter: [0, 0],
    },
    title: { show: true, color: '#ABC7FF', fontSize: 11, offsetCenter: [0, '65%'], formatter: label },
    data: [{ value: value ?? 0 }],
  }],
})

// ─── SLA KPIs (month-to-date) ──────────────────────────────────────────────

// Profiles surfaced on the dashboard, in display order. Everything else from
// validation_rules.profile_types stays hidden — add here if we want more.
const SLA_PROFILE_ORDER = ['MONTHLY_BILLING', 'DAILYLOAD', 'BLOCKLOAD']

const SLA_ICON = {
  MONTHLY_BILLING: FileText,
  DAILYLOAD: CalendarDays,
  BLOCKLOAD: Clock,
}

const slaColor = (pct) => {
  if (pct == null) return '#6B7280'
  if (pct >= 98) return '#02C9A8'
  if (pct >= 90) return '#F59E0B'
  return '#E94B4B'
}

const SlaCard = ({ profile, devices }) => {
  const Icon = SLA_ICON[profile.profile_type] ?? Activity
  const color = slaColor(profile.sla_pct)
  const pctLabel = profile.sla_pct == null ? '—' : `${profile.sla_pct.toFixed(2)}%`
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: `${color}20` }}
        >
          <Icon size={18} style={{ color }} />
        </div>
        <span style={{ fontSize: 11, color }}>{profile.label}</span>
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 28 }}>{pctLabel}</div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>
          {profile.received.toLocaleString()} / {profile.expected.toLocaleString()} records
        </div>
        <div style={{ color, fontSize: 11, marginTop: 4 }}>
          {devices != null ? `${devices.toLocaleString()} meters` : 'MTD'} · {profile.invalid.toLocaleString()} invalid · {profile.estimated.toLocaleString()} est.
        </div>
      </div>
    </div>
  )
}

const SlaSection = ({ sla, loading, error, onRetry }) => {
  const profiles = (sla?.profiles ?? [])
  // Order by SLA_PROFILE_ORDER and drop anything not in the list.
  const ordered = SLA_PROFILE_ORDER
    .map((t) => profiles.find((p) => p.profile_type === t))
    .filter(Boolean)

  const meters = sla?.devices?.meters
  const dtrs = sla?.devices?.dtrs
  const feeders = sla?.devices?.feeders

  return (
    <div data-testid="dashboard-sla-row">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-white font-bold" style={{ fontSize: 16 }}>
          Metrology SLA — Month to Date
        </h2>
        {sla && (
          <div className="text-white/50 text-xs flex items-center gap-3">
            <span><span className="text-white font-bold">{meters?.toLocaleString() ?? '—'}</span> meters</span>
            <span><span className="text-white font-bold">{dtrs?.toLocaleString() ?? '—'}</span> DTRs</span>
            <span><span className="text-white font-bold">{feeders?.toLocaleString() ?? '—'}</span> feeders</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonMetricCard key={i} />)}
        </div>
      ) : error ? (
        <ErrorBanner message={`SLA: ${error}`} onRetry={onRetry} />
      ) : ordered.length === 0 ? (
        <div className="glass-card p-6 text-center text-white/50">
          No SLA data available for this month yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {ordered.map((p) => (
            <SlaCard key={p.profile_type} profile={p} devices={meters} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Connect / Disconnect command SLA (MTD, currently mock-backed) ─────────

const COMMAND_SLA_ICON = {
  DISCONNECT: Power,
  CONNECT: PlugZap,
}

const COMMAND_SLA_ORDER = ['DISCONNECT', 'CONNECT']

const CommandSlaCard = ({ entry }) => {
  const Icon = COMMAND_SLA_ICON[entry.command_type] ?? Activity
  const color = slaColor(entry.sla_pct)
  const pctLabel = entry.sla_pct == null ? '—' : `${entry.sla_pct.toFixed(2)}%`
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: `${color}20` }}
        >
          <Icon size={18} style={{ color }} />
        </div>
        <span style={{ fontSize: 11, color }}>
          {entry.label} · {entry.target_hours}h
        </span>
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 28 }}>{pctLabel}</div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>
          {entry.within_sla.toLocaleString()} / {entry.issued.toLocaleString()} within SLA
        </div>
        <div style={{ color, fontSize: 11, marginTop: 4 }}>
          {entry.breached.toLocaleString()} breached · {entry.failed.toLocaleString()} failed · {entry.pending.toLocaleString()} pending
        </div>
      </div>
    </div>
  )
}

const CommandSlaSection = ({ data, loading, error, onRetry }) => {
  const items = (data?.commands ?? [])
  const ordered = COMMAND_SLA_ORDER
    .map((t) => items.find((c) => c.command_type === t))
    .filter(Boolean)

  const isMock = data?.sources?.commands === 'mock'

  return (
    <div data-testid="dashboard-command-sla-row">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-white font-bold" style={{ fontSize: 16 }}>
          Reconnection / Disconnection SLA — Month to Date
        </h2>
        {isMock && (
          <span className="text-white/40 text-xs" title="Mocked pending command_log integration">
            sample data
          </span>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, i) => <SkeletonMetricCard key={i} />)}
        </div>
      ) : error ? (
        <ErrorBanner message={`Command SLA: ${error}`} onRetry={onRetry} />
      ) : ordered.length === 0 ? (
        <div className="glass-card p-6 text-center text-white/50">
          No command SLA data available for this month yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ordered.map((c) => (
            <CommandSlaCard key={c.command_type} entry={c} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { liveAlarms } = useOutletContext()
  const navigate = useNavigate()
  // Spec 018 W4.T11 — saved dashboard layouts. On mount we fetch the user's
  // layouts and pick the default (first-is-default in list ordering) so its
  // name is shown alongside a "Manage layouts" button. Widget positions /
  // refresh cadence are persisted in `widgets` on each layout; this page
  // currently renders the canonical built-in widgets and will honor layout
  // widget overrides incrementally (W4.T11.x follow-up).
  const [activeLayout, setActiveLayout] = useState(null)
  const [layoutManagerOpen, setLayoutManagerOpen] = useState(false)

  const reloadLayouts = async () => {
    try {
      const { data } = await dashboardsAPI.list()
      const def = (data || []).find((l) => l.is_default) || (data || [])[0] || null
      setActiveLayout(def)
    } catch {
      // Layout persistence is non-critical; the dashboard still renders the
      // built-in widgets if the endpoint is down.
    }
  }

  useEffect(() => {
    reloadLayouts()
  }, [])

  // KPI row / load profile / alarm feed all come from MDMS via
  // /api/v1/mdms-dashboard/*. DER asset panel below continues to read from
  // the local EMS database.
  const [summary, setSummary] = useState(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [derAssets, setDerAssets] = useState([])
  const [derLoading, setDerLoading] = useState(true)
  const [derError, setDerError] = useState(null)
  const [energyData, setEnergyData] = useState([])
  const [energyLoading, setEnergyLoading] = useState(true)
  const [energyError, setEnergyError] = useState(null)
  const [mdmsAlarms, setMdmsAlarms] = useState([])
  const [alarmsLoading, setAlarmsLoading] = useState(true)
  const [alarmsError, setAlarmsError] = useState(null)
  const [sla, setSla] = useState(null)
  const [slaLoading, setSlaLoading] = useState(true)
  const [slaError, setSlaError] = useState(null)
  const [cmdSla, setCmdSla] = useState(null)
  const [cmdSlaLoading, setCmdSlaLoading] = useState(true)
  const [cmdSlaError, setCmdSlaError] = useState(null)

  const s = summary
  const hasAnyKpi = s != null

  const loadDER = () => {
    setDerLoading(true)
    setDerError(null)
    derAPI.list()
      .then(({ data }) => setDerAssets(data))
      .catch((err) => setDerError(formatApiError(err)))
      .finally(() => setDerLoading(false))
  }

  const loadSla = () => {
    setSlaLoading(true)
    setSlaError(null)
    slaAPI.kpis()
      .then(({ data }) => setSla(data))
      .catch((err) => setSlaError(formatApiError(err)))
      .finally(() => setSlaLoading(false))
  }

  const loadCmdSla = () => {
    setCmdSlaLoading(true)
    setCmdSlaError(null)
    slaAPI.connectDisconnect()
      .then(({ data }) => setCmdSla(data))
      .catch((err) => setCmdSlaError(formatApiError(err)))
      .finally(() => setCmdSlaLoading(false))
  }

  const loadSummary = () => {
    setSummaryLoading(true)
    setSummaryError(null)
    mdmsDashboardAPI.summary(24)
      .then(({ data }) => {
        setSummary(data)
        setLastRefresh(new Date().toISOString())
      })
      .catch((err) => setSummaryError(formatApiError(err)))
      .finally(() => setSummaryLoading(false))
  }

  const loadEnergy = () => {
    setEnergyLoading(true)
    setEnergyError(null)
    mdmsDashboardAPI.loadProfile(24)
      .then(({ data }) => {
        const pts = data?.points || []
        setEnergyData(
          pts.map((p) => ({
            time: new Date(p.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            load: p.total_kw ?? 0,
          }))
        )
      })
      .catch((err) => setEnergyError(formatApiError(err)))
      .finally(() => setEnergyLoading(false))
  }

  const loadMdmsAlarms = () => {
    setAlarmsLoading(true)
    setAlarmsError(null)
    mdmsDashboardAPI.alarms({ hours: 720, limit: 25 })
      .then(({ data }) => setMdmsAlarms(data?.items || []))
      .catch((err) => setAlarmsError(formatApiError(err)))
      .finally(() => setAlarmsLoading(false))
  }

  useEffect(() => {
    loadSummary()
    loadDER()
    loadEnergy()
    loadSla()
    loadCmdSla()
    loadMdmsAlarms()
  }, [])

  const handleRetry = () => {
    loadSummary()
    loadDER()
    loadEnergy()
    loadSla()
    loadCmdSla()
    loadMdmsAlarms()
  }

  const pvAsset = derAssets.find((a) => a.asset_type === 'pv')
  const bessAsset = derAssets.find((a) => a.asset_type === 'bess')
  const evAsset = derAssets.find((a) => a.asset_type === 'ev_charger')

  const sparklineOption = {
    backgroundColor: 'transparent',
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, data: energyData.map((d) => d.time) },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line',
      data: energyData.map((d) => d.load),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#02C9A8', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(2,201,168,0.3)' },
            { offset: 1, color: 'rgba(2,201,168,0)' },
          ],
        },
      },
    }],
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 } },
  }

  const topLevelError = summaryError && !hasAnyKpi
  const anyLoading = summaryLoading && !hasAnyKpi

  return (
    <div className="space-y-6 animate-slide-up" data-testid="dashboard-page">
      {/* Spec 018 W4.T11 — active layout indicator + "Manage layouts" entry point. */}
      <div className="flex items-center justify-between" data-testid="dashboard-layout-bar">
        <div className="flex items-center gap-2 text-white/60 text-xs">
          <LayoutGrid size={12} />
          <span>
            Layout:{' '}
            <span className="text-white font-bold">
              {activeLayout?.name ?? 'Default'}
            </span>
          </span>
          {activeLayout?.shared && (
            <span className="text-accent-blue" style={{ fontSize: 10 }}>SHARED</span>
          )}
        </div>
        <button
          onClick={() => setLayoutManagerOpen(true)}
          className="btn-secondary flex items-center gap-2"
          style={{ padding: '6px 12px', fontSize: 12 }}
          data-testid="manage-layouts-btn"
        >
          <LayoutGrid size={12} /> Manage layouts
        </button>
      </div>

      <LayoutManager
        open={layoutManagerOpen}
        onClose={() => setLayoutManagerOpen(false)}
        onLayoutChanged={reloadLayouts}
      />

      {/* MDMS upstream banner — warn without blanking the page when /summary 500s */}
      {summaryError && hasAnyKpi && (
        <UpstreamErrorPanel upstream="mdms" detail={summaryError}
          lastRefresh={lastRefresh} onRetry={handleRetry} />
      )}
      {/* Top-level error — shown when /summary failed and we have nothing to render */}
      {topLevelError && (
        <ErrorBanner message={summaryError} onRetry={handleRetry} />
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4" data-testid="dashboard-kpi-row">
        {anyLoading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonMetricCard key={i} />)
        ) : s ? (
          <>
            <MetricCard icon={Wifi}          label="Online Meters"  value={s.online_meters ?? '—'}
              sub={s.total_meters != null ? `of ${Number(s.total_meters).toLocaleString()} total` : 'HES unavailable'} color="#02C9A8" />
            <MetricCard icon={WifiOff}       label="Offline Meters" value={s.offline_meters ?? '—'} sub="check connectivity" color="#6B7280" />
            <MetricCard icon={AlertTriangle} label="Active Alarms"  value={s.active_alarms ?? '—'}  sub="require attention"  color="#E94B4B" />
            <MetricCard icon={CheckCircle}   label="Comm Success"
              value={s.comm_success_rate != null ? `${s.comm_success_rate}%` : '—'}
              sub="network health"    color="#02C9A8" />
            <MetricCard icon={MapPin}        label="Transformers"   value={s.total_transformers ?? '—'}
              sub={s.total_feeders != null ? `${s.total_feeders} feeders` : 'MDMS unavailable'} color="#56CCF2" />
            <MetricCard icon={Activity}      label="Tamper Alerts"  value={s.tamper_meters ?? '—'} sub="this period" color="#F97316" />
          </>
        ) : (
          /* Summary reached an empty state (not loading, no error) */
          <div className="col-span-full glass-card p-6 text-center text-white/50">
            No network summary data available yet.
          </div>
        )}
      </div>

      {/* Metrology SLA — month-to-date, sourced from MDMS validation_rules. */}
      <SlaSection
        sla={sla}
        loading={slaLoading}
        error={slaError}
        onRetry={loadSla}
      />

      {/* Reconnection / Disconnection SLA — month-to-date. Mocked until
          command_log confirmation aggregates are wired up. */}
      <CommandSlaSection
        data={cmdSla}
        loading={cmdSlaLoading}
        error={cmdSlaError}
        onRetry={loadCmdSla}
      />

      {/* Gauges + sparkline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Comm rate gauge */}
        <div className="glass-card p-4 flex flex-col">
          <div className="text-white/60 font-bold mb-2" style={{ fontSize: 12 }}>COMM SUCCESS RATE</div>
          <div className="flex-1" style={{ height: 160 }}>
            {anyLoading ? (
              <Skeleton style={{ height: '100%', borderRadius: 12 }} />
            ) : (
              <ReactECharts option={GAUGE_OPTION(s?.comm_success_rate ?? null, 'Comm Rate')} style={{ height: '100%' }} />
            )}
          </div>
        </div>

        {/* Energy sparkline */}
        <div className="glass-card p-4 col-span-1 lg:col-span-2 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-white/60 font-bold" style={{ fontSize: 12 }}>NETWORK LOAD — LAST 24h</div>
              {energyLoading ? (
                <Skeleton style={{ height: 22, width: 120, marginTop: 4 }} />
              ) : energyError ? (
                <div className="text-status-critical font-bold mt-1" style={{ fontSize: 14 }}>
                  Load profile unavailable
                </div>
              ) : (
                <div className="text-energy-green font-black mt-1" style={{ fontSize: 22 }}>
                  {energyData.at(-1)?.load ?? 0} <span className="text-white/40 font-medium" style={{ fontSize: 14 }}>kW</span>
                </div>
              )}
            </div>
            {!energyLoading && !energyError && <span className="badge-ok">Live</span>}
          </div>
          <div className="flex-1" style={{ minHeight: 100 }}>
            {energyLoading ? (
              <Skeleton style={{ height: 120, borderRadius: 12 }} />
            ) : energyError ? (
              <div className="text-white/50 text-center py-6" style={{ fontSize: 13 }}>
                {energyError}{' '}
                <button onClick={loadEnergy} className="text-accent-blue hover:text-white underline ml-2">
                  Retry
                </button>
              </div>
            ) : (
              <ReactECharts option={sparklineOption} style={{ height: 120 }} />
            )}
          </div>
        </div>
      </div>

      {/* DER Summary */}
      <div>
        <h2 className="text-white font-bold mb-3" style={{ fontSize: 16 }}>DER Asset Status</h2>
        {derLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="glass-card p-5 space-y-3">
                <Skeleton style={{ height: 20, width: '40%' }} />
                <Skeleton style={{ height: 32, width: '70%' }} />
                <Skeleton style={{ height: 12, width: '50%' }} />
              </div>
            ))}
          </div>
        ) : derError ? (
          <ErrorBanner message={`DER assets: ${derError}`} onRetry={loadDER} />
        ) : derAssets.length === 0 ? (
          <div className="glass-card p-6 text-center text-white/50">
            No DER assets registered.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* PV */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => navigate(pvAsset ? `/der/pv/${pvAsset.id}` : '/der/pv')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(pvAsset ? `/der/pv/${pvAsset.id}` : '/der/pv')
                }
              }}
              className="glass-card p-5 cursor-pointer hover:border-white/30 transition-colors"
              data-testid="der-card-pv"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(245,158,11,0.2)' }}>
                  <Zap size={14} className="text-status-medium" />
                </div>
                <div>
                  <div className="text-white font-bold text-sm">PV Cluster</div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>{pvAsset?.name ?? 'No PV asset'}</div>
                </div>
                {pvAsset && (
                  <span className={`ml-auto ${pvAsset.status === 'online' ? 'badge-ok' : 'badge-medium'}`}>
                    {pvAsset.status}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>Output</div>
                  <div className="text-white font-bold" style={{ fontSize: 18 }}>
                    {pvAsset?.current_output_kw ?? 0} <span className="text-white/40 font-normal text-sm">kW</span>
                  </div>
                </div>
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>Today</div>
                  <div className="text-energy-green font-bold" style={{ fontSize: 18 }}>
                    {Math.round(pvAsset?.generation_today_kwh ?? 0)} <span className="text-white/40 font-normal text-sm">kWh</span>
                  </div>
                </div>
              </div>
            </div>

            {/* BESS */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => navigate(bessAsset ? `/der/bess/${bessAsset.id}` : '/der/bess')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(bessAsset ? `/der/bess/${bessAsset.id}` : '/der/bess')
                }
              }}
              className="glass-card p-5 cursor-pointer hover:border-white/30 transition-colors"
              data-testid="der-card-bess"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(56,204,242,0.2)' }}>
                  <Battery size={14} className="text-sky-blue" />
                </div>
                <div>
                  <div className="text-white font-bold text-sm">BESS</div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>{bessAsset?.name ?? 'No BESS asset'}</div>
                </div>
                {bessAsset && (
                  <span className={`ml-auto ${bessAsset.status === 'discharging' ? 'badge-ok' : bessAsset.status === 'charging' ? 'badge-info' : 'badge-medium'}`}>
                    {bessAsset.status}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>SoC</div>
                  <div className="text-sky-blue font-bold" style={{ fontSize: 18 }}>
                    {bessAsset?.state_of_charge != null
                      ? Number(bessAsset.state_of_charge).toFixed(2)
                      : '0.00'}
                    <span className="text-white/40 font-normal text-sm">%</span>
                  </div>
                </div>
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>Output</div>
                  <div className="text-white font-bold" style={{ fontSize: 18 }}>
                    {bessAsset?.current_output_kw ?? 0} <span className="text-white/40 font-normal text-sm">kW</span>
                  </div>
                </div>
              </div>
            </div>

            {/* EV Charger */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => navigate(evAsset ? `/der/ev/${evAsset.id}` : '/der/ev')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(evAsset ? `/der/ev/${evAsset.id}` : '/der/ev')
                }
              }}
              className="glass-card p-5 cursor-pointer hover:border-white/30 transition-colors"
              data-testid="der-card-ev"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(2,201,168,0.2)' }}>
                  <Car size={14} className="text-energy-green" />
                </div>
                <div>
                  <div className="text-white font-bold text-sm">EV Charger</div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>{evAsset?.name ?? 'No EV charger asset'}</div>
                </div>
                {evAsset && (
                  <span className={`ml-auto ${evAsset.status === 'online' ? 'badge-ok' : 'badge-medium'}`}>
                    {evAsset.status}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>Active Sessions</div>
                  <div className="text-energy-green font-bold" style={{ fontSize: 18 }}>
                    {evAsset?.active_sessions ?? 0} <span className="text-white/40 font-normal text-sm">/ {evAsset?.num_ports ?? 0}</span>
                  </div>
                </div>
                <div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>Load</div>
                  <div className="text-white font-bold" style={{ fontSize: 18 }}>
                    {evAsset?.current_output_kw ?? 0} <span className="text-white/40 font-normal text-sm">kW</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Alarm feed — sourced from MDMS gp_hes.mdm_pushevent. Falls back to the
          SSE-driven liveAlarms stream if the MDMS feed is empty. */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-white font-bold" style={{ fontSize: 16 }}>Alarm Feed</h2>
          <span className="text-white/40 text-xs">
            {alarmsLoading ? 'loading…' : `${mdmsAlarms.length} events from MDMS`}
          </span>
        </div>
        {alarmsLoading ? (
          <Skeleton style={{ height: 120, borderRadius: 12 }} />
        ) : alarmsError ? (
          <ErrorBanner message={`Alarms: ${alarmsError}`} onRetry={loadMdmsAlarms} />
        ) : mdmsAlarms.length === 0 ? (
          liveAlarms?.length > 0 ? (
            <div className="glass-card overflow-hidden">
              <table className="data-table">
                <thead>
                  <tr><th>Severity</th><th>Type</th><th>Meter</th><th>Description</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {liveAlarms.slice(0, 10).map((a, i) => (
                    <tr key={i}>
                      <td><span className={`badge-${a.severity}`}>{a.severity}</span></td>
                      <td className="text-accent-blue">{a.alarm_type?.replace(/_/g, ' ')}</td>
                      <td className="text-white/60 font-mono text-xs">{a.meter_serial ?? '—'}</td>
                      <td className="text-white/80">{a.title}</td>
                      <td className="text-white/40 text-xs">{new Date(a.triggered_at).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="glass-card p-6 text-center text-white/50">
              No alarms reported in the last 30 days.
            </div>
          )
        ) : (
          <div className="glass-card overflow-hidden">
            <table className="data-table">
              <thead>
                <tr><th>Severity</th><th>Meter</th><th>Events</th><th>Time</th></tr>
              </thead>
              <tbody>
                {mdmsAlarms.slice(0, 15).map((a, i) => (
                  <tr key={i}>
                    <td>
                      <span className={a.is_tamper ? 'badge-critical' : 'badge-medium'}>
                        {a.is_tamper ? 'tamper' : 'info'}
                      </span>
                    </td>
                    <td className="text-white/60 font-mono text-xs">{a.meter_id || '—'}</td>
                    <td className="text-white/80 text-xs">
                      {(a.messages || []).slice(0, 2).join(' · ')}
                      {a.messages?.length > 2 && <span className="text-white/40"> +{a.messages.length - 2} more</span>}
                    </td>
                    <td className="text-white/40 text-xs">{new Date(a.triggered_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
