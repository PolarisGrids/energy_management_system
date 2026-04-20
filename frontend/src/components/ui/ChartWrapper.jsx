import ReactECharts from 'echarts-for-react'
import Skeleton from './Skeleton'
import EmptyState from './EmptyState'

/**
 * ChartWrapper — normalises loading / empty / error states around ECharts.
 */
export default function ChartWrapper({
  option,
  loading = false,
  empty = false,
  error = null,
  height = 260,
  ...rest
}) {
  if (loading) return <Skeleton height={height} />
  if (error) {
    return (
      <div className="flex items-center justify-center text-red-400 text-sm" style={{ height }}>
        Chart error: {String(error.message || error)}
      </div>
    )
  }
  if (empty || !option) {
    return (
      <div style={{ height }}>
        <EmptyState title="No data to plot" />
      </div>
    )
  }
  return <ReactECharts option={option} style={{ height }} {...rest} />
}
