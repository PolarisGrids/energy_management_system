// W5 — PV Solar fleet page (rewritten).
//
// Pattern: aggregate KPIs → trend charts → searchable/sortable consumer list
// → drill-down into /der/pv/:assetId for the per-consumer detail view.
//
// Backed by /api/v1/der/telemetry (extended in W5 with search, filter, type_code,
// 30d window, consumer summary inlined per asset, and total_assets for paging).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle, Cpu, Gauge, RefreshCw,
  TrendingUp, Users, Wifi, WifiOff, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI, metersAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'
import DERConsumerSearch from '@/components/der/DERConsumerSearch'
import DERConsumerFilters from '@/components/der/DERConsumerFilters'
import DERConsumerTable from '@/components/der/DERConsumerTable'

const PAGE_SIZE = 20
const POLL_MS = 30_000

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

// Achievement → traffic-light colour for the column cell.
const achColor = (v) =>
  v == null ? '#ABC7FF' : v >= 80 ? '#02C9A8' : v >= 60 ? '#F59E0B' : '#E94B4B'

// Inverter equipment status → badge class + colour.
const invStatusMeta = (s) => {
  switch ((s || '').toLowerCase()) {
    case 'online':        return { cls: 'badge-ok',       color: '#02C9A8' }
    case 'fault':         return { cls: 'badge-critical',  color: '#E94B4B' }
    case 'maintenance':   return { cls: 'badge-medium',    color: '#F59E0B' }
    case 'commissioning': return { cls: 'badge-info',      color: '#56CCF2' }
    case 'offline':       return { cls: 'badge-low',       color: '#6B7280' }
    default:              return { cls: 'badge-low',       color: '#6B7280' }
  }
}

