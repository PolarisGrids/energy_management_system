import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Activity, RefreshCw, ListChecks, AlertOctagon } from 'lucide-react'
import HierarchyFilter from '@/components/filters/HierarchyFilter'
import MonthRangeFilter from '@/components/filters/MonthRangeFilter'
import MixedChartCard from '@/components/reports/MixedChartCard'
import ReportDataTable from '@/components/reports/ReportDataTable'
import ReportDownloadButton from '@/components/reports/ReportDownloadButton'
import { reliabilityIndicesAPI } from '@/services/api'

// Reliability Indices — ported from avdhaan_v2 `reports/reliability-indices`.
// Monthly SAIDI/SAIFI/CAIDI/CAIFI/MAIFI chart + feeder-level summary + per-
// outage drill-down. Backed by /api/v1/egsm-reports/reliability-indices/*.
export default function ReliabilityIndices() {
  const { search } = useLocation()
  const params = useSearchObject(search)

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <PageHeader />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 20 }}>
        <HierarchyFilter />
        <MonthRangeFilter showConsumerType />

        <ChartSection params={params} />
        <FeederLevelSection params={params} />
        <PowerOutagesSection params={params} />
      </div>
    </div>
  )
}

function PageHeader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10, background: '#02C9A822',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Activity size={18} color="#02C9A8" />
      </div>
      <div>
        <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>Reliability Indices</h1>
        <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>
          SAIDI · SAIFI · CAIDI · CAIFI · MAIFI · Feeder-level summary · Power outages
        </p>
      </div>
    </div>
  )
}

function ChartSection({ params }) {
  const { data, loading, error, refetch } = useEgsmQuery(reliabilityIndicesAPI.stats, params)
  const records = data?.data?.records || []
  const chartData = records[0]
  const reportName = data?.data?.reportName || 'RELIABILITY_INDICES_STATS'

  return (
    <section>
      <SectionHeader
        title="Monthly Reliability Indices"
        subtitle="SAIDI / CAIDI on left axis · SAIFI / CAIFI / MAIFI on right"
        reportName={reportName}
        onRefresh={refetch}
        loading={loading}
        error={error}
      />
      <MixedChartCard chartData={chartData} height={420} />
    </section>
  )
}

function FeederLevelSection({ params }) {
  const { data, loading, error, refetch } = useEgsmQuery(reliabilityIndicesAPI.feederLevel, params)
  const columns = data?.data?.columns || []
  const records = data?.data?.records || []
  const reportName = data?.data?.reportName

  return (
    <section>
      <SectionHeader
        icon={ListChecks}
        title="Feeder Reliability Indices Summary"
        subtitle="One row per feeder, indices aggregated over selected window"
        reportName={reportName}
        onRefresh={refetch}
        loading={loading}
        error={error}
        recordCount={records.length}
      />
      <ReportDataTable
        columns={columns}
        records={records}
        emptyMessage={loading ? 'Loading…' : 'No feeders matched the selected filters'}
      />
    </section>
  )
}

function PowerOutagesSection({ params }) {
  const { data, loading, error, refetch } = useEgsmQuery(reliabilityIndicesAPI.summary, params)
  const columns = data?.data?.columns || []
  const records = data?.data?.records || []
  const reportName = data?.data?.reportName

  return (
    <section>
      <SectionHeader
        icon={AlertOctagon}
        title="Power Outages"
        subtitle="Per-outage detail with accounting flags and duration"
        reportName={reportName}
        onRefresh={refetch}
        loading={loading}
        error={error}
        recordCount={records.length}
      />
      <ReportDataTable
        columns={columns}
        records={records}
        emptyMessage={loading ? 'Loading…' : 'No outages in the selected window'}
      />
    </section>
  )
}

function SectionHeader({ icon: Icon, title, subtitle, reportName, onRefresh, loading, error, recordCount }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        {Icon && <Icon size={18} color="#ABC7FF" />}
        <div>
          <div className="text-white font-semibold" style={{ fontSize: 15 }}>{title}</div>
          {subtitle && (
            <div style={{ color: '#ABC7FF', fontSize: 11 }}>
              {subtitle}
              {recordCount !== undefined && !loading && !error ? ` · ${recordCount} row${recordCount === 1 ? '' : 's'}` : ''}
            </div>
          )}
          {error && <div style={{ color: '#E94B4B', fontSize: 11, marginTop: 2 }}>{error}</div>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {reportName && <ReportDownloadButton reportName={reportName} />}
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="btn-secondary"
          style={{ padding: '6px 10px', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : undefined} />
          {loading ? 'Loading' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}

function useEgsmQuery(fetcher, params) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const paramsKey = JSON.stringify(params)
  const run = useCallback(async () => {
    if (!params.from || !params.to) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetcher(params)
      setData(res.data)
    } catch (err) {
      const msg = err?.response?.data?.detail?.error?.message
        || err?.response?.data?.detail
        || err?.message
        || 'Request failed'
      setError(typeof msg === 'string' ? msg : 'Request failed')
      setData(null)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, paramsKey])

  useEffect(() => { run() }, [run])
  return { data, loading, error, refetch: run }
}

function useSearchObject(search) {
  return useMemo(() => {
    const p = new URLSearchParams(search)
    const out = {}
    for (const key of new Set(p.keys())) {
      const vals = p.getAll(key)
      out[key] = vals.length > 1 ? vals : vals[0]
    }
    return out
  }, [search])
}
