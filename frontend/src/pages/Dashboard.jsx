import { useOutletContext } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  Wifi, WifiOff, AlertTriangle, CheckCircle, Zap,
  Activity, MapPin, Battery, Car, RefreshCw, LayoutGrid,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, energyAPI, dashboardsAPI } from '@/services/api'
import { useSSOTDashboard } from '@/hooks/useSSOTDashboard'
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

// ─── Page ──────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { liveAlarms } = useOutletContext()
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

  // Spec 018 W1.T9: KPIs sourced from the SSOT proxy. No legacy fallback.
  const { kpis, errors: ssotErrors, loading: summaryLoading, refetch, lastRefresh } = useSSOTDashboard()
  // Build the "summary" shape the rest of the page already expects, directly
  // from proxy-fetched values. When any field is null (upstream down) we keep
  // the field null so MetricCard renders "—" rather than a hardcoded fallback.
  const s = kpis?.total_meters == null && kpis?.online_meters == null ? null : kpis
  const hasAnyKpi = s != null
  const summaryError = ssotErrors.hes || ssotErrors.mdms || null
  const [derAssets, setDerAssets] = useState([])
  const [derLoading, setDerLoading] = useState(true)
  const [derError, setDerError] = useState(null)
  const [energyData, setEnergyData] = useState([])
  const [energyLoading, setEnergyLoading] = useState(true)
  const [energyError, setEnergyError] = useState(null)

  const loadDER = () => {
    setDerLoading(true)
    setDerError(null)
    derAPI.list()
      .then(({ data }) => setDerAssets(data))
      .catch((err) => setDerError(err?.response?.data?.detail ?? err?.message ?? 'Unavailable'))
      .finally(() => setDerLoading(false))
  }

  const loadEnergy = () => {
    setEnergyLoading(true)
    setEnergyError(null)
    energyAPI.loadProfile({ hours: 24 })
      .then((res) => {
        const hours = res.data.hours || []
        const total = res.data.total || []
        setEnergyData(hours.map((time, i) => ({ time, load: total[i] ?? 0 })))
      })
      .catch((err) => setEnergyError(err?.response?.data?.detail ?? err?.message ?? 'Unavailable'))
      .finally(() => setEnergyLoading(false))
  }

  useEffect(() => {
    loadDER()
    loadEnergy()
  }, [])

  const handleRetry = () => {
    refetch?.()
    loadDER()
    loadEnergy()
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

      {/* SSOT upstream banners — shown when proxy returns error but the UI should keep rendering */}
      {ssotErrors.hes && hasAnyKpi && (
        <UpstreamErrorPanel upstream="hes" detail={ssotErrors.hes}
          lastRefresh={lastRefresh} onRetry={handleRetry} />
      )}
      {ssotErrors.mdms && hasAnyKpi && (
        <UpstreamErrorPanel upstream="mdms" detail={ssotErrors.mdms}
          lastRefresh={lastRefresh} onRetry={handleRetry} />
      )}
      {/* Top-level error — shown when every KPI source failed */}
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
            <div className="glass-card p-5">
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
            <div className="glass-card p-5">
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
                    {bessAsset?.state_of_charge ?? 0}<span className="text-white/40 font-normal text-sm">%</span>
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
            <div className="glass-card p-5">
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

      {/* Live alarm feed */}
      {liveAlarms?.length > 0 && (
        <div>
          <h2 className="text-white font-bold mb-3" style={{ fontSize: 16 }}>Live Alarm Feed</h2>
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
        </div>
      )}
    </div>
  )
}
