// BESS individual asset detail page.
// Route: /der/bess/:assetId
//
// Data:
//   /der/telemetry?asset_id=&window=  → KPIs + SoC / power curve
//   /der/:assetId/metrology?window=   → daily charged / discharged rollup
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Battery, Gauge,
  RefreshCw, TrendingUp, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'

const POLL_MS = 30_000
const ACCENT = '#56CCF2'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const socColor = (v) =>
  v == null ? '#ABC7FF' : v >= 60 ? '#02C9A8' : v >= 30 ? '#F59E0B' : '#E94B4B'

const stateClass = (s) => {
  switch ((s || '').toLowerCase()) {
    case 'charging':    return 'badge-info'
    case 'discharging': return 'badge-ok'
    case 'idle':        return 'badge-low'
    case 'offline':     return 'badge-critical'
    default:            return 'badge-low'
  }
}

export default function DERBessDetail() {
  const { assetId } = useParams()
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [telemetry, setTelemetry] = useState({ assets: [], aggregate: [], banner: null })
  const [metrology, setMetrology] = useState({ daily: [], banner: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  const loadTelemetry = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await derAPI.telemetry({ asset_id: assetId, window })
      setTelemetry({
        assets: data.assets || [],
        aggregate: data.aggregate || [],
        banner: data.banner ?? null,
      })
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load telemetry.')
    } finally {
      setLoading(false)
    }
  }, [assetId, window])

  const loadMetrology = useCallback(async () => {
    try {
      const { data } = await derAPI.metrology(assetId, {
        window: window === '1h' || window === '24h' ? '7d' : window === '7d' ? '7d' : '30d',
        daily_only: true,
      })
      setMetrology({ daily: data.daily || [], banner: data.banner ?? null })
    } catch {
      setMetrology({ daily: [], banner: null })
    }
  }, [assetId, window])

  useEffect(() => {
    loadTelemetry()
    loadMetrology()
    const id = setInterval(loadTelemetry, POLL_MS)
    return () => clearInterval(id)
  }, [loadTelemetry, loadMetrology])

  const asset = telemetry.assets[0]
  const consumer = asset?.consumer

  const kpis = useMemo(() => {
    if (!asset) return {}
    const soc = asset.soc_pct
    const energyStored = (soc != null && asset.capacity_kwh != null)
      ? (soc / 100) * asset.capacity_kwh
      : null
    // Integrate aggregate → charged vs discharged kWh
    let chargedKwh = 0, dischargedKwh = 0
    for (const p of telemetry.aggregate || []) {
      const kwh = (p.total_kw || 0) / (window === '30d' ? 1 : 60)
      if (kwh < 0) chargedKwh += -kwh
      else dischargedKwh += kwh
    }
    return {
      soc,
      energyStored,
      capacity: asset.capacity_kwh,
      power: asset.current_output_kw,
      chargedKwh,
      dischargedKwh,
      sessionEnergy: asset.session_energy_kwh,
    }
  }, [asset, telemetry.aggregate, window])

  const socCurveChart = useMemo(() => buildSoCCurve(telemetry.aggregate), [telemetry.aggregate])
  const dailyChart = useMemo(() => buildDailyChart(metrology.daily), [metrology.daily])

  if (loading && !asset) {
    return (
      <div className="flex items-center justify-center py-16 text-white/40">
        <RefreshCw size={16} className="animate-spin mr-3" /> Loading asset detail…
      </div>
    )
  }

  if (!asset) {
    return (
      <div className="space-y-4">
        <BackBtn onClick={() => navigate('/der/bess')} />
        <div className="glass-card p-6 text-white/60 text-center" data-testid="der-bess-detail-missing">
          {error || `No BESS asset found with id "${assetId}".`}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-bess-detail-page">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <BackBtn onClick={() => navigate('/der/bess')} />
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>
            {consumer?.name || asset.name || asset.id}
          </h1>
          <div className="text-white/40 flex items-center gap-3 flex-wrap" style={{ fontSize: 12 }}>
            <span className="font-mono">{asset.id}</span>
            {asset.feeder_id && <span>· Feeder {asset.feeder_id}</span>}
            {asset.dtr_id && <span>· DTR {asset.dtr_id}</span>}
            {consumer?.account_no && <span>· Acct {consumer.account_no}</span>}
            {consumer?.tariff_code && <span>· Tariff {consumer.tariff_code}</span>}
            {asset.state && (
              <span className={stateClass(asset.state)}>{asset.state}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DERTimeRangePicker value={window} onChange={setWindow} accent={ACCENT} />
          <button onClick={loadTelemetry} disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {telemetry.banner && <Banner color={ACCENT} message={telemetry.banner} testid="der-bess-detail-banner" />}
      {error && <Banner color="#E94B4B" message={error} />}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="der-bess-detail-kpis">
        <KPI icon={Gauge} label="State of Charge"
          value={kpis.soc == null ? '—' : fmt(kpis.soc, 1)} unit={kpis.soc == null ? '' : '%'}
          color={socColor(kpis.soc)} />
        <KPI icon={Battery} label="Energy Stored"
          value={fmt(kpis.energyStored, 0)} unit="kWh" color={ACCENT} />
        <KPI icon={TrendingUp} label="Discharged (window)"
          value={fmt(kpis.dischargedKwh, 1)} unit="kWh" color="#02C9A8" />
        <KPI icon={Zap} label="Current Power"
          value={kpis.power == null ? '—' : `${kpis.power >= 0 ? '+' : ''}${fmt(kpis.power, 1)}`}
          unit="kW" color={kpis.power != null && kpis.power < 0 ? ACCENT : '#02C9A8'} />
      </div>

      {/* Secondary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard label="Rated Capacity" value={`${fmt(kpis.capacity, 0)} kWh`} />
        <StatCard label="Session Energy" value={kpis.sessionEnergy != null ? `${fmt(kpis.sessionEnergy, 1)} kWh` : '—'} />
        <StatCard label="Charged (window)" value={`${fmt(kpis.chargedKwh, 1)} kWh`} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`POWER CURVE — ${windowLabel(window)}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={socCurveChart} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="DAILY ENERGY — billing-grade rollup"
          subtitle={metrology.banner ? 'no metrology yet' : null}>
          <ReactECharts option={dailyChart} style={{ height: 260 }} notMerge />
        </ChartCard>
      </div>

      {/* Consumer card */}
      {consumer && (
        <div className="glass-card p-5">
          <h2 className="text-white font-bold mb-3" style={{ fontSize: 15 }}>Consumer</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DetailField label="Name" value={consumer.name} />
            <DetailField label="Account" value={consumer.account_no || '—'} mono />
            <DetailField label="Tariff" value={consumer.tariff_code || '—'} />
            <DetailField label="Consumer ID" value={consumer.id} mono small />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function BackBtn({ onClick }) {
  return (
    <button onClick={onClick}
      className="text-white/40 hover:text-white inline-flex items-center gap-1 mb-2"
      style={{ fontSize: 12 }}>
      <ArrowLeft size={11} /> Back to BESS fleet
    </button>
  )
}

function KPI({ icon: Icon, label, value, unit, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 24 }}>
          {value}
          {unit && <span className="text-white/40 font-medium ml-1" style={{ fontSize: 13 }}>{unit}</span>}
        </div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
      </div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="glass-card p-4">
      <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
      <div className="text-white font-bold mt-1" style={{ fontSize: 16 }}>{value}</div>
    </div>
  )
}

function Banner({ message, color, testid }) {
  return (
    <div className="glass-card p-3 flex items-center gap-3" data-testid={testid}
      style={{ borderColor: `${color}4D`, background: `${color}14` }}>
      <AlertTriangle size={16} style={{ color }} />
      <span className="text-white/80" style={{ fontSize: 13 }}>{message}</span>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="text-white/60 font-bold" style={{ fontSize: 12 }}>{title}</div>
        {subtitle && <div className="text-white/30" style={{ fontSize: 11 }}>{subtitle}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  )
}

function DetailField({ label, value, mono, small }) {
  return (
    <div>
      <div className="text-white/40" style={{ fontSize: 10 }}>{label}</div>
      <div className={mono ? 'font-mono' : ''}
        style={{ color: '#fff', fontSize: small ? 11 : 13, fontWeight: small ? 500 : 700 }}>
        {value}
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function windowLabel(w) {
  return w === '1h' ? 'last hour' : w === '24h' ? 'last 24 h' : w === '7d' ? 'last 7 days' : 'last 30 days'
}

function buildSoCCurve(aggregate) {
  // Separate charge (negative power) and discharge (positive power) series.
  const charge = (aggregate || []).map((p) => [p.ts, p.total_kw < 0 ? -p.total_kw : 0])
  const discharge = (aggregate || []).map((p) => [p.ts, p.total_kw > 0 ? p.total_kw : 0])
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      data: ['Charge', 'Discharge'],
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 },
      top: 0, right: 0,
    },
    grid: { left: 48, right: 20, top: 28, bottom: 40 },
    xAxis: {
      type: 'time',
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
    },
    yAxis: {
      type: 'value', name: 'kW',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        name: 'Charge',
        type: 'bar', stack: 'flow', barMaxWidth: 8,
        data: charge,
        itemStyle: { color: 'rgba(86,204,242,0.8)', borderRadius: [2, 2, 0, 0] },
      },
      {
        name: 'Discharge',
        type: 'bar', stack: 'flow', barMaxWidth: 8,
        data: discharge,
        itemStyle: { color: 'rgba(2,201,168,0.8)', borderRadius: [2, 2, 0, 0] },
      },
    ],
  }
}

function buildDailyChart(daily) {
  const rows = (daily || []).slice().sort((a, b) => (a.date < b.date ? -1 : 1))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 },
      top: 0, right: 0,
    },
    grid: { left: 48, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.date.slice(5)),
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', name: 'kWh',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        name: 'Discharged',
        type: 'bar', stack: 'energy', barMaxWidth: 14,
        data: rows.map((r) => Number(r.kwh_generated || 0).toFixed(1)),
        itemStyle: { color: '#02C9A8', borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'Charged',
        type: 'bar', stack: 'energy', barMaxWidth: 14,
        data: rows.map((r) => Number(r.kwh_imported || 0).toFixed(1)),
        itemStyle: { color: '#56CCF2', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
}
