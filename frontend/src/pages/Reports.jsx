import { useState, useMemo, useEffect, useCallback } from 'react'
import {
  BarChart2, FileText, ClipboardList, Download,
  Search, RefreshCw, TrendingUp, Zap, Calendar, PlayCircle, Clock,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { reportsAPI, egsmReportsAPI, scheduledReportsAPI, devicesAPI, mdmsAPI } from '@/services/api'
import { DateRangePicker, defaultRange } from '@/components/ui'

// ─── helpers ─────────────────────────────────────────────────────────────────
const fmt = (n) => (n ?? 0).toLocaleString()

const TABS = [
  'Consumption Reports',
  'Meter Reading Reports',
  'Audit Statements',
  'EGSM (MDMS)',
  'Scheduled',
]

// Only the "All" sentinel is a literal — real options are fetched from
// devicesAPI.hierarchy / mdmsAPI.tariffs. Never hardcode specific
// feeder/tariff names here.
const ALL_FEEDERS = 'All Feeders'
const ALL_CLASSES = 'All Classes'
const REPORT_TYPES = ['Daily', 'Monthly']

// Hook: fetch feeder list from CIS hierarchy (never hardcoded).
function useFeederOptions() {
  const [opts, setOpts] = useState([ALL_FEEDERS])
  useEffect(() => {
    devicesAPI.hierarchy({ level: 'feeder' })
      .then((res) => {
        const rows = Array.isArray(res.data) ? res.data : res.data?.data || []
        const names = rows.map((r) => r.name || r.label || r.id).filter(Boolean)
        setOpts([ALL_FEEDERS, ...names])
      })
      .catch(() => setOpts([ALL_FEEDERS])) // empty — do NOT fall back to hardcoded list
  }, [])
  return opts
}

// Hook: fetch tariff-class list from MDMS (never hardcoded).
function useTariffClassOptions() {
  const [opts, setOpts] = useState([ALL_CLASSES])
  useEffect(() => {
    mdmsAPI.tariffs()
      .then((res) => {
        const rows = Array.isArray(res.data) ? res.data : res.data?.tariffs || res.data?.data || []
        const names = Array.from(
          new Set(rows.map((r) => r.class || r.tariff_class || r.name).filter(Boolean))
        )
        setOpts([ALL_CLASSES, ...names])
      })
      .catch(() => setOpts([ALL_CLASSES])) // empty — do NOT fall back
  }, [])
  return opts
}

// ─── KPI card ─────────────────────────────────────────────────────────────────
const KPI = ({ icon: Icon, label, value, color = '#02C9A8' }) => (
  <div className="metric-card">
    <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}22`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
      <Icon size={17} style={{ color }} />
    </div>
    <div className="text-white font-black" style={{ fontSize: 22 }}>{value}</div>
    <div className="text-white/50 font-medium" style={{ fontSize: 12 }}>{label}</div>
  </div>
)

// ─── Filter row helper ────────────────────────────────────────────────────────
const FilterSelect = ({ value, onChange, options, style }) => (
  <select value={value} onChange={(e) => onChange(e.target.value)}
    style={{ padding: '8px 12px', background: '#0A1628', border: '1px solid #ABC7FF22',
      borderRadius: 8, color: '#fff', fontSize: 13, cursor: 'pointer', ...style }}>
    {options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>
)

const DateInput = ({ value, onChange, label }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
    <label style={{ color: '#ABC7FF', fontSize: 11 }}>{label}</label>
    <input type="date" value={value} onChange={(e) => onChange(e.target.value)}
      style={{ padding: '7px 10px', background: '#0A1628', border: '1px solid #ABC7FF22',
        borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none', colorScheme: 'dark' }} />
  </div>
)

// ─── CSV export helper ────────────────────────────────────────────────────────
const exportCSV = (rows, filename) => {
  if (!rows?.length) return
  const keys = Object.keys(rows[0])
  const csv = [keys.join(','), ...rows.map((r) => keys.map((k) => r[k]).join(','))].join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ─── Consumption Reports ──────────────────────────────────────────────────────
function ConsumptionReports() {
  const [range,    setRange]    = useState(defaultRange('30d'))
  const feeders    = useFeederOptions()
  const classes    = useTariffClassOptions()
  const [feeder,   setFeeder]   = useState(ALL_FEEDERS)
  const [rtype,    setRtype]    = useState('Daily')
  const [cclass,   setCclass]   = useState(ALL_CLASSES)
  const [rows,     setRows]     = useState(null)
  const [loading,  setLoading]  = useState(false)

  const handleGenerate = async () => {
    setLoading(true)
    try {
      const res = await reportsAPI.consumption({ from_date: range.from, to_date: range.to })
      setRows(res.data.rows)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const barOption = useMemo(() => {
    if (!rows) return null
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22',
        axisPointer: { type: 'shadow' } },
      legend: { data: ['Import kWh','Export kWh'], textStyle: { color: '#ABC7FF' }, bottom: 0 },
      xAxis: { type: 'category', data: rows.map((r) => r.date),
        axisLabel: { color: '#ABC7FF', fontSize: 10, rotate: rows.length > 14 ? 45 : 0 },
        axisLine: { lineStyle: { color: '#ABC7FF44' } } },
      yAxis: { type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { lineStyle: { color: '#ABC7FF11' } } },
      series: [
        { name:'Import kWh', type:'bar', data: rows.map((r) => r.import), barMaxWidth: 28,
          itemStyle: { color: '#02C9A8', borderRadius: [4,4,0,0] } },
        { name:'Export kWh', type:'bar', data: rows.map((r) => r.export), barMaxWidth: 28,
          itemStyle: { color: '#56CCF2', borderRadius: [4,4,0,0] } },
      ],
    }
  }, [rows])

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Filters */}
      <div className="glass-card" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <DateRangePicker value={range} onChange={setRange} />
          <FilterSelect value={feeder}  onChange={setFeeder}  options={feeders} />
          <FilterSelect value={rtype}   onChange={setRtype}   options={REPORT_TYPES} />
          <FilterSelect value={cclass}  onChange={setCclass}  options={classes} />
          <button className="btn-primary" style={{ height: 36, fontSize: 13, alignSelf: 'flex-end' }}
            onClick={handleGenerate} disabled={loading}>
            {loading
              ? <><RefreshCw size={13} style={{ marginRight: 5, animation: 'spin 1s linear infinite' }} />Generating…</>
              : <><BarChart2 size={13} style={{ marginRight: 5 }} />Generate Report</>}
          </button>
          {rows && (
            <button className="btn-secondary" style={{ height: 36, fontSize: 13, alignSelf: 'flex-end' }}
              onClick={() => exportCSV(rows, 'consumption_report.csv')}>
              <Download size={13} style={{ marginRight: 5 }} />Export CSV
            </button>
          )}
        </div>
      </div>

      {!rows && !loading && (
        <div className="glass-card" style={{ padding: 48, textAlign: 'center' }}>
          <BarChart2 size={40} color="#ABC7FF44" style={{ margin: '0 auto 12px' }} />
          <p style={{ color: '#ABC7FF', fontSize: 14 }}>Select filters and click Generate Report to view consumption data.</p>
        </div>
      )}

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[1,2,3].map((k) => <div key={k} className="skeleton" style={{ height: 60, borderRadius: 8 }} />)}
        </div>
      )}

      {rows && !loading && (
        <>
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="text-white font-semibold mb-2" style={{ fontSize: 14 }}>
              {rtype} Consumption — {feeder} — {cclass}
            </div>
            <ReactECharts option={barOption} style={{ height: 280 }} />
          </div>

          <div className="glass-card" style={{ padding: 20 }}>
            <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>Summary</div>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ width: '100%' }}>
                <thead><tr>
                  {['Date','Total Import kWh','Total Export kWh','Net kWh','Peak Demand kW','Avg Power Factor'].map((h) => <th key={h}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td style={{ color: '#ABC7FF', fontSize: 11 }}>{r.date}</td>
                      <td style={{ color: '#02C9A8', fontFamily: 'monospace' }}>{fmt(r.import)}</td>
                      <td style={{ color: '#56CCF2', fontFamily: 'monospace' }}>{fmt(r.export)}</td>
                      <td style={{ fontFamily: 'monospace' }}>{fmt(r.net)}</td>
                      <td style={{ fontFamily: 'monospace' }}>{r.peak}</td>
                      <td style={{ color: r.pf >= 0.95 ? '#02C9A8' : '#F59E0B', fontFamily: 'monospace' }}>{r.pf}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Meter Reading Reports ────────────────────────────────────────────────────
function MeterReadingReports() {
  const feeders = useFeederOptions()
  const [serial,   setSerial]   = useState('')
  const [feeder,   setFeeder]   = useState(ALL_FEEDERS)
  const [range,    setRange]    = useState(defaultRange('30d'))
  const [rows,     setRows]     = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [searched, setSearched] = useState('')

  const handleSearch = async () => {
    const s = serial.trim()
    if (!s) return // No hardcoded default serial — user must enter one
    setLoading(true)
    try {
      const res = await reportsAPI.meterReadings({
        meter_serial: s,
        from_date: range.from,
        to_date: range.to,
      })
      setRows(res.data?.readings || [])
      setSearched(s)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const lineOption = useMemo(() => {
    if (!rows) return null
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22' },
      xAxis: { type: 'category', data: rows.map((r) => r.date),
        axisLabel: { color: '#ABC7FF', fontSize: 11, rotate: 30 },
        axisLine: { lineStyle: { color: '#ABC7FF44' } } },
      yAxis: { type: 'value', axisLabel: { color: '#ABC7FF', formatter: '{value} kWh' },
        splitLine: { lineStyle: { color: '#ABC7FF11' } } },
      series: [{
        type: 'line', data: rows.map((r) => r.delta), smooth: true,
        lineStyle: { color: '#02C9A8', width: 2 },
        areaStyle: { color: { type:'linear', x:0,y:0,x2:0,y2:1,
          colorStops:[{offset:0,color:'#02C9A844'},{offset:1,color:'#02C9A800'}] } },
        symbol: 'circle', symbolSize: 5, itemStyle: { color: '#02C9A8' },
      }],
    }
  }, [rows])

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="glass-card" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <label style={{ color: '#ABC7FF', fontSize: 11 }}>Meter Serial</label>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: '#ABC7FF88' }} />
              <input value={serial} onChange={(e) => setSerial(e.target.value)}
                placeholder="ESK-XXXXXXX"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                style={{ paddingLeft: 28, paddingRight: 12, paddingTop: 8, paddingBottom: 8,
                  background: '#0A1628', border: '1px solid #ABC7FF22', borderRadius: 8,
                  color: '#fff', fontSize: 13, outline: 'none', fontFamily: 'monospace', width: 180 }} />
            </div>
          </div>
          <FilterSelect value={feeder} onChange={setFeeder} options={feeders} />
          <DateRangePicker value={range} onChange={setRange} />
          <button className="btn-primary" style={{ height: 36, fontSize: 13, alignSelf: 'flex-end' }}
            onClick={handleSearch} disabled={loading || !serial.trim()}>
            {loading
              ? <><RefreshCw size={13} style={{ marginRight: 5, animation: 'spin 1s linear infinite' }} />Searching…</>
              : <><Search size={13} style={{ marginRight: 5 }} />Search</>}
          </button>
          {rows && (
            <button className="btn-secondary" style={{ height: 36, fontSize: 13, alignSelf: 'flex-end' }}
              onClick={() => exportCSV(rows, `readings_${searched}.csv`)}>
              <Download size={13} style={{ marginRight: 5 }} />Export CSV
            </button>
          )}
        </div>
      </div>

      {!rows && !loading && (
        <div className="glass-card" style={{ padding: 48, textAlign: 'center' }}>
          <FileText size={40} color="#ABC7FF44" style={{ margin: '0 auto 12px' }} />
          <p style={{ color: '#ABC7FF', fontSize: 14 }}>Enter a meter serial and click Search to view readings.</p>
        </div>
      )}

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1,2,3].map((k) => <div key={k} className="skeleton" style={{ height: 48, borderRadius: 8 }} />)}
        </div>
      )}

      {rows && !loading && (
        <>
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="text-white font-semibold mb-1" style={{ fontSize: 14 }}>
              Daily Consumption — <span style={{ color: '#56CCF2', fontFamily: 'monospace' }}>{searched}</span>
            </div>
            <div style={{ color: '#ABC7FF', fontSize: 11, marginBottom: 8 }}>Last 14 days (kWh delta)</div>
            <ReactECharts option={lineOption} style={{ height: 220 }} />
          </div>

          <div className="glass-card" style={{ padding: 20 }}>
            <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>Reading Detail</div>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ width: '100%' }}>
                <thead><tr>
                  {['Date','Reading kWh','Delta kWh','Demand kW','Voltage V','Power Factor','Estimated?'].map((h) => <th key={h}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td style={{ color: '#ABC7FF', fontSize: 11 }}>{r.date}</td>
                      <td style={{ fontFamily: 'monospace' }}>{fmt(r.reading)}</td>
                      <td style={{ color: '#02C9A8', fontFamily: 'monospace' }}>{r.delta}</td>
                      <td style={{ fontFamily: 'monospace' }}>{r.demand}</td>
                      <td style={{ color: r.voltage < 226 || r.voltage > 234 ? '#F59E0B' : '#02C9A8', fontFamily: 'monospace' }}>{r.voltage}</td>
                      <td style={{ color: r.pf >= 0.95 ? '#02C9A8' : '#F59E0B', fontFamily: 'monospace' }}>{r.pf}</td>
                      <td style={{ textAlign: 'center' }}>
                        {r.estimated === 'Y'
                          ? <span className="badge-medium" style={{ fontSize: 10 }}>Est</span>
                          : <span className="badge-ok" style={{ fontSize: 10 }}>Act</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Audit Statements ─────────────────────────────────────────────────────────
function AuditStatements() {
  const [query, setQuery] = useState('')
  const [topConsumers, setTopConsumers] = useState([])

  useEffect(() => {
    reportsAPI.topConsumers({ limit: 10 })
      .then(res => setTopConsumers(res.data.consumers))
      .catch(console.error)
  }, [])

  const filteredInquiry = topConsumers.filter((r) => {
    const q = query.toLowerCase()
    return !q || r.meter.toLowerCase().includes(q) || r.customer.toLowerCase().includes(q)
  })

  const totalKwh = topConsumers.reduce((a, r) => a + (r.monthly || r.kwh || 0), 0)
  const avgKwh   = topConsumers.length ? totalKwh / topConsumers.length : 0

  const topBar = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22',
      axisPointer: { type: 'shadow' } },
    grid: { left: 160 },
    xAxis: { type: 'value', axisLabel: { color: '#ABC7FF', formatter: (v) => `${(v/1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: '#ABC7FF11' } } },
    yAxis: { type: 'category', data: topConsumers.map((c) => c.customer).reverse(),
      axisLabel: { color: '#ABC7FF', fontSize: 11 }, axisLine: { lineStyle: { color: '#ABC7FF44' } } },
    series: [{
      type: 'bar', data: topConsumers.map((c) => c.kwh).reverse(), barMaxWidth: 28,
      itemStyle: { color: (p) => {
        const v = topConsumers[topConsumers.length - 1 - p.dataIndex]?.kwh || 0
        return v > 30000 ? '#E94B4B' : v > 15000 ? '#F59E0B' : '#02C9A8'
      }, borderRadius: [0,4,4,0] },
      label: { show: true, position: 'right', color: '#ABC7FF', fontSize: 10,
        formatter: (p) => `${(p.value/1000).toFixed(1)}k kWh` },
    }],
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Summary KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14 }}>
        <KPI icon={Zap}       label="Total Meters in Report" value={fmt(topConsumers.length)}        color="#02C9A8" />
        <KPI icon={TrendingUp}label="Total Consumption (Mo)" value={`${(totalKwh/1000).toFixed(1)} MWh`} color="#56CCF2" />
        <KPI icon={BarChart2} label="Average per Meter (Mo)" value={`${avgKwh.toFixed(0)} kWh`}     color="#ABC7FF" />
      </div>

      {/* Top 10 chart */}
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp size={15} color="#02C9A8" />
          <span className="text-white font-semibold" style={{ fontSize: 14 }}>Energy Intensive Reading — Top 10 Consumers (Monthly kWh)</span>
        </div>
        <ReactECharts option={topBar} style={{ height: 320 }} />
      </div>

      {/* Centralized inquiry */}
      <div className="glass-card" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div className="flex items-center gap-2">
            <ClipboardList size={15} color="#56CCF2" />
            <span className="text-white font-semibold" style={{ fontSize: 14 }}>Centralised Meter Reading Inquiry</span>
          </div>
          <button className="btn-secondary" style={{ fontSize: 11, padding: '5px 12px' }}
            onClick={() => exportCSV(topConsumers, 'meter_inquiry.csv')}>
            <Download size={12} style={{ marginRight: 4 }} />Export CSV
          </button>
        </div>

        <div style={{ position: 'relative', maxWidth: 380, marginBottom: 14 }}>
          <Search size={13} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: '#ABC7FF88' }} />
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search meter or customer…"
            style={{ width: '100%', paddingLeft: 28, paddingRight: 12, paddingTop: 8, paddingBottom: 8,
              background: 'rgba(255,255,255,0.05)', border: '1px solid #ABC7FF22',
              borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none' }} />
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Meter','Customer','Daily Usage kWh','Monthly Usage kWh','Periodic Usage kWh','Last Read Date'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {filteredInquiry.map((r, i) => (
                <tr key={i}>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{r.meter}</td>
                  <td style={{ fontSize: 12 }}>{r.customer}</td>
                  <td style={{ fontFamily: 'monospace', color: '#02C9A8' }}>{r.daily}</td>
                  <td style={{ fontFamily: 'monospace' }}>{fmt(r.monthly)}</td>
                  <td style={{ fontFamily: 'monospace' }}>{fmt(r.periodic)}</td>
                  <td style={{ color: '#ABC7FF', fontSize: 11 }}>{r.lastRead}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ color: '#ABC7FF', fontSize: 11, marginTop: 8 }}>
          Showing {filteredInquiry.length} of {topConsumers.length} meters
        </div>
      </div>
    </div>
  )
}

