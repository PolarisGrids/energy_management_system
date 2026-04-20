// Spec 018 W3.T11 — EV chargers aggregate + per-pile grid.
// Route: /der/ev.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Car, Zap, Activity, PlugZap, RefreshCw, AlertTriangle, TrendingUp, Info } from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, mdmsAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const WINDOWS = [
  { id: '1h', label: '1 h' },
  { id: '24h', label: '24 h' },
  { id: '7d', label: '7 d' },
]

export default function DEREv() {
  const [window, setWindow] = useState('24h')
  const [data, setData] = useState({ assets: [], aggregate: [], banner: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // EV tariff rate (R/kWh) — fetched from MDMS tariff schedule for the
  // 'ev_owner' class. NEVER falls back to a hardcoded number (was 8).
  const [evRate, setEvRate] = useState(null)
  const [evRateMissing, setEvRateMissing] = useState(false)

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

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await derAPI.telemetry({ type: 'ev', window })
      setData(data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load EV charger telemetry.')
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
    const totalKw = assets.reduce((s, a) => s + (a.current_output_kw ?? 0), 0)
    const totalCap = assets.reduce((s, a) => s + (a.capacity_kw ?? 0), 0)
    const active = assets.filter((a) => (a.state || '').toLowerCase() === 'charging').length
    const energy = (data.aggregate || []).reduce((s, p) => s + (p.total_kw ?? 0) / 60, 0)
    // Fees: only computable when MDMS has a tariff rate. Otherwise null —
    // UI renders 'Tariff rate not configured' rather than synthesizing R0.
    const fees = evRate != null ? energy * evRate : null
    return { totalKw, totalCap, active, energy, fees }
  }, [data, evRate])

  const hourlyOption = useMemo(() => {
    // Bucket the minute-level aggregate into per-hour kWh + fees for the chart.
    const buckets = new Map()
    for (const p of data.aggregate || []) {
      const d = new Date(p.ts)
      d.setMinutes(0, 0, 0)
      const k = d.toISOString()
      const prev = buckets.get(k) || { kwh: 0 }
      prev.kwh += (p.total_kw ?? 0) / 60
      buckets.set(k, prev)
    }
    const sorted = Array.from(buckets.entries()).sort()
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 52, top: 20, bottom: 40 },
      xAxis: {
        type: 'time',
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      },
      yAxis: [
        {
          type: 'value', name: 'kWh',
          nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
          axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
        },
        {
          type: 'value', name: 'R',
          position: 'right',
          nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
          axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: 'Energy',
          type: 'bar',
          data: sorted.map(([k, v]) => [k, Number(v.kwh.toFixed(2))]),
          itemStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: '#02C9A8' },
                { offset: 1, color: 'rgba(2,201,168,0.2)' },
              ],
            },
            borderRadius: [4, 4, 0, 0],
          },
          yAxisIndex: 0,
          barMaxWidth: 16,
        },
        // Fees series is only rendered when MDMS provides a tariff rate.
        ...(evRate != null
          ? [{
              name: 'Fees',
              type: 'line',
              data: sorted.map(([k, v]) => [k, Number((v.kwh * evRate).toFixed(2))]),
              yAxisIndex: 1,
              smooth: true,
              symbol: 'none',
              lineStyle: { color: '#F59E0B', width: 2 },
            }]
          : []),
      ],
      legend: {
        data: evRate != null ? ['Energy', 'Fees'] : ['Energy'],
        textStyle: { color: 'rgba(255,255,255,0.6)' }, top: 0,
      },
    }
  }, [data, evRate])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-ev-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>EV Charging — Fleet</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-18 · Pile status, active sessions, energy delivered, fees
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="glass-card p-1 flex gap-1">
            {WINDOWS.map((w) => (
              <button key={w.id} onClick={() => setWindow(w.id)}
                className="px-3 py-1.5 rounded-md font-semibold"
                style={{
                  fontSize: 12,
                  background: window === w.id ? 'rgba(2,201,168,0.15)' : 'transparent',
                  color: window === w.id ? '#02C9A8' : 'rgba(255,255,255,0.5)',
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
        <div className="glass-card p-3 flex items-center gap-3" data-testid="der-ev-banner"
          style={{ borderColor: 'rgba(2,201,168,0.3)', background: 'rgba(2,201,168,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#02C9A8' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{data.banner}</span>
        </div>
      )}

      {evRateMissing && (
        <div
          role="status"
          data-testid="ev-rate-banner"
          className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(245,158,11,0.35)', background: 'rgba(245,158,11,0.08)' }}
        >
          <Info size={15} style={{ color: '#F59E0B' }} />
          <span className="text-white/80" style={{ fontSize: 12 }}>
            Tariff rate not configured — fees not shown until MDMS returns a
            tariff for the EV owner class.
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="der-ev-kpis">
        <KPI icon={Activity} label="Active Sessions" value={fmt(totals.active, 0)} color="#02C9A8" />
        <KPI icon={Zap} label="Fleet Load" value={fmt(totals.totalKw, 1)} unit="kW" color="#F59E0B" />
        <KPI icon={TrendingUp} label="Energy Dispensed" value={fmt(totals.energy, 1)} unit="kWh" color="#56CCF2" />
        <KPI icon={PlugZap} label="Fees Collected"
          value={totals.fees == null ? '—' : `R ${fmt(totals.fees, 0)}`}
          color="#ABC7FF" />
      </div>

      <div className="glass-card p-5">
        <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>
          HOURLY ENERGY + FEES
        </div>
        <ReactECharts option={hourlyOption} style={{ height: 260 }} notMerge />
      </div>

      <div>
        <h2 className="text-white font-bold mb-3" style={{ fontSize: 15 }}>Per-Pile View</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="der-ev-grid">
          {(data.assets || []).map((a) => <EvCard key={a.id} asset={a} evRate={evRate} />)}
          {(data.assets || []).length === 0 && !loading && (
            <div className="glass-card p-6 text-center text-white/40" style={{ fontSize: 13 }}>
              No EV chargers registered.
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

function EvCard({ asset, evRate }) {
  const state = (asset.state || 'idle').toLowerCase()
  const badge = state === 'charging' ? 'badge-info' : state === 'online' ? 'badge-ok' : 'badge-low'
  const isCharging = state === 'charging'
  const sessEnergy = asset.session_energy_kwh
  const fee = (sessEnergy != null && evRate != null) ? sessEnergy * evRate : null
  return (
    <div className="glass-card p-4" data-testid="der-ev-card">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: 'rgba(2,201,168,0.2)' }}>
          <Car size={16} style={{ color: '#02C9A8' }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-white font-bold truncate" style={{ fontSize: 13 }}>{asset.name || asset.id}</div>
          <div className="text-white/40" style={{ fontSize: 11 }}>{asset.id}</div>
        </div>
        <span className={badge}>{state}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Current Load" value={`${fmt(asset.current_output_kw, 1)} kW`}
          color={isCharging ? '#02C9A8' : '#fff'} />
        <Field label="Rated" value={`${fmt(asset.capacity_kw, 0)} kW`} />
        <Field label="Session Energy" value={sessEnergy != null ? `${fmt(sessEnergy, 2)} kWh` : '—'} />
        <Field label="Session Fee" value={fee != null ? `R ${fmt(fee, 0)}` : '—'} color="#F59E0B" />
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
