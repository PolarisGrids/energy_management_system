// Spec 018 W3.T11 — BESS aggregate + per-asset grid.
// Route: /der/bess.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Battery, Zap, Gauge, RefreshCw, AlertTriangle, TrendingUp } from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const WINDOWS = [
  { id: '1h', label: '1 h' },
  { id: '24h', label: '24 h' },
  { id: '7d', label: '7 d' },
]

export default function DERBess() {
  const [window, setWindow] = useState('24h')
  const [data, setData] = useState({ assets: [], aggregate: [], banner: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await derAPI.telemetry({ type: 'bess', window })
      setData(data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load BESS telemetry.')
    } finally {
      setLoading(false)
    }
  }, [window])

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const totals = useMemo(() => {
    const assets = data.assets || []
    const totalKwh = assets.reduce((s, a) => s + (a.capacity_kwh ?? 0), 0)
    const avgSoc = assets.length
      ? assets.reduce((s, a) => s + (a.soc_pct ?? 0), 0) / assets.length
      : 0
    // Integrate power curve into charged / discharged kWh buckets.
    let charged = 0
    let discharged = 0
    for (const p of data.aggregate || []) {
      const kwh = (p.total_kw || 0) / 60
      if (kwh >= 0) discharged += kwh
      else charged += -kwh
    }
    return { totalKwh, avgSoc, charged, discharged }
  }, [data])

  const chargeDischargeOption = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['Charge', 'Discharge'],
      textStyle: { color: 'rgba(255,255,255,0.6)' },
      top: 0,
    },
    grid: { left: 48, right: 20, top: 32, bottom: 40 },
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
        type: 'bar',
        data: (data.aggregate || []).map((p) => [p.ts, p.total_kw < 0 ? -p.total_kw : 0]),
        itemStyle: { color: 'rgba(86,204,242,0.7)' },
        stack: 'flow',
        barMaxWidth: 8,
      },
      {
        name: 'Discharge',
        type: 'bar',
        data: (data.aggregate || []).map((p) => [p.ts, p.total_kw > 0 ? p.total_kw : 0]),
        itemStyle: { color: 'rgba(2,201,168,0.7)' },
        stack: 'flow',
        barMaxWidth: 8,
      },
    ],
  }), [data])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-bess-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>BESS — Battery Storage Fleet</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-19 · State of charge, cycles, revenue
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="glass-card p-1 flex gap-1">
            {WINDOWS.map((w) => (
              <button key={w.id} onClick={() => setWindow(w.id)}
                className="px-3 py-1.5 rounded-md font-semibold"
                style={{
                  fontSize: 12,
                  background: window === w.id ? 'rgba(86,204,242,0.15)' : 'transparent',
                  color: window === w.id ? '#56CCF2' : 'rgba(255,255,255,0.5)',
                }}>{w.label}</button>
            ))}
          </div>
          <button onClick={load} disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {data.banner && (
        <div className="glass-card p-3 flex items-center gap-3" data-testid="der-bess-banner"
          style={{ borderColor: 'rgba(86,204,242,0.3)', background: 'rgba(86,204,242,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#56CCF2' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{data.banner}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="der-bess-kpis">
        <KPI icon={Gauge} label="Average SoC" value={fmt(totals.avgSoc, 1)} unit="%"
          color={totals.avgSoc >= 60 ? '#02C9A8' : totals.avgSoc >= 30 ? '#F59E0B' : '#E94B4B'} />
        <KPI icon={Battery} label="Fleet Capacity" value={fmt(totals.totalKwh, 0)} unit="kWh" color="#56CCF2" />
        <KPI icon={Zap} label="Discharged" value={fmt(totals.discharged, 1)} unit="kWh" color="#02C9A8" />
        <KPI icon={TrendingUp} label="Charged" value={fmt(totals.charged, 1)} unit="kWh" color="#ABC7FF" />
      </div>

      <div className="glass-card p-5">
        <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>
          CHARGE / DISCHARGE PROFILE — {window === '1h' ? 'last hour' : window === '24h' ? 'last 24 hours' : 'last 7 days'}
        </div>
        <ReactECharts option={chargeDischargeOption} style={{ height: 260 }} notMerge />
      </div>

      <div>
        <h2 className="text-white font-bold mb-3" style={{ fontSize: 15 }}>Per-Battery View</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="der-bess-grid">
          {(data.assets || []).map((a) => <BessCard key={a.id} asset={a} />)}
          {(data.assets || []).length === 0 && !loading && (
            <div className="glass-card p-6 text-center text-white/40" style={{ fontSize: 13 }}>
              No BESS assets registered.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function KPI({ icon: Icon, label, value, unit, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: `${color}20` }}>
          <Icon size={18} style={{ color }} />
        </div>
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 26 }}>
          {value}
          {unit && <span className="text-white/40 font-medium ml-1" style={{ fontSize: 14 }}>{unit}</span>}
        </div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>{label}</div>
      </div>
    </div>
  )
}

function BessCard({ asset }) {
  const soc = asset.soc_pct ?? 0
  const socColor = soc >= 60 ? '#02C9A8' : soc >= 30 ? '#F59E0B' : '#E94B4B'
  // Cycles & revenue aren't in der_telemetry — surface from details when present.
  const cyclesToday = asset.details?.cycles_today ?? null
  const revenue = asset.details?.revenue_today ?? null
  // From aggregate trend fields: session_energy_kwh acts as proxy for dispensed kWh.
  return (
    <div className="glass-card p-4" data-testid="der-bess-card">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: 'rgba(86,204,242,0.2)' }}>
          <Battery size={16} style={{ color: '#56CCF2' }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-white font-bold truncate" style={{ fontSize: 13 }}>{asset.name || asset.id}</div>
          <div className="text-white/40" style={{ fontSize: 11 }}>{asset.id}</div>
        </div>
        <span className="badge-info">{asset.state || '—'}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="SoC" value={`${fmt(soc, 1)}%`} color={socColor} />
        <Field label="Capacity" value={`${fmt(asset.capacity_kwh, 0)} kWh`} />
        <Field label="Power" value={`${fmt(asset.current_output_kw, 1)} kW`} color="#56CCF2" />
        <Field label="Cycles Today" value={cyclesToday != null ? fmt(cyclesToday, 0) : '—'} />
        <Field label="Session Energy" value={asset.session_energy_kwh != null ? `${fmt(asset.session_energy_kwh, 1)} kWh` : '—'} />
        <Field label="Revenue Today" value={revenue != null ? `R ${fmt(revenue, 0)}` : '—'} />
      </div>
    </div>
  )
}

function Field({ label, value, color = '#fff' }) {
  return (
    <div>
      <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ color, fontSize: 14, fontWeight: 700, fontFamily: 'monospace' }}>{value}</div>
    </div>
  )
}