// ─── EGSM (MDMS proxy) ───────────────────────────────────────────────────────
// Spec 018 W4.T9. Browse the full ~52-endpoint EGSM report surface via the
// /api/v1/reports/egsm/:category/:report proxy. A report name is free-form
// text so any MDMS endpoint the catalogue exposes can be invoked.
function EGSMReports() {
  const [categories, setCategories] = useState([])
  const [category, setCategory] = useState('')
  const [reportName, setReportName] = useState('')
  const [params, setParams] = useState('{}')
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [downloadToken, setDownloadToken] = useState('')
  const [downloadUrl, setDownloadUrl] = useState('')

  useEffect(() => {
    egsmReportsAPI
      .categories()
      .then((r) => {
        setCategories(r.data.categories || [])
        if (r.data.categories?.length) setCategory(r.data.categories[0].slug)
      })
      .catch(console.error)
  }, [])

  const runReport = async () => {
    if (!category || !reportName) {
      setError('Category and report name are required.')
      return
    }
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      let parsed = {}
      if (params.trim()) parsed = JSON.parse(params)
      const res = await egsmReportsAPI.run(category, reportName.trim(), parsed)
      setResponse(res.data)
    } catch (e) {
      setError(
        e?.response?.data?.detail?.error?.message ||
          e?.response?.data?.detail ||
          e.message,
      )
    } finally {
      setLoading(false)
    }
  }

  const pollDownload = async () => {
    if (!downloadToken.trim()) return
    try {
      const res = await egsmReportsAPI.pollDownload(downloadToken.trim())
      if (res.data?.url) setDownloadUrl(res.data.url)
      else setError('Download not ready yet — try again in a few seconds.')
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    }
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>
          EGSM report (MDMS proxy)
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
          <div>
            <label style={{ color: '#ABC7FF', fontSize: 11 }}>Category</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13 }}>
              {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ color: '#ABC7FF', fontSize: 11 }}>Report slug</label>
            <input value={reportName} onChange={(e) => setReportName(e.target.value)}
              placeholder="e.g. feeder-loss-summary"
              style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13,
                fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ color: '#ABC7FF', fontSize: 11 }}>Parameters (JSON)</label>
            <textarea value={params} onChange={(e) => setParams(e.target.value)}
              placeholder='{"from_date":"2026-04-01","to_date":"2026-04-18"}'
              style={{ width: '100%', padding: '8px 10px', background: '#0A1628',
                border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 12,
                fontFamily: 'monospace', minHeight: 60, outline: 'none', resize: 'vertical',
                boxSizing: 'border-box' }} />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn-primary" onClick={runReport} disabled={loading}
            style={{ gap: 6, fontSize: 13 }}>
            <PlayCircle size={13} />{loading ? 'Running…' : 'Run report'}
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card" style={{ padding: 16, border: '1px solid #E94B4B55',
          background: 'rgba(233,75,75,0.08)' }}>
          <span style={{ color: '#E94B4B', fontWeight: 700 }}>Error:</span>{' '}
          <span style={{ color: '#fff', fontSize: 13 }}>{error}</span>
        </div>
      )}

      {response && (
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <div className="text-white font-semibold" style={{ fontSize: 14 }}>
              /reports/egsm/{category}/{reportName}
            </div>
            {Array.isArray(response?.rows) && (
              <button className="btn-secondary" style={{ fontSize: 11 }}
                onClick={() => exportCSV(response.rows, `${reportName}.csv`)}>
                <Download size={12} style={{ marginRight: 4 }} />Export CSV
              </button>
            )}
          </div>
          <pre style={{
            margin: 0, padding: 14, background: '#020617', borderRadius: 8,
            color: '#02C9A8', fontFamily: 'monospace', fontSize: 11,
            maxHeight: 400, overflow: 'auto',
          }}>
            {JSON.stringify(response, null, 2)}
          </pre>
        </div>
      )}

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold" style={{ fontSize: 14, marginBottom: 10 }}>
          CSV download pipeline
        </div>
        <p style={{ color: '#ABC7FF', fontSize: 12, margin: '0 0 10px' }}>
          Large exports are handed off to MDMS's S3+SQS pipeline. Enter the
          download token returned by the report, then poll.
        </p>
        <div style={{ display: 'flex', gap: 10 }}>
          <input value={downloadToken} onChange={(e) => setDownloadToken(e.target.value)}
            placeholder="download token" style={{ flex: 1, padding: '8px 10px',
              background: '#0A1628', border: '1px solid #ABC7FF22', borderRadius: 8,
              color: '#fff', fontSize: 13, fontFamily: 'monospace', outline: 'none' }} />
          <button className="btn-secondary" onClick={pollDownload}>Poll</button>
        </div>
        {downloadUrl && (
          <a href={downloadUrl} target="_blank" rel="noreferrer"
            style={{ color: '#02C9A8', fontSize: 12, marginTop: 8, display: 'inline-block' }}>
            Download ready → {downloadUrl}
          </a>
        )}
      </div>
    </div>
  )
}

