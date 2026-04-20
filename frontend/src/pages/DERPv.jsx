// Spec 018 W3.T11 — PV aggregate + per-asset grid.
// Route: /der/pv.
// Live telemetry via /api/v1/der/telemetry?type=pv&window=24h.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Sun, Zap, Gauge, CheckCircle, AlertTriangle, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const WINDOWS = [
  { id: '1h', label: '1 h' },
  { id: '24h', label: '24 h' },
  { id: '7d', label: '7 d' },
]

export default function DERPv() {
  const [window, setWindow] = useState('24h')
  const [data, setData] = useState({ assets: [], aggregate: [], banner: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await derAPI.telemetry({ type: 'pv', window })
      setData(data)
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load PV telemetry.')
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
    const totalCap = assets.reduce((s, a) => s + (a.capacity_kw ?? 0), 0)
    const totalOut = assets.reduce((s, a) => s + (a.current_output_kw ?? 0), 0)
    const onlineCount = assets.filter(
      (a) => a.inverter_online === true || a.state === 'online',
    ).length
    const achievement = assets.length
      ? assets.reduce((s, a) => s + (a.achievement_rate_pct ?? 0), 0) / assets.length
      : 0
    // Equivalent hours today ≈ integrated kWh / capacity. Best-effort from aggregate curve.
    const aggKwh = (data.aggregate || []).reduce((s, p) => s + (p.total_kw ?? 0), 0)
    // Each bucket is 1-min for 24h, so kWh = sum(kW) * (1/60)
    const eqHours = totalCap > 0 ? (aggKwh / 60) / totalCap : 0
    return { totalCap, totalOut, onlineCount, achievement, eqHours }
  }, [data])

  const chartOption = useMemo(() => {
    const points = (data.aggregate || []).map((p) => [p.ts, p.total_kw])
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
        type: 'value',
        name: 'kW',
        nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      },
      series: [{
        type: 'line',
        data: points,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#F59E0B', width: 2 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245,158,11,0.4)' },
              { offset: 1, color: 'rgba(245,158,11,0.02)' },
            ],
          },
        },
      }],
    }
  }, [data])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-pv-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>PV Solar — Fleet</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-17 · Live telemetry via hesv2.der.telemetry
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="glass-card p-1 flex gap-1">
            {WINDOWS.map((w) => (
              <button key={w.id} onClick={() => setWindow(w.id)}
                className="px-3 py-1.5 rounded-md font-semibold whitespace-nowrap"
                style={{
                  fontSize: 12,
                  background: window === w.id ? 'rgba(245,158,11,0.15)' : 'transparent',
                  color: window === w.id ? '#F59E0B' : 'rgba(255,255,255,0.5)',
                }}>{w.label}</button>
            ))}
          </div>
          <button onClick={load} disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {data.banner && (
        <div className="glass-card p-3 flex items-center gap-3" data-testid="der-pv-banner"
          style={{ borderColor: 'rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#F59E0B' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{data.banner}</span>
        </div>
      )}
      {error && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4" data-testid="der-pv-kpis">
        <KPI icon={Zap} label="Total Output" value={fmt(totals.totalOut, 1)} unit="kW" color="#F59E0B" />
        <KPI icon={Gauge} label="Fleet Capacity" value={fmt(totals.totalCap, 0)} unit="kW" color="#F97316" />
        <KPI icon={CheckCircle} label="Achievement" value={fmt(totals.achievement, 1)} unit="%" color="#02C9A8" />
        <KPI icon={Wifi} label="Online Inverters" value={`${totals.onlineCount}/${(data.assets || []).length}`} color="#56CCF2" />
        <KPI icon={Sun} label="Equivalent Hours" value={fmt(totals.eqHours, 2)} unit="h" color="#ABC7FF" />
      </div>

      <div className="glass-card p-5">
        <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>
          AGGREGATE GENERATION — {window === '1h' ? 'last hour' : window === '24h' ? 'last 24 hours' : 'last 7 days'}
        </div>
        <ReactECharts option={chartOption} style={{ height: 260 }} notMerge />
        {refreshedAt && (
          <div className="text-white/30 text-xs mt-2">
            Updated {refreshedAt.toLocaleTimeString('en-ZA')}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-white font-bold mb-3" style={{ fontSize: 15 }}>Per-Asset View</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="der-pv-grid">
          {(data.assets || []).map((a) => (
            <PvAssetCard key={a.id} asset={a} capacity={totals.totalCap} />
          ))}
          {(data.assets || []).length === 0 && !loading && (
            <div className="glass-card p-6 text-center text-white/40" style={{ fontSize: 13 }}>
              No PV assets registered.
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
        <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
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

function PvAssetCard({ asset }) {
  const online = asset.inverter_online === true || (asset.state || '').toLowerCase() === 'online'
  const ach = asset.achievement_rate_pct ?? 0
  const color = ach >= 80 ? '#02C9A8' : ach >= 60 ? '#F59E0B' : '#E94B4B'
  // Equivalent hours today: session_energy_kwh (if simulator provides) / capacity
  const eqHours =
    asset.capacity_kw && asset.session_energy_kwh
      ? asset.session_energy_kwh / asset.capacity_kw
      : null
  return (
    <div className="glass-card p-4" data-testid="der-pv-card">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: 'rgba(245,158,11,0.2)' }}>
          <Sun size={16} style={{ color: '#F59E0B' }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-white font-bold truncate" style={{ fontSize: 13 }}>
            {asset.name || asset.id}
          </div>
          <div className="text-white/40" style={{ fontSize: 11 }}>{asset.id}</div>
        </div>
        <span className={online ? 'badge-ok' : 'badge-critical'}>
          {online ? <Wifi size={10} /> : <WifiOff size={10} />}
          <span className="ml-1">{online ? 'online' : 'offline'}</span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Capacity" value={`${fmt(asset.capacity_kw, 0)} kW`} />
        <Field label="Current Output" value={`${fmt(asset.current_output_kw, 1)} kW`} color="#F59E0B" />
        <Field label="Achievement" value={`${fmt(ach, 1)}%`} color={color} />
        <Field label="Equivalent Hours" value={eqHours != null ? `${fmt(eqHours, 2)} h` : '—'} />
      </div>
    </div>
  )
}

function Field({ label, value, color = '#fff' }) {
  return (
    <div>
      <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ color, fontSize: 14, fontWeight: 700, fontFamily: 'monospace' }}>
        {value}
      </div>
    </div>
  )
}
