import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

// Props:
//   title       — card heading
//   chartData   — { [seriesName]: { y-axis, type, data: [{label, value}] } }
//   xKey        — label field inside each data point (default "label")
//   colors      — series color palette
//
// This mirrors the avdhaan_v2 `prepareMixedChartDataMDMS` helper: each entry
// is a named series with its own type (bar/column/line) and optional
// secondary y-axis (`y-axis.opposite === true`).
const DEFAULT_COLORS = ['#02C9A8', '#56CCF2', '#0A3690', '#F59E0B', '#E94B4B', '#ABC7FF', '#7685E5', '#FFC32E']

export default function MixedChartCard({ title, chartData, colors = DEFAULT_COLORS, height = 380, emptyMessage = 'No chart data' }) {
  const option = useMemo(() => buildOption(chartData, colors), [chartData, colors])

  if (!option) {
    return (
      <div className="glass-card" style={{ padding: 20 }}>
        {title && <div className="text-white font-semibold mb-2" style={{ fontSize: 14 }}>{title}</div>}
        <div style={{ padding: 32, textAlign: 'center', color: '#ABC7FF' }}>{emptyMessage}</div>
      </div>
    )
  }

  return (
    <div className="glass-card" style={{ padding: 20 }}>
      {title && <div className="text-white font-semibold mb-2" style={{ fontSize: 14 }}>{title}</div>}
      <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />
    </div>
  )
}

function buildOption(chartData, colors) {
  if (!chartData || typeof chartData !== 'object') return null
  const series = Object.entries(chartData).filter(
    ([, v]) => v && Array.isArray(v.data) && v.data.length,
  )
  if (!series.length) return null

  // Determine x-axis labels from the first series (all series share the same
  // month/day labels in the mdms-analytics payload).
  const categories = Array.from(
    new Set(series.flatMap(([, s]) => s.data.map((d) => d.label))),
  )

  // Separate y-axes when any series has `y-axis.opposite: true` (Loss %,
  // SAIFI/CAIFI/MAIFI etc). ECharts wants an array of yAxis config.
  const hasOpposite = series.some(([, s]) => s['y-axis']?.opposite)
  const yAxis = hasOpposite
    ? [
        { type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { lineStyle: { color: '#ABC7FF11' } } },
        { type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { show: false }, position: 'right' },
      ]
    : [{ type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { lineStyle: { color: '#ABC7FF11' } } }]

  const seriesOption = series.map(([name, s], idx) => {
    const type = normalizeSeriesType(s.type)
    const valueByLabel = Object.fromEntries(s.data.map((d) => [d.label, Number(d.value) || 0]))
    const data = categories.map((c) => (c in valueByLabel ? valueByLabel[c] : null))
    return {
      name,
      type,
      data,
      yAxisIndex: hasOpposite && s['y-axis']?.opposite ? 1 : 0,
      smooth: type === 'line',
      symbol: 'circle',
      symbolSize: 5,
      barMaxWidth: 28,
      itemStyle: {
        color: colors[idx % colors.length],
        borderRadius: type === 'bar' ? [4, 4, 0, 0] : undefined,
      },
      lineStyle: type === 'line' ? { color: colors[idx % colors.length], width: 2 } : undefined,
      stack: s.stack || undefined,
    }
  })

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22',
      textStyle: { color: '#fff' }, axisPointer: { type: 'shadow' },
    },
    legend: {
      data: series.map(([n]) => n), textStyle: { color: '#ABC7FF' },
      bottom: 0, type: 'scroll',
    },
    grid: { top: 30, right: hasOpposite ? 60 : 30, left: 60, bottom: 40 },
    xAxis: {
      type: 'category', data: categories,
      axisLabel: { color: '#ABC7FF', fontSize: 10, rotate: categories.length > 10 ? 30 : 0 },
      axisLine: { lineStyle: { color: '#ABC7FF44' } },
    },
    yAxis,
    series: seriesOption,
  }
}

function normalizeSeriesType(t) {
  if (t === 'column') return 'bar'
  if (t === 'line' || t === 'bar') return t
  return 'bar'
}
