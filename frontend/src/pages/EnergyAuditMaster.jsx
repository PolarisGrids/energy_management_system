import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { BarChart2, RefreshCw, AlertTriangle, TrendingDown, TrendingUp, ListChecks } from 'lucide-react'
import HierarchyFilter from '@/components/filters/HierarchyFilter'
import MonthRangeFilter from '@/components/filters/MonthRangeFilter'
import MixedChartCard from '@/components/reports/MixedChartCard'
import ReportDataTable from '@/components/reports/ReportDataTable'
import ReportDownloadButton from '@/components/reports/ReportDownloadButton'
import { energyAuditAPI } from '@/services/api'

// Energy Audit Master — ported from avdhaan_v2 `reports/energy-audit-master`.
// Each section mirrors one endpoint under /api/v1/egsm-reports/energy-audit/*.
export default function EnergyAuditMaster() {
  const { search } = useLocation()
  const params = useSearchObject(search)

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <PageHeader />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 20 }}>
        <HierarchyFilter />
        <MonthRangeFilter />

        <MonthlyEnergyAuditSection params={params} />
        <FeederListSection
          icon={TrendingUp}
          title="Top Performing Feeders"
          subtitle="Lowest loss % — best performers"
          fetcher={energyAuditAPI.topFeeders}
          params={params}
        />
        <FeederListSection
          icon={TrendingDown}
          title="Worst Performing Feeders"
          subtitle="Highest loss % — investigation priority"
          fetcher={energyAuditAPI.worstFeeders}
          params={params}
        />
        <FeederListSection
          icon={AlertTriangle}
          title="Anomaly Feeders"
          subtitle="Zero / negative consumption or negative loss"
          fetcher={energyAuditAPI.anomalyFeeders}
          params={params}
        />
        <FeederListSection
          icon={ListChecks}
          title="All Feeders"
          subtitle="Full feeder-level energy audit — within selected window"
          fetcher={energyAuditAPI.allFeeders}
          params={params}
        />
      </div>
    </div>
  )
}

function PageHeader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10, background: '#ABC7FF22',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <BarChart2 size={18} color="#ABC7FF" />
      </div>
      <div>
        <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>Energy Audit Master</h1>
        <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>
          Feeder ↔ DT ↔ consumer loss audit · Monthly chart · Top / Worst / Anomaly / All feeder views
        </p>
      </div>
    </div>
  )
}

function MonthlyEnergyAuditSection({ params }) {
  const { data, loading, error, refetch } = useEgsmQuery(energyAuditAPI.monthlyConsumption, params)
  const reportName = data?.data?.reportName
  const records = data?.data?.records || []
  const chartData = records[0]

  return (
    <section>
      <SectionHeader
        title="Monthly Energy Audit"
        subtitle="Feeder / DTR / Consumer consumption with loss %"
        reportName={reportName}
        onRefresh={refetch}
        loading={loading}
        error={error}
      />
      <MixedChartCard title="" chartData={chartData} height={420} />
    </section>
  )
}

function FeederListSection({ icon: Icon, title, subtitle, fetcher, params }) {
  const { data, loading, error, refetch } = useEgsmQuery(fetcher, params)
  const columns = data?.data?.columns || []
  const records = data?.data?.records || []
  const reportName = data?.data?.reportName

  return (
    <section>
      <SectionHeader
        icon={Icon}
        title={title}
        subtitle={subtitle}
        reportName={reportName}
        onRefresh={refetch}
        loading={loading}
        error={error}
        recordCount={records.length}
      />
      <ReportDataTable columns={columns} records={records} emptyMessage={loading ? 'Loading…' : 'No records for selected filters'} />
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

// Shared query hook — rerun when the URL query string (hierarchy + date
// range filters) changes. Returns {data, loading, error, refetch}.
function useEgsmQuery(fetcher, params) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const paramsKey = JSON.stringify(params)
  const run = useCallback(async () => {
    if (!params.from || !params.to) return // wait for defaults to seed
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

// Parse `location.search` into a flat object, preserving multi-value keys
// (e.g. zone=A&zone=B → {zone: ['A','B']}) — axios serializes arrays as
// repeated params by default, which is what mdms-analytics expects.
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
