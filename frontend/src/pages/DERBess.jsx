// BESS fleet page — KPIs + charge/discharge charts + searchable table + drill-down.
// Route: /der/bess
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, Battery, Gauge, RefreshCw, TrendingUp,
  Users, Zap, Zap as ZapIcon,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI, metersAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'
import DERConsumerSearch from '@/components/der/DERConsumerSearch'
import DERConsumerFilters from '@/components/der/DERConsumerFilters'
import DERConsumerTable from '@/components/der/DERConsumerTable'

const PAGE_SIZE = 20
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

export default function DERBess() {
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({})
  const [page, setPage] = useState(1)

  const [data, setData] = useState({ assets: [], aggregate: [], total_assets: 0, banner: null })
  const [trend30d, setTrend30d] = useState({ aggregate: [] })
  const [feeders, setFeeders] = useState([])
  const [types, setTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  useEffect(() => {
    derAPI.types('bess').then((r) => setTypes(r.data || [])).catch(() => {})
    metersAPI.feeders().then((r) => setFeeders(r.data || [])).catch(() => {})
  }, [])

  const load30d = useCallback(() => {
    derAPI
      .telemetry({ type: 'bess', window: '30d', limit: 1 })
      .then((r) => setTrend30d({ aggregate: r.data?.aggregate || [] }))
      .catch(() => setTrend30d({ aggregate: [] }))
  }, [])
  useEffect(() => { load30d() }, [load30d])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { type: 'bess', window, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
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
      setError(err?.response?.data?.detail ?? 'Failed to load BESS telemetry.')
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
    const totalCapKwh = assets.reduce((s, a) => s + (a.capacity_kwh ?? 0), 0)
    const socVals = assets.map((a) => a.soc_pct).filter((v) => v != null)
    const avgSoc = socVals.length ? socVals.reduce((s, v) => s + v, 0) / socVals.length : null
    const charging = assets.filter((a) => (a.state || '').toLowerCase() === 'charging').length
    const discharging = assets.filter((a) => (a.state || '').toLowerCase() === 'discharging').length
    // Integrate aggregate power curve → kWh charged vs discharged
    let chargedKwh = 0
    let dischargedKwh = 0
    for (const p of data.aggregate || []) {
      const kwh = (p.total_kw || 0) / 60
      if (kwh < 0) chargedKwh += -kwh
      else dischargedKwh += kwh
    }
    return { totalCapKwh, avgSoc, charging, discharging, chargedKwh, dischargedKwh, totalAssets: data.total_assets }
  }, [data])

  const chargeChart = useMemo(() => buildChargeChart(data.aggregate), [data])
  const dailyChart = useMemo(() => buildDailyChart(trend30d.aggregate), [trend30d])

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
        { value: 'discharging', label: 'Discharging' },
        { value: 'idle', label: 'Idle' },
        { value: 'offline', label: 'Offline' },
      ],
    },
  ], [types, feeders])

  const columns = useMemo(() => [
    {
      key: 'consumer',
      label: 'Asset',
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
      key: 'capacity_kwh',
      label: 'Capacity kWh',
      align: 'right',
      render: (r) => (
        <span className="font-mono text-white/70" style={{ fontSize: 13 }}>
          {fmt(r.capacity_kwh, 0)}
        </span>
      ),
    },
    {
      key: 'soc_pct',
      label: 'SoC %',
      align: 'right',
      render: (r) => (
        <div className="flex flex-col items-end gap-1">
          <span className="font-mono" style={{ fontSize: 13, color: socColor(r.soc_pct) }}>
            {r.soc_pct == null ? '—' : `${fmt(r.soc_pct, 1)}%`}
          </span>
          {r.soc_pct != null && (
            <div style={{ width: 48, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
              <div style={{
                width: `${Math.min(r.soc_pct, 100)}%`, height: '100%',
                borderRadius: 2, background: socColor(r.soc_pct),
              }} />
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'current_output_kw',
      label: 'Power kW',
      align: 'right',
      render: (r) => {
        const v = r.current_output_kw
        const positive = v != null && v >= 0
        return (
          <span className="font-mono" style={{ fontSize: 13, color: positive ? '#02C9A8' : '#56CCF2' }}>
            {v == null ? '—' : `${v >= 0 ? '+' : ''}${fmt(v, 1)}`}
          </span>
        )
      },
    },
    {
      key: 'session_energy_kwh',
      label: 'Session kWh',
      align: 'right',
      render: (r) => (
        <span className="font-mono text-white/60" style={{ fontSize: 13 }}>
          {r.session_energy_kwh == null ? '—' : fmt(r.session_energy_kwh, 1)}
        </span>
      ),
    },
    {
      key: 'state',
      label: 'State',
      render: (r) => (
        <span className={stateClass(r.state)}>
          {r.state || 'unknown'}
        </span>
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
  ], [types])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-bess-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>BESS — Battery Storage Fleet</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-19 — Fleet view → asset drill-down
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

      {data.banner && <Banner color={ACCENT} message={data.banner} testid="der-bess-banner" />}
      {error && <Banner color="#E94B4B" message={error} />}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4" data-testid="der-bess-kpis">
        <KPI icon={Gauge} label="Avg SoC"
          value={kpis.avgSoc == null ? '—' : fmt(kpis.avgSoc, 1)}
          unit={kpis.avgSoc == null ? '' : '%'}
          color={socColor(kpis.avgSoc)} />
        <KPI icon={Battery} label="Fleet Capacity" value={fmt(kpis.totalCapKwh, 0)} unit="kWh" color={ACCENT} />
        <KPI icon={TrendingUp} label="Discharged" value={fmt(kpis.dischargedKwh, 1)} unit="kWh" color="#02C9A8" />
        <KPI icon={Zap} label="Charged" value={fmt(kpis.chargedKwh, 1)} unit="kWh" color="#ABC7FF" />
        <KPI icon={ZapIcon} label="Discharging Now"
          value={`${kpis.discharging}/${(data.assets || []).length}`} color="#02C9A8" />
        <KPI icon={Users} label="Total Assets" value={fmt(kpis.totalAssets, 0)} color="#ABC7FF" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`CHARGE / DISCHARGE — ${windowLabel(window)}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={chargeChart} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="DAILY NET ENERGY — last 30 days" subtitle="discharge − charge per day">
          <ReactECharts option={dailyChart} style={{ height: 260 }} notMerge />
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
            ? `${kpis.totalAssets} asset${kpis.totalAssets === 1 ? '' : 's'} match`
            : ''}
        </div>
      </div>

      {/* Asset table */}
      <DERConsumerTable
        columns={columns}
        rows={data.assets || []}
        onRowClick={(row) => navigate(`/der/bess/${encodeURIComponent(row.id)}`)}
        emptyLabel="No BESS assets match the current search / filters."
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

function buildChargeChart(aggregate) {
  const points = (aggregate || []).map((p) => ({
    ts: p.ts,
    charge: p.total_kw < 0 ? -p.total_kw : 0,
    discharge: p.total_kw > 0 ? p.total_kw : 0,
  }))
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
        type: 'bar',
        data: points.map((p) => [p.ts, p.charge]),
        barMaxWidth: 8,
        itemStyle: { color: 'rgba(86,204,242,0.75)', borderRadius: [2, 2, 0, 0] },
        stack: 'flow',
      },
      {
        name: 'Discharge',
        type: 'bar',
        data: points.map((p) => [p.ts, p.discharge]),
        barMaxWidth: 8,
        itemStyle: { color: 'rgba(2,201,168,0.75)', borderRadius: [2, 2, 0, 0] },
        stack: 'flow',
      },
    ],
  }
}

function buildDailyChart(aggregate) {
  const byDay = new Map()
  for (const p of aggregate || []) {
    const d = new Date(p.ts)
    if (Number.isNaN(d.valueOf())) continue
    const key = d.toISOString().slice(0, 10)
    byDay.set(key, (byDay.get(key) ?? 0) + Number(p.total_kw || 0))
  }
  const days = [...byDay.keys()].sort()
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (p) => `${p[0].name}<br/>${Number(p[0].value).toFixed(1)} kWh net`,
    },
    grid: { left: 48, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: days.map((d) => d.slice(5)),
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 'auto' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', name: 'kWh',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [{
      type: 'bar',
      data: days.map((d) => Number((byDay.get(d) ?? 0).toFixed(1))),
      barMaxWidth: 14,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: (p) => p.value >= 0
          ? { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#02C9A8' }, { offset: 1, color: '#02C9A833' }] }
          : { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#56CCF2' }, { offset: 1, color: '#56CCF233' }] },
      },
    }],
  }
}