export default function DERPv() {
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

  // ── One-shot dimension loads (filter options) ─────────────────────────
  useEffect(() => {
    derAPI.types('pv').then((r) => setTypes(r.data || [])).catch(() => {})
    metersAPI.feeders().then((r) => setFeeders(r.data || [])).catch(() => {})
  }, [])

  // ── 30-day trend (loaded once on mount, refreshed on window-30d only) ─
  const load30d = useCallback(() => {
    derAPI
      .telemetry({ type: 'pv', window: '30d', limit: 1 })
      .then((r) => setTrend30d({ aggregate: r.data?.aggregate || [] }))
      .catch(() => setTrend30d({ aggregate: [] }))
  }, [])
  useEffect(() => {
    load30d()
  }, [load30d])

  // ── Live page data (KPIs + selected window aggregate + paginated list) ─
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = {
        type: 'pv',
        window,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }
      if (search) params.search = search
      if (filters.type_code) params.type_code = filters.type_code
      if (filters.feeder_id) params.feeder_id = filters.feeder_id
      if (filters.state) params.state = filters.state
      const { data } = await derAPI.telemetry(params)
      setData({
        assets: data.assets || [],
        aggregate: data.aggregate || [],
        total_assets: data.total_assets ?? 0,
        banner: data.banner ?? null,
      })
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load PV telemetry.')
    } finally {
      setLoading(false)
    }
  }, [window, page, search, filters])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  // Reset to page 1 when search / filters change.
  useEffect(() => {
    setPage(1)
  }, [search, filters, window])

  // ── Fleet KPIs (derived from current page; in v2 we'd have a dedicated
  // /der/fleet/summary endpoint that aggregates server-side regardless of
  // the visible page). ───────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const assets = data.assets || []
    const totalCap = assets.reduce((s, a) => s + (a.capacity_kw ?? 0), 0)
    const totalOut = assets.reduce((s, a) => s + (a.current_output_kw ?? 0), 0)
    const onlineCount = assets.filter((a) => a.inverter_online === true).length
    const achVals = assets.map((a) => a.achievement_rate_pct).filter((v) => v != null)
    const avgAchievement = achVals.length
      ? achVals.reduce((s, v) => s + v, 0) / achVals.length
      : null
    const aggKwh = (data.aggregate || []).reduce((s, p) => s + (p.total_kw ?? 0), 0)
    const generationToday = aggKwh / 60 // 1-min buckets → kWh
    return {
      totalOut, totalCap, onlineCount, avgAchievement,
      generationToday, totalConsumers: data.total_assets,
    }
  }, [data])

  // ── Charts ────────────────────────────────────────────────────────────
  const chart24h = useMemo(() => buildBellChart(data.aggregate, '#F59E0B'), [data])
  const chart30d = useMemo(() => buildDailyBars(trend30d.aggregate, '#F97316'), [trend30d])

  // ── Filter option groups (consumer list) ──────────────────────────────
  const filterGroups = useMemo(
    () => [
      {
        key: 'type_code',
        label: 'Sub-type',
        options: types.map((t) => ({ value: t.code, label: t.display_name })),
      },
      {
        key: 'feeder_id',
        label: 'Feeder',
        options: (feeders || []).map((f) => ({
          value: String(f.id ?? f.feeder_id ?? f),
          label: f.name ?? String(f.id ?? f),
        })),
      },
      {
        key: 'state',
        label: 'Status',
        options: [
          { value: 'online', label: 'Online' },
          { value: 'offline', label: 'Offline' },
          { value: 'curtailed', label: 'Curtailed' },
        ],
      },
    ],
    [types, feeders],
  )

  // ── Table column definition ───────────────────────────────────────────
  const columns = useMemo(
    () => [
      {
        key: 'consumer',
        label: 'Consumer',
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
        label: 'Output kW',
        align: 'right',
        render: (r) => (
          <span className="font-mono" style={{ fontSize: 13, color: '#F59E0B' }}>
            {fmt(r.current_output_kw, 1)}
          </span>
        ),
      },
      {
        key: 'achievement_rate_pct',
        label: 'Achievement',
        align: 'right',
        render: (r) => (
          <span
            className="font-mono"
            style={{ fontSize: 13, color: achColor(r.achievement_rate_pct) }}
          >
            {r.achievement_rate_pct == null ? '—' : `${fmt(r.achievement_rate_pct, 1)}%`}
          </span>
        ),
      },
      {
        key: 'state',
        label: 'Status',
        render: (r) => {
          const online = r.inverter_online === true
          return (
            <span className={online ? 'badge-ok' : r.state ? 'badge-medium' : 'badge-low'}>
              {online ? <Wifi size={10} /> : <WifiOff size={10} />}
              <span className="ml-1">{r.state || 'unknown'}</span>
            </span>
          )
        },
      },
      {
        key: 'inverter_status',
        label: 'Inverter',
        render: (r) => {
          if (!r.inverter_status) {
            return <span className="text-white/25 font-mono" style={{ fontSize: 11 }}>—</span>
          }
          const { cls } = invStatusMeta(r.inverter_status)
          return (
            <span className={cls}>
              <Cpu size={10} />
              <span className="ml-1">{r.inverter_status}</span>
            </span>
          )
        },
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
    ],
    [types],
  )

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-pv-page">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>
            PV Solar — Fleet
          </h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-17 — Fleet view → consumer drill-down
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DERTimeRangePicker value={window} onChange={setWindow} accent="#F59E0B" />
          <button
            onClick={load}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {data.banner && (
        <Banner color="#F59E0B" message={data.banner} testid="der-pv-banner" />
      )}
      {error && <Banner color="#E94B4B" message={error} />}

      {/* ── Section 1: Fleet KPIs ───────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4" data-testid="der-pv-kpis">
        <KPI
          icon={Zap} label="Current Output"
          value={fmt(kpis.totalOut, 1)} unit="kW" color="#F59E0B"
        />
        <KPI
          icon={Gauge} label="Installed Capacity"
          value={fmt(kpis.totalCap, 0)} unit="kW" color="#F97316"
        />
        <KPI
          icon={TrendingUp} label="Generation (window)"
          value={fmt(kpis.generationToday, 0)} unit="kWh" color="#02C9A8"
        />
        <KPI
          icon={CheckCircle} label="Avg Achievement"
          value={kpis.avgAchievement == null ? '—' : fmt(kpis.avgAchievement, 1)}
          unit={kpis.avgAchievement == null ? '' : '%'}
          color={achColor(kpis.avgAchievement)}
        />
        <KPI
          icon={Wifi} label="Online Inverters"
          value={`${kpis.onlineCount}/${(data.assets || []).length}`}
          color="#56CCF2"
        />
        <KPI
          icon={Users} label="Total Consumers"
          value={fmt(kpis.totalConsumers, 0)} color="#ABC7FF"
        />
      </div>

      {/* ── Section 2: Trend charts ─────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`AGGREGATE GENERATION — ${window === '1h' ? 'last hour' : window === '24h' ? 'last 24 h' : window === '7d' ? 'last 7 days' : 'last 30 days'}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={chart24h} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="DAILY GENERATION — last 30 days" subtitle="hourly buckets summed per day">
          <ReactECharts option={chart30d} style={{ height: 260 }} notMerge />
        </ChartCard>
      </div>

      {/* ── Section 3: Search + filters ─────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <DERConsumerSearch value={search} onChange={setSearch} />
          <DERConsumerFilters groups={filterGroups} value={filters} onChange={setFilters} />
        </div>
        <div className="text-white/40" style={{ fontSize: 12 }}>
          {kpis.totalConsumers != null
            ? `${kpis.totalConsumers} consumer${kpis.totalConsumers === 1 ? '' : 's'} match`
            : ''}
        </div>
      </div>

      {/* ── Section 4: Consumer table ───────────────────────────────── */}
      <DERConsumerTable
        columns={columns}
        rows={data.assets || []}
        onRowClick={(row) => navigate(`/der/pv/${encodeURIComponent(row.id)}`)}
        emptyLabel="No PV consumers match the current search / filters."
        totalCount={kpis.totalConsumers ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}

// ── Reusable presentational helpers ─────────────────────────────────────────

function KPI({ icon: Icon, label, value, unit, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}
      >
        <Icon size={18} style={{ color }} />
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 24 }}>
          {value}
          {unit && (
            <span className="text-white/40 font-medium ml-1" style={{ fontSize: 13 }}>
              {unit}
            </span>
          )}
        </div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>
          {label}
        </div>
      </div>
    </div>
  )
}

