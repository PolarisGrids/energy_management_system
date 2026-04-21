// EV charging fleet page — KPIs + energy/fees chart + searchable table + drill-down.
// Route: /der/ev
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity, AlertTriangle, Car, Info,
  PlugZap, RefreshCw, TrendingUp, Users, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI, mdmsAPI, metersAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'
import DERConsumerSearch from '@/components/der/DERConsumerSearch'
import DERConsumerFilters from '@/components/der/DERConsumerFilters'
import DERConsumerTable from '@/components/der/DERConsumerTable'

const PAGE_SIZE = 20
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

export default function DEREv() {
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({})
  const [page, setPage] = useState(1)

  const [data, setData] = useState({ assets: [], aggregate: [], total_assets: 0, banner: null })
  const [trend30d, setTrend30d] = useState({ aggregate: [] })
  const [feeders, setFeeders] = useState([])
  const [types, setTypes] = useState([])
  const [evRate, setEvRate] = useState(null)
  const [evRateMissing, setEvRateMissing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  // MDMS tariff rate for EV class — optional, never synthesized
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

  useEffect(() => {
    derAPI.types('ev').then((r) => setTypes(r.data || [])).catch(() => {})
    metersAPI.feeders().then((r) => setFeeders(r.data || [])).catch(() => {})
  }, [])

  const load30d = useCallback(() => {
    derAPI
      .telemetry({ type: 'ev', window: '30d', limit: 1 })
      .then((r) => setTrend30d({ aggregate: r.data?.aggregate || [] }))
      .catch(() => setTrend30d({ aggregate: [] }))
  }, [])
  useEffect(() => { load30d() }, [load30d])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { type: 'ev', window, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
      if (search) params.search = search
      if (filters.type_code) params.type_code = filters.type_code
      if (filters.feeder_id) params.feeder_id = filters.feeder_id
      if (filters.state) params.state = filters.state
      const { data: d } = await derAPI.telemetry(params)
      setData({
        assets: d.assets || [],
        aggregate: d.aggregate || [],
        total_assets: d.total_assets ?? 0,
        banner: d.banner ?? null,
      })
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load EV telemetry.')
    } finally {
      setLoading(false)
    }
  }, [window, page, search, filters])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => { setPage(1) }, [search, filters, window])

  const kpis = useMemo(() => {
    const assets = data.assets || []
    const totalKw = assets.reduce((s, a) => s + (a.current_output_kw ?? 0), 0)
    const totalCap = assets.reduce((s, a) => s + (a.capacity_kw ?? 0), 0)
    const activeCount = assets.filter((a) => (a.state || '').toLowerCase() === 'charging').length
    const energyKwh = (data.aggregate || []).reduce((s, p) => s + (p.total_kw ?? 0) / 60, 0)
    const fees = evRate != null ? energyKwh * evRate : null
    return { totalKw, totalCap, activeCount, energyKwh, fees, totalAssets: data.total_assets }
  }, [data, evRate])

  const hourlyChart = useMemo(() => buildHourlyChart(data.aggregate, evRate), [data, evRate])
  const daily30dChart = useMemo(() => buildDaily30dChart(trend30d.aggregate, evRate), [trend30d, evRate])

  const filterGroups = useMemo(() => [
    {
      key: 'type_code', label: 'Sub-type',
      options: types.map((t) => ({ value: t.code, label: t.display_name })),
    },
    {
      key: 'feeder_id', label: 'Feeder',
      options: (feeders || []).map((f) => ({
        value: String(f.id ?? f.feeder_id ?? f),
        label: f.name ?? String(f.id ?? f),
      })),
    },
    {
      key: 'state', label: 'Status',
      options: [
        { value: 'charging', label: 'Charging' },
        { value: 'online',   label: 'Online' },
        { value: 'idle',     label: 'Idle' },
        { value: 'offline',  label: 'Offline' },
      ],
    },
  ], [types, feeders])

  const columns = useMemo(() => [
    {
      key: 'consumer',
      label: 'Charger',
      render: (r) => (
        <div className="flex flex-col">
          <span className="text-white font-semibold" style={{ fontSize: 13 }}>
            {r.consumer?.name || r.name || r.id}
          </span>
          <span className="text-white/40 font-mono" style={{ fontSize: 11 }}>
            {r.consumer?.account_no || r.id}
          </span>
        </div>
      ),
    },
    {
      key: 'type_code',
      label: 'Sub-type',
      render: (r) => (
        <span style={{ fontSize: 12, color: '#ABC7FF' }}>
          {types.find((t) => t.code === r.type_code)?.display_name ?? '—'}
        </span>
      ),
    },
    {
      key: 'capacity_kw',
      label: 'Rated kW',
      align: 'right',
      render: (r) => (
        <span className="font-mono text-white/70" style={{ fontSize: 13 }}>
          {fmt(r.capacity_kw, 0)}
        </span>
      ),
    },
    {
      key: 'current_output_kw',
      label: 'Load kW',
      align: 'right',
      render: (r) => (
        <span className="font-mono" style={{ fontSize: 13, color: ACCENT }}>
          {fmt(r.current_output_kw, 1)}
        </span>
      ),
    },
    {
      key: 'session_energy_kwh',
      label: 'Session kWh',
      align: 'right',
      render: (r) => (
        <span className="font-mono text-white/60" style={{ fontSize: 13 }}>
          {r.session_energy_kwh == null ? '—' : fmt(r.session_energy_kwh, 2)}
        </span>
      ),
    },
    {
      key: 'session_fee',
      label: 'Session Fee',
      align: 'right',
      sortable: false,
      render: (r) => {
        const fee = (r.session_energy_kwh != null && evRate != null)
          ? r.session_energy_kwh * evRate : null
        return (
          <span className="font-mono" style={{ fontSize: 13, color: '#F59E0B' }}>
            {fee == null ? '—' : `R ${fmt(fee, 0)}`}
          </span>
        )
      },
    },
    {
      key: 'state',
      label: 'State',
      render: (r) => (
        <span className={stateClass(r.state)}>{r.state || 'unknown'}</span>
      ),
    },
    {
      key: 'feeder_id',
      label: 'Feeder',
      render: (r) => (
        <span className="text-white/50 font-mono" style={{ fontSize: 12 }}>
          {r.feeder_id ?? '—'}
        </span>
      ),
    },
    {
      key: 'last_ts',
      label: 'Last seen',
      sortable: false,
      render: (r) => (
        <span className="text-white/40" style={{ fontSize: 11 }}>
          {r.last_ts ? new Date(r.last_ts).toLocaleTimeString('en-ZA') : '—'}
        </span>
      ),
    },
  ], [types, evRate])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-ev-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>EV Charging — Fleet</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-18 — Fleet view → charger drill-down
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DERTimeRangePicker value={window} onChange={setWindow} accent={ACCENT} />
          <button onClick={load} disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {data.banner && <Banner color={ACCENT} message={data.banner} testid="der-ev-banner" />}
      {error && <Banner color="#E94B4B" message={error} />}
      {evRateMissing && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(245,158,11,0.35)', background: 'rgba(245,158,11,0.08)' }}>
          <Info size={15} style={{ color: '#F59E0B' }} />
          <span className="text-white/80" style={{ fontSize: 12 }}>
            EV tariff rate not configured — fees not shown until MDMS returns a rate for the EV owner class.
          </span>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4" data-testid="der-ev-kpis">
        <KPI icon={Activity} label="Active Sessions" value={fmt(kpis.activeCount, 0)} color={ACCENT} />
        <KPI icon={Zap} label="Fleet Load" value={fmt(kpis.totalKw, 1)} unit="kW" color="#F59E0B" />
        <KPI icon={TrendingUp} label="Energy Dispensed" value={fmt(kpis.energyKwh, 1)} unit="kWh" color="#56CCF2" />
        <KPI icon={PlugZap} label="Fees Collected"
          value={kpis.fees == null ? '—' : `R ${fmt(kpis.fees, 0)}`} color="#ABC7FF" />
        <KPI icon={Users} label="Total Chargers" value={fmt(kpis.totalAssets, 0)} color="#ABC7FF" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`HOURLY ENERGY + FEES — ${windowLabel(window)}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={hourlyChart} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="DAILY ENERGY — last 30 days">
          <ReactECharts option={daily30dChart} style={{ height: 260 }} notMerge />
        </ChartCard>
      </div>

      {/* Search + filters */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <DERConsumerSearch value={search} onChange={setSearch} />
          <DERConsumerFilters groups={filterGroups} value={filters} onChange={setFilters} />
        </div>
        <div className="text-white/40" style={{ fontSize: 12 }}>
          {kpis.totalAssets != null
            ? `${kpis.totalAssets} charger${kpis.totalAssets === 1 ? '' : 's'} match`
            : ''}
        </div>
      </div>

      {/* Charger table */}
      <DERConsumerTable
        columns={columns}
        rows={data.assets || []}
        onRowClick={(row) => navigate(`/der/ev/${encodeURIComponent(row.id)}`)}
        emptyLabel="No EV chargers match the current search / filters."
        totalCount={kpis.totalAssets ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}

// ── Presentational helpers ────────────────────────────────────────────────────

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

// ── ECharts builders ──────────────────────────────────────────────────────────

function windowLabel(w) {
  return w === '1h' ? 'last hour' : w === '24h' ? 'last 24 h' : w === '7d' ? 'last 7 days' : 'last 30 days'
}

function buildHourlyChart(aggregate, evRate) {
  const buckets = new Map()
  for (const p of aggregate || []) {
    const d = new Date(p.ts)
    d.setMinutes(0, 0, 0)
    const k = d.toISOString()
    const prev = buckets.get(k) || { kwh: 0 }
    prev.kwh += (p.total_kw ?? 0) / 60
    buckets.set(k, prev)
  }
  const sorted = [...buckets.entries()].sort()
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
      data: hasFees ? ['Energy', 'Fees'] : ['Energy'],
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 },
      top: 0, right: 0,
    },
    grid: { left: 48, right: hasFees ? 52 : 20, top: 28, bottom: 40 },
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
      ...(hasFees ? [{
        type: 'value', name: 'R', position: 'right',
        nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
        splitLine: { show: false },
      }] : []),
    ],
    series: [
      {
        name: 'Energy', type: 'bar', yAxisIndex: 0, barMaxWidth: 16,
        data: sorted.map(([k, v]) => [k, Number(v.kwh.toFixed(2))]),
        itemStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: '#02C9A8' }, { offset: 1, color: 'rgba(2,201,168,0.2)' }] },
          borderRadius: [4, 4, 0, 0],
        },
      },
      ...(hasFees ? [{
        name: 'Fees', type: 'line', yAxisIndex: 1,
        data: sorted.map(([k, v]) => [k, Number((v.kwh * evRate).toFixed(2))]),
        smooth: true, symbol: 'none',
        lineStyle: { color: '#F59E0B', width: 2 },
      }] : []),
    ],
  }
}

function buildDaily30dChart(aggregate, evRate) {
  const byDay = new Map()
  for (const p of aggregate || []) {
    const d = new Date(p.ts)
    if (Number.isNaN(d.valueOf())) continue
    const key = d.toISOString().slice(0, 10)
    byDay.set(key, (byDay.get(key) ?? 0) + Number(p.total_kw || 0))
  }
  const days = [...byDay.keys()].sort()
  const hasFees = evRate != null
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    grid: { left: 48, right: hasFees ? 52 : 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: days.map((d) => d.slice(5)),
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 'auto' },
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
        name: 'Energy', type: 'bar', yAxisIndex: 0, barMaxWidth: 14,
        data: days.map((d) => Number((byDay.get(d) ?? 0).toFixed(1))),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: '#02C9A8' }, { offset: 1, color: '#02C9A833' }] },
        },
      },
      ...(hasFees ? [{
        name: 'Fees', type: 'line', yAxisIndex: 1,
        data: days.map((d) => Number(((byDay.get(d) ?? 0) * evRate).toFixed(0))),
        smooth: true, symbol: 'none',
        lineStyle: { color: '#F59E0B', width: 2 },
      }] : []),
    ],
  }
}
