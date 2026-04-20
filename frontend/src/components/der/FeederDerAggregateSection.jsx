// Spec 018 W3.T12 — stacked per-type DER contribution per feeder.
// Feeder selector + stacked area chart of PV / BESS / EV / microgrid kW
// plus a reverse-flow banner if the backend reports one.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, GitMerge, RefreshCw } from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, metersAPI, reverseFlowAPI } from '@/services/api'

const TYPE_COLORS = {
  pv: '#F59E0B',
  bess: '#56CCF2',
  ev: '#02C9A8',
  microgrid: '#ABC7FF',
}

const WINDOWS = [
  { id: '1h', label: '1 h' },
  { id: '24h', label: '24 h' },
  { id: '7d', label: '7 d' },
]

export default function FeederDerAggregateSection() {
  const [feeders, setFeeders] = useState([])
  const [feederId, setFeederId] = useState(null)
  const [window, setWindow] = useState('24h')
  const [data, setData] = useState({ buckets: [], assets_by_type: {}, banner: null })
  const [reverseFlow, setReverseFlow] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Load feeder list once.
  useEffect(() => {
    metersAPI.feeders()
      .then((resp) => {
        setFeeders(resp.data || [])
        if ((resp.data || []).length && !feederId) {
          const first = resp.data[0]
          // feeder_id is string-typed in der_asset (sim id); fall back to numeric id.
          setFeederId(String(first.code || first.id))
        }
      })
      .catch((err) => setError(err?.response?.data?.detail ?? 'Failed to load feeders.'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load aggregate + reverse-flow when selection changes.
  const load = useCallback(async () => {
    if (!feederId) return
    setLoading(true); setError(null)
    try {
      const [{ data: agg }, { data: rf }] = await Promise.all([
        derAPI.feederAggregate(feederId, window),
        reverseFlowAPI.forFeeder(feederId).catch(() => ({ data: [] })),
      ])
      setData(agg)
      const open = (rf || []).find((e) => e.status === 'OPEN')
      setReverseFlow(open || null)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load feeder aggregate.')
    } finally {
      setLoading(false)
    }
  }, [feederId, window])

  useEffect(() => { load() }, [load])

  const option = useMemo(() => {
    const buckets = data.buckets || []
    const x = buckets.map((b) => b.ts)
    const mkSeries = (name, key, color) => ({
      name,
      type: 'line',
      stack: 'total',
      areaStyle: { color: `${color}55` },
      lineStyle: { color, width: 1 },
      symbol: 'none',
      data: buckets.map((b) => Number((b[key] ?? 0).toFixed(2))),
    })
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['PV', 'BESS', 'EV', 'Microgrid'],
        textStyle: { color: 'rgba(255,255,255,0.6)' },
        top: 0,
      },
      grid: { left: 48, right: 20, top: 32, bottom: 40 },
      xAxis: {
        type: 'category',
        data: x,
        axisLabel: {
          color: 'rgba(255,255,255,0.4)',
          fontSize: 10,
          formatter: (v) => v ? v.slice(11, 16) : '',
        },
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
        mkSeries('PV', 'pv_kw', TYPE_COLORS.pv),
        mkSeries('BESS', 'bess_kw', TYPE_COLORS.bess),
        mkSeries('EV', 'ev_kw', TYPE_COLORS.ev),
        mkSeries('Microgrid', 'microgrid_kw', TYPE_COLORS.microgrid),
      ],
    }
  }, [data])

  const assetsByType = data.assets_by_type || {}

  return (
    <div className="space-y-4" data-testid="der-feeder-aggregate">
      <div className="flex items-center gap-3 flex-wrap">
        <GitMerge size={16} style={{ color: '#ABC7FF' }} />
        <h2 className="text-white font-bold" style={{ fontSize: 15 }}>DER per Feeder</h2>
        <select
          value={feederId || ''}
          onChange={(e) => setFeederId(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-white outline-none"
          style={{ fontSize: 13 }}
        >
          {feeders.map((f) => (
            <option key={f.id} value={String(f.code || f.id)}>{f.name || f.code || f.id}</option>
          ))}
        </select>
        <div className="glass-card p-1 flex gap-1">
          {WINDOWS.map((w) => (
            <button key={w.id} onClick={() => setWindow(w.id)}
              className="px-3 py-1 rounded-md font-semibold"
              style={{
                fontSize: 12,
                background: window === w.id ? 'rgba(171,199,255,0.15)' : 'transparent',
                color: window === w.id ? '#ABC7FF' : 'rgba(255,255,255,0.5)',
              }}>{w.label}</button>
          ))}
        </div>
        <button onClick={load} disabled={loading}
          className="btn-secondary flex items-center gap-2 ml-auto"
          style={{ padding: '6px 12px', fontSize: 12 }}>
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {reverseFlow && (
        <div className="glass-card p-4 flex items-center gap-3 animate-slide-up"
          data-testid="der-feeder-reverse-flow-banner"
          style={{ borderColor: 'rgba(233,75,75,0.4)', background: 'rgba(233,75,75,0.10)' }}>
          <AlertTriangle size={20} style={{ color: '#E94B4B' }} />
          <div className="flex-1">
            <div className="text-white font-bold" style={{ fontSize: 14 }}>Reverse flow detected</div>
            <div className="text-white/70" style={{ fontSize: 12 }}>
              Feeder {reverseFlow.feeder_id} · net flow {reverseFlow.net_flow_kw?.toFixed?.(1) ?? '?'} kW
              · opened at {new Date(reverseFlow.detected_at).toLocaleTimeString('en-ZA')}
            </div>
          </div>
        </div>
      )}

      {data.banner && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.08)' }}>
          <AlertTriangle size={14} style={{ color: '#F59E0B' }} />
          <span className="text-white/80" style={{ fontSize: 12 }}>{data.banner}</span>
        </div>
      )}

      {error && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={14} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 12 }}>{error}</span>
        </div>
      )}

      <div className="glass-card p-4">
        <ReactECharts option={option} style={{ height: 240 }} notMerge />
        <div className="flex gap-4 mt-2 text-xs text-white/60">
          {Object.entries(assetsByType).map(([type, list]) => (
            <span key={type}>
              <span style={{ color: TYPE_COLORS[type] || '#ABC7FF' }}>■</span>
              <span className="ml-1">{type.toUpperCase()}: {list.length}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