function Banner({ message, color, testid }) {
  return (
    <div
      className="glass-card p-3 flex items-center gap-3"
      data-testid={testid}
      style={{
        borderColor: `${color}4D`,
        background: `${color}14`,
      }}
    >
      <AlertTriangle size={16} style={{ color }} />
      <span className="text-white/80" style={{ fontSize: 13 }}>
        {message}
      </span>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="text-white/60 font-bold" style={{ fontSize: 12 }}>
          {title}
        </div>
        {subtitle && (
          <div className="text-white/30" style={{ fontSize: 11 }}>
            {subtitle}
          </div>
        )}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  )
}

// ── ECharts option builders ─────────────────────────────────────────────────

function buildBellChart(aggregate, accent = '#F59E0B') {
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
      type: 'value',
      name: 'kW',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        type: 'line',
        data: points,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: accent, width: 2 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: accent + '66' },
              { offset: 1, color: accent + '0A' },
            ],
          },
        },
      },
    ],
  }
}

function buildDailyBars(aggregate, accent = '#F97316') {
  // Sum hourly buckets into daily totals (kWh ≈ Σ kW × hour).
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
      formatter: (p) => `${p[0].name}<br/>${Number(p[0].value).toFixed(1)} kWh`,
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
      type: 'value',
      name: 'kWh',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        type: 'bar',
        data: days.map((d) => Number((byDay.get(d) ?? 0).toFixed(1))),
        barMaxWidth: 14,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: accent },
              { offset: 1, color: accent + '33' },
            ],
          },
        },
      },
    ],
  }
}
