// EV charger individual asset detail page.
// Route: /der/ev/:assetId
//
// Data:
//   /der/telemetry?asset_id=&window=  → KPIs + load curve
//   /der/:assetId/metrology?window=   → daily energy dispensed rollup
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Activity, AlertTriangle, ArrowLeft, Car,
  Info, PlugZap, RefreshCw, TrendingUp, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI, mdmsAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'

const POLL_MS = 30_000
const ACCENT = '#02C9A8'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const stateClass = (s) => {
  switch ((s || '').toLowerCase()) {
    case 'charging': return 'badge-info'
    case 'online':   return 'badge-ok'
    case 'idle':     return 'badge-low'
    case 'offline':  return 'badge-critical'
    case 'fault':    return 'badge-critical'
    default:         return 'badge-low'
  }
}

export default function DEREvDetail() {
  const { assetId } = useParams()
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [telemetry, setTelemetry] = useState({ assets: [], aggregate: [], banner: null })
  const [metrology, setMetrology] = useState({ daily: [], banner: null })
  const [evRate, setEvRate] = useState(null)
  const [evRateMissing, setEvRateMissing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  // MDMS tariff — optional, never synthesized
  useEffect(() => {
    let cancelled = false
    const fetchRate = async () => {
      try {
        const direct = await mdmsAPI.tariff?.('ev_owner').catch(() => null)
        if (!cancelled && direct?.data) {
          const r = direct.data.rate_per_kwh ?? direct.data.r_per_kwh ?? direct.data.rate
          if (r != null) { setEvRate(Number(r)); return }
        }
        const list = await mdmsAPI.tariffs()
        const rows = Array.isArray(list.data)
          ? list.data
          : list.data?.tariffs || list.data?.data || []
        const ev = rows.find((t) =>
          (t.class || t.tariff_class || t.name || '').toLowerCase().includes('ev'),
        )
        if (cancelled) return
        const r = ev?.rate_per_kwh ?? ev?.r_per_kwh ?? ev?.rate
        if (r != null) setEvRate(Number(r))
        else setEvRateMissing(true)
      } catch {
        if (!cancelled) setEvRateMissing(true)
      }
    }
    fetchRate()
    return () => { cancelled = true }
  }, [])

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
    const energyKwh = (telemetry.aggregate || []).reduce(
      (s, p) => s + (p.total_kw ?? 0) / (window === '30d' ? 1 : 60), 0,
    )
    const fee = (asset.session_energy_kwh != null && evRate != null)
      ? asset.session_energy_kwh * evRate : null
    const totalFees = evRate != null ? energyKwh * evRate : null
    return {
      load: asset.current_output_kw,
      capacity: asset.capacity_kw,
      sessionEnergy: asset.session_energy_kwh,
      sessionFee: fee,
      energyKwh,
      totalFees,
      utilPct: (asset.current_output_kw != null && asset.capacity_kw)
        ? (asset.current_output_kw / asset.capacity_kw) * 100 : null,
    }
  }, [asset, telemetry.aggregate, window, evRate])

  const loadCurveChart = useMemo(() => buildLoadCurve(telemetry.aggregate), [telemetry.aggregate])
  const dailyChart = useMemo(() => buildDailyChart(metrology.daily, evRate), [metrology.daily, evRate])

  if (loading && !asset) {
    return (
      <div className="flex items-center justify-center py-16 text-white/40">
        <RefreshCw size={16} className="animate-spin mr-3" /> Loading charger detail…
      </div>
    )
  }

  if (!asset) {
    return (
      <div className="space-y-4">
        <BackBtn onClick={() => navigate('/der/ev')} />
        <div className="glass-card p-6 text-white/60 text-center" data-testid="der-ev-detail-missing">
          {error || `No EV charger found with id "${assetId}".`}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-ev-detail-page">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <BackBtn onClick={() => navigate('/der/ev')} />
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>
            {consumer?.name || asset.name || asset.id}
          </h1>
          <div className="text-white/40 flex items-center gap-3 flex-wrap" style={{ fontSize: 12 }}>
            <span className="font-mono">{asset.id}</span>
            {asset.feeder_id && <span>· Feeder {asset.feeder_id}</span>}
            {asset.dtr_id && <span>· DTR {asset.dtr_id}</span>}
            {consumer?.account_no && <span>· Acct {consumer.account_no}</span>}
            {consumer?.tariff_code && <span>· Tariff {consumer.tariff_code}</span>}
            {asset.state && <span className={stateClass(asset.state)}>{asset.state}</span>}
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

      {telemetry.banner && <Banner color={ACCENT} message={telemetry.banner} testid="der-ev-detail-banner" />}
      {error && <Banner color="#E94B4B" message={error} />}
      {evRateMissing && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(245,158,11,0.35)', background: 'rgba(245,158,11,0.08)' }}>
          <Info size={15} style={{ color: '#F59E0B' }} />
          <span className="text-white/80" style={{ fontSize: 12 }}>
            EV tariff rate not configured — fees shown as '—' until MDMS returns a rate.
          </span>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="der-ev-detail-kpis">
        <KPI icon={Zap} label="Current Load"
          value={fmt(kpis.load, 1)} unit="kW" color={ACCENT} />
        <KPI icon={TrendingUp} label="Energy (window)"
          value={fmt(kpis.energyKwh, 1)} unit="kWh" color="#56CCF2" />
        <KPI icon={Activity} label="Session Energy"
          value={fmt(kpis.sessionEnergy, 2)} unit="kWh" color="#F59E0B" />
        <KPI icon={PlugZap} label="Session Fee"
          value={kpis.sessionFee == null ? '—' : `R ${fmt(kpis.sessionFee, 0)}`}
          color="#ABC7FF" />
      </div>

      {/* Secondary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Rated Capacity" value={`${fmt(kpis.capacity, 0)} kW`} />
        <StatCard label="Utilisation"
          value={kpis.utilPct == null ? '—' : `${fmt(kpis.utilPct, 1)}%`}
          color={kpis.utilPct != null ? (kpis.utilPct > 90 ? '#E94B4B' : kpis.utilPct > 70 ? '#F59E0B' : ACCENT) : undefined} />
        <StatCard label="Fees (window)"
          value={kpis.totalFees == null ? '—' : `R ${fmt(kpis.totalFees, 0)}`} />
        <StatCard label="Sub-type" value={asset.type_code || '—'} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`LOAD CURVE — ${windowLabel(window)}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={loadCurveChart} style={{ height: 260 }} notMerge />
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
      <ArrowLeft size={11} /> Back to EV fleet
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

function StatCard({ label, value, color }) {
  return (
    <div className="glass-card p-4">
      <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
      <div className="font-bold mt-1" style={{ fontSize: 16, color: color || '#fff' }}>{value}</div>
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

function buildLoadCurve(aggregate) {
  const points = (aggregate || []).map((p) => [p.ts, p.total_kw])
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    grid: { left: 48, right: 20, top: 20, bottom: 40 },
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
    series: [{
      type: 'line', data: points, smooth: true, symbol: 'none',
      lineStyle: { color: '#02C9A8', width: 2 },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(2,201,168,0.4)' }, { offset: 1, color: 'rgba(2,201,168,0.02)' }] },
      },
    }],
  }
}

function buildDailyChart(daily, evRate) {
  const rows = (daily || []).slice().sort((a, b) => (a.date < b.date ? -1 : 1))
  const hasFees = evRate != null
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
    grid: { left: 48, right: hasFees ? 52 : 20, top: 30, bottom: 40 },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.date.slice(5)),
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value', name: 'kWh',
        nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      },
      ...(hasFees ? [{
        type: 'value', name: 'R', position: 'right',
        nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
        splitLine: { show: false },
      }] : []),
    ],
    series: [
      {
        name: 'Energy Dispensed', type: 'bar', yAxisIndex: 0, barMaxWidth: 14,
        data: rows.map((r) => Number(r.kwh_imported || 0).toFixed(1)),
        itemStyle: { color: '#02C9A8', borderRadius: [4, 4, 0, 0] },
      },
      ...(hasFees ? [{
        name: 'Fees', type: 'line', yAxisIndex: 1,
        data: rows.map((r) => Number(((r.kwh_imported || 0) * evRate).toFixed(0))),
        smooth: true, symbol: 'none',
        lineStyle: { color: '#F59E0B', width: 2 },
      }] : []),
    ],
  }
}