// ─── Scheduled reports ────────────────────────────────────────────────────────
// Spec 018 W4.T10. List + create + run-now for user-scheduled EGSM reports.
function ScheduledReportsPanel() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({
    name: '', report_ref: '', schedule_cron: '0 6 * * *',
    recipients: '', params: '{}', enabled: true,
  })

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await scheduledReportsAPI.list()
      setRows(res.data || [])
    } catch (e) {
      console.error(e)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const create = async () => {
    if (!form.name.trim() || !form.report_ref.trim()) return
    try {
      await scheduledReportsAPI.create({
        name: form.name.trim(),
        report_ref: form.report_ref.trim(),
        schedule_cron: form.schedule_cron.trim(),
        recipients: form.recipients.split(',').map((s) => s.trim()).filter(Boolean),
        params: form.params.trim() ? JSON.parse(form.params) : {},
        enabled: form.enabled,
      })
      await refresh()
      setCreating(false)
      setForm({ name: '', report_ref: '', schedule_cron: '0 6 * * *',
        recipients: '', params: '{}', enabled: true })
    } catch (e) {
      alert(e?.response?.data?.detail || 'Create failed')
    }
  }

  const runNow = async (id) => {
    try {
      await scheduledReportsAPI.runNow(id)
      await refresh()
    } catch (e) { alert(e?.response?.data?.detail || 'Run failed') }
  }

  const remove = async (id) => {
    if (!confirm('Delete this schedule?')) return
    try {
      await scheduledReportsAPI.remove(id)
      await refresh()
    } catch (e) { alert('Delete failed') }
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button className="btn-secondary" onClick={refresh} style={{ gap: 6 }}>
          <RefreshCw size={12} /> Refresh
        </button>
        <button className="btn-primary" onClick={() => setCreating(true)} style={{ gap: 6 }}>
          <Clock size={13} /> New Schedule
        </button>
      </div>

      {creating && (
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div><label style={{ color: '#ABC7FF', fontSize: 11 }}>Name</label>
              <input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13,
                  boxSizing: 'border-box' }} /></div>
            <div><label style={{ color: '#ABC7FF', fontSize: 11 }}>report_ref</label>
              <input value={form.report_ref}
                onChange={(e) => setForm((p) => ({ ...p, report_ref: e.target.value }))}
                placeholder="egsm:energy-audit:feeder-loss-summary"
                style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13,
                  fontFamily: 'monospace', boxSizing: 'border-box' }} /></div>
            <div><label style={{ color: '#ABC7FF', fontSize: 11 }}>Cron</label>
              <input value={form.schedule_cron}
                onChange={(e) => setForm((p) => ({ ...p, schedule_cron: e.target.value }))}
                style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13,
                  fontFamily: 'monospace', boxSizing: 'border-box' }} /></div>
            <div><label style={{ color: '#ABC7FF', fontSize: 11 }}>Recipients (comma-separated)</label>
              <input value={form.recipients}
                onChange={(e) => setForm((p) => ({ ...p, recipients: e.target.value }))}
                placeholder="ops@example.com,mgr@example.com"
                style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 13,
                  boxSizing: 'border-box' }} /></div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ color: '#ABC7FF', fontSize: 11 }}>Parameters (JSON)</label>
              <textarea value={form.params}
                onChange={(e) => setForm((p) => ({ ...p, params: e.target.value }))}
                style={{ width: '100%', padding: '7px 10px', background: '#0A1628',
                  border: '1px solid #ABC7FF22', borderRadius: 8, color: '#fff', fontSize: 12,
                  fontFamily: 'monospace', minHeight: 60, outline: 'none', resize: 'vertical',
                  boxSizing: 'border-box' }} /></div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn-primary" onClick={create}>Create</button>
            <button className="btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="glass-card" style={{ overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Report</th><th>Cron</th><th>Recipients</th>
              <th>Last Run</th><th>Status</th><th style={{ width: 130 }}>Actions</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: '#ABC7FF' }}>Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: '#ABC7FF' }}>
                No scheduled reports yet.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.id}>
                <td style={{ fontWeight: 600, color: '#fff' }}>{r.name}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#56CCF2' }}>{r.report_ref}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#ABC7FF' }}>{r.schedule_cron}</td>
                <td style={{ fontSize: 11, color: '#ABC7FF' }}>{r.recipients?.join(', ') || '—'}</td>
                <td style={{ fontSize: 11, color: '#ABC7FF' }}>
                  {r.last_run_at ? new Date(r.last_run_at).toLocaleString() : '—'}
                </td>
                <td>
                  {r.last_status === 'ok'
                    ? <span className="badge-ok" style={{ fontSize: 10 }}>OK</span>
                    : r.last_status === 'error'
                      ? <span className="badge-critical" style={{ fontSize: 10 }}>ERR</span>
                      : <span style={{ fontSize: 10, color: '#ABC7FF' }}>—</span>}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => runNow(r.id)}
                      style={{ padding: '3px 9px', borderRadius: 5, fontSize: 11,
                        background: '#02C9A822', border: '1px solid #02C9A8', color: '#02C9A8',
                        cursor: 'pointer', fontWeight: 700 }}>Run</button>
                    <button onClick={() => remove(r.id)}
                      style={{ padding: '3px 9px', borderRadius: 5, fontSize: 11,
                        background: 'rgba(233,75,75,0.1)', border: '1px solid rgba(233,75,75,0.3)',
                        color: '#E94B4B', cursor: 'pointer', fontWeight: 700 }}>×</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function Reports() {
  const [tab, setTab] = useState(0)

  const panels = [
    <ConsumptionReports />,
    <MeterReadingReports />,
    <AuditStatements />,
    <EGSMReports />,
    <ScheduledReportsPanel />,
  ]

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: '#ABC7FF22',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <FileText size={18} color="#ABC7FF" />
          </div>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>Reports &amp; Audit</h1>
            <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>REQ-13 / REQ-14 — Consumption · Meter Readings · Audit Statements</p>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 22, background: 'rgba(255,255,255,0.04)',
        padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            style={{
              padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600,
              cursor: 'pointer', border: 'none', transition: 'all 0.2s',
              background: tab === i ? 'linear-gradient(135deg,#0A3690,#ABC7FF88)' : 'transparent',
              color: tab === i ? '#fff' : '#ABC7FF',
            }}>
            {t}
          </button>
        ))}
      </div>

      {panels[tab]}
    </div>
  )
}
