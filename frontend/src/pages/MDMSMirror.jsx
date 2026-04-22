import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircle, AlertTriangle, TrendingUp, Database,
  Search, RefreshCw, ShieldAlert, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { mdmsAPI, theftAPI } from '@/services/api'
import { ErrorBoundary, UpstreamErrorPanel, useToast } from '@/components/ui'

// ─── helpers ─────────────────────────────────────────────────────────────────
const fmt = (n) => (n ?? 0).toLocaleString()
const TABS = ['VEE Status', 'Consumer Data', 'Billing & Tariffs', 'Analytics']

// Every panel below is rendered behind the SSOT proxy — `/api/v1/mdms/*`
// forwards straight to MDMS. We keep per-panel error state so one
// unavailable endpoint doesn't blank out the whole page.

const KPI = ({ icon: Icon, label, value, color = '#02C9A8', sub }) => (
  <div className="metric-card">
    <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}22`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
      <Icon size={17} style={{ color }} />
    </div>
    <div className="text-white font-black" style={{ fontSize: 24 }}>{value}</div>
    <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
    {sub && <div style={{ color, fontSize: 11, marginTop: 3 }}>{sub}</div>}
  </div>
)

const formatUpstreamError = (err) => {
  if (!err) return null
  const payload = err.response?.data?.error
  if (payload?.message) return `${payload.code || 'ERR'}: ${payload.message}`
  return err.message || 'Upstream request failed'
}

// Normalise the VEE-summary payload from MDMS. The contract is still in
// flight (see mdms-todos.md MDMS-T3 note) so we tolerate two shapes: either
// the legacy {days, validated, estimated, failed} or the spec's
// {items: [{date, validated, estimated, failed}]}. Returns the former.
const normaliseVeeSummary = (raw) => {
  if (!raw) return { days: [], validated: [], estimated: [], failed: [] }
  if (Array.isArray(raw.items)) {
    return {
      days: raw.items.map((r) => r.date),
      validated: raw.items.map((r) => r.validated_count ?? r.validated ?? 0),
      estimated: raw.items.map((r) => r.estimated_count ?? r.estimated ?? 0),
      failed: raw.items.map((r) => r.failed_count ?? r.failed ?? 0),
    }
  }
  return {
    days: raw.days ?? [],
    validated: raw.validated ?? [],
    estimated: raw.estimated ?? [],
    failed: raw.failed ?? [],
  }
}

// ─── VEE Status ───────────────────────────────────────────────────────────────
function VEEStatus({ veeSummary, veeExceptions, error, onRetry }) {
  if (error) {
    return (
      <UpstreamErrorPanel upstream="mdms" detail={error} onRetry={onRetry} />
    )
  }

  const tot = (arr) => (arr ?? []).reduce((a, b) => a + (b ?? 0), 0)
  const totalValid = tot(veeSummary.validated)
  const totalEst = tot(veeSummary.estimated)
  const totalFail = tot(veeSummary.failed)
  const totalProcessed = totalValid + totalEst + totalFail

  // Spec 018 Story 1 acceptance #2: no hardcoded fallback numbers.
  // When totalProcessed is 0 (e.g. upstream returned empty), show em-dashes
  // rather than NaN% on the validation-rate tile.
  const pct = (n) => (totalProcessed > 0 ? `${((n / totalProcessed) * 100).toFixed(1)}%` : '—')

  const bar = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#0A1628', borderColor: '#ABC7FF22',
      axisPointer: { type: 'shadow' } },
    legend: { data: ['Validated','Estimated','Failed'], textStyle: { color: '#ABC7FF' }, bottom: 0 },
    xAxis: { type: 'category', data: veeSummary.days,
      axisLine: { lineStyle: { color: '#ABC7FF44' } }, axisLabel: { color: '#ABC7FF', fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: '#ABC7FF' }, splitLine: { lineStyle: { color: '#ABC7FF11' } } },
    series: [
      { name:'Validated', type:'bar', stack:'vee', data: veeSummary.validated, itemStyle: { color: '#02C9A8' } },
      { name:'Estimated', type:'bar', stack:'vee', data: veeSummary.estimated, itemStyle: { color: '#F59E0B' } },
      { name:'Failed',    type:'bar', stack:'vee', data: veeSummary.failed,    itemStyle: { color: '#E94B4B', borderRadius: [3,3,0,0] } },
    ],
  }

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
        <KPI icon={Database}      label="Records Processed"   value={fmt(totalProcessed)} color="#02C9A8" />
        <KPI icon={CheckCircle}   label="Passed Validation"   value={pct(totalValid)}     color="#02C9A8" />
        <KPI icon={TrendingUp}    label="Estimated Readings"  value={pct(totalEst)}       color="#F59E0B" />
        <KPI icon={AlertTriangle} label="Failed Validation"   value={fmt(totalFail)}      color="#E94B4B" />
      </div>

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>VEE Results — Last 7 Days</div>
        {veeSummary.days.length === 0 ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No VEE summary rows returned by MDMS.
          </div>
        ) : (
          <ReactECharts option={bar} style={{ height: 280 }} />
        )}
      </div>

      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>VEE Exceptions</div>
        {veeExceptions.length === 0 ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No exceptions in the current window.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Meter Serial','Exception Type','Date','Original Value','Corrected Value','Status'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {veeExceptions.map((e, i) => (
                <tr key={i}>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{e.meter_serial ?? e.serial}</td>
                  <td style={{ fontSize: 12 }}>{e.rule_name ?? e.type}</td>
                  <td style={{ color: '#ABC7FF', fontSize: 11 }}>{e.date}</td>
                  <td style={{ fontSize: 12 }}>{e.original_value ?? e.orig ?? '—'}</td>
                  <td style={{ fontSize: 12, color: (e.corrected_value ?? e.corr) === 'Pending' ? '#F59E0B' : '#02C9A8' }}>
                    {e.corrected_value ?? e.corr ?? '—'}
                  </td>
                  <td>
                    <span className={`badge-${(e.status === 'Resolved' || e.status === 'resolved') ? 'ok' : 'medium'}`} style={{ fontSize: 10 }}>
                      {e.status ?? '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Consumer Data ────────────────────────────────────────────────────────────
function ConsumerData({ consumers, error, onRetry }) {
  const [query, setQuery] = useState('')

  if (error) return <UpstreamErrorPanel upstream="mdms" detail={error} onRetry={onRetry} />

  const rows = (consumers ?? []).filter((c) => {
    const q = query.toLowerCase()
    return (
      !q ||
      (c.account_number ?? c.acct ?? '').toLowerCase().includes(q) ||
      (c.customer_name ?? c.name ?? '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ position: 'relative', maxWidth: 420 }}>
        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#ABC7FF88' }} />
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by account number or customer name…"
          style={{ width: '100%', paddingLeft: 32, paddingRight: 12, paddingTop: 9, paddingBottom: 9,
            background: 'rgba(255,255,255,0.05)', border: '1px solid #ABC7FF22',
            borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none' }} />
      </div>

      {rows.length === 0 ? (
        <div className="glass-card" style={{ padding: 40, textAlign: 'center', color: '#ABC7FF' }}>
          {consumers?.length === 0
            ? 'No consumers returned by MDMS CIS.'
            : 'No consumers match the current filter.'}
        </div>
      ) : rows.map((c) => {
        const acct = c.account_number ?? c.acct
        return (
          <div key={acct} className="glass-card" style={{ padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
              <div>
                <div style={{ color: '#02C9A8', fontSize: 11, fontFamily: 'monospace', marginBottom: 2 }}>{acct}</div>
                <div className="text-white font-bold" style={{ fontSize: 16 }}>{c.customer_name ?? c.name}</div>
                <div style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>{c.address ?? c.addr ?? '—'}</div>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
              {[
                ['Tariff Class',   c.tariff_class ?? c.tariff ?? '—'],
                ['Meter Serial',   c.meter_serial ?? c.serial ?? '—'],
                ['Hierarchy',      c.dtr_id ?? c.transformer ?? '—'],
                ['Phase',          c.phase ?? '—'],
              ].map(([k, v]) => (
                <div key={k} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ color: '#ABC7FF', fontSize: 10, marginBottom: 3 }}>{k}</div>
                  <div style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Billing & Tariffs ────────────────────────────────────────────────────────
function BillingTariffs({ tariffs, error, onRetry }) {
  if (error) return <UpstreamErrorPanel upstream="mdms" detail={error} onRetry={onRetry} />

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="text-white font-semibold mb-3" style={{ fontSize: 14 }}>Active Tariff Structures</div>
        {(!tariffs || tariffs.length === 0) ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No tariff schedules returned by MDMS.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Tariff Name','Type','Off-Peak Rate','Standard Rate','Peak Rate','Valid From'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {tariffs.map((t) => (
                <tr key={t.id ?? t.name}>
                  <td style={{ fontWeight: 600, fontSize: 13 }}>{t.name}</td>
                  <td style={{ fontSize: 11 }}><span className="badge-info">{t.tariff_type ?? t.type ?? '—'}</span></td>
                  <td style={{ color: '#02C9A8', fontFamily: 'monospace' }}>{t.offpeak_rate ?? t.offpeak ?? '—'}</td>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace' }}>{t.standard_rate ?? t.std ?? '—'}</td>
                  <td style={{ color: '#E94B4B', fontFamily: 'monospace' }}>{t.peak_rate ?? t.peak ?? '—'}</td>
                  <td style={{ color: '#ABC7FF', fontSize: 11 }}>{t.effective_from ?? t.from ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Analytics ────────────────────────────────────────────────────────────────
function Analytics({ ntl, powerQuality, theftSummary, error, onRetry }) {
  if (error) return <UpstreamErrorPanel upstream="mdms" detail={error} onRetry={onRetry} />

  const ntlColor = (flag) =>
    flag === 'High Risk' || flag === 'high' ? '#E94B4B' :
    flag === 'Medium' || flag === 'medium' ? '#F59E0B' :
    '#56CCF2'

  const pqZones = Array.isArray(powerQuality?.zones) ? powerQuality.zones : []
  const pqCompliant = pqZones.filter(z => z.ok).length
  const pqBreach   = pqZones.length - pqCompliant
  const worstZones = [...pqZones]
    .sort((a, b) => (b.vDev ?? 0) - (a.vDev ?? 0))
    .slice(0, 5)

  const tamperTiers = theftSummary?.tiers || {}

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert size={16} color="#E94B4B" />
          <span className="text-white font-semibold" style={{ fontSize: 14 }}>Non-Technical Loss Detection</span>
        </div>
        {(!ntl || ntl.length === 0) ? (
          <div style={{ color: '#ABC7FF', fontSize: 12, padding: 24, textAlign: 'center' }}>
            No NTL suspects returned by MDMS (MDMS-T2: service gated behind MDMS_NTL_ENABLED).
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Meter Serial','Customer','Consumption Pattern','Suspicion Score','Risk Flag'].map((h) => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {ntl.map((m, i) => (
                <tr key={(m.meter_serial ?? m.serial) + i}>
                  <td style={{ color: '#56CCF2', fontFamily: 'monospace', fontSize: 12 }}>{m.meter_serial ?? m.serial}</td>
                  <td style={{ fontSize: 12 }}>{m.customer_name ?? m.customer ?? '—'}</td>
                  <td style={{ fontSize: 11, color: '#ABC7FF' }}>{m.pattern_description ?? m.pattern ?? '—'}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 60, height: 5, background: '#ABC7FF22', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${m.suspicion_score ?? m.score ?? 0}%`, height: '100%',
                          background: ntlColor(m.risk_flag ?? m.flag), borderRadius: 3 }} />
                      </div>
                      <span style={{ color: ntlColor(m.risk_flag ?? m.flag), fontSize: 12, fontWeight: 700 }}>
                        {m.suspicion_score ?? m.score ?? 0}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 4, fontWeight: 600,
                      background: `${ntlColor(m.risk_flag ?? m.flag)}22`, color: ntlColor(m.risk_flag ?? m.flag) }}>
                      {m.risk_flag ?? m.flag ?? '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Power-quality compliance — per-zone voltage deviation / THD / flicker. */}
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="flex items-center gap-2 mb-3">
          <Zap size={16} color="#F59E0B" />
          <span className="text-white font-semibold" style={{ fontSize: 14 }}>Power Quality Compliance</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#ABC7FF' }}>
            {pqCompliant}/{pqZones.length || 0} zones compliant
            {pqBreach > 0 && <span style={{ color: '#E94B4B', marginLeft: 8 }}>{pqBreach} breach(es)</span>}
          </span>
        </div>
        {pqZones.length === 0 ? (
          <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, padding: 16 }}>
            Power-quality feed unavailable.
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              {['Zone', 'V Deviation %', 'THD %', 'Flicker Pst', 'Status'].map(h => <th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {worstZones.map((z, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 12, color: '#ABC7FF' }}>{z.zone}</td>
                  <td style={{ fontSize: 12, color: (z.vDev ?? 0) > 5 ? '#E94B4B' : '#fff' }}>{z.vDev?.toFixed?.(1) ?? '—'}</td>
                  <td style={{ fontSize: 12, color: (z.thd ?? 0) > 5 ? '#F59E0B' : '#fff' }}>{z.thd?.toFixed?.(1) ?? '—'}</td>
                  <td style={{ fontSize: 12 }}>{z.flicker?.toFixed?.(1) ?? '—'}</td>
                  <td>
                    <span style={{
                      fontSize: 10, padding: '3px 8px', borderRadius: 4, fontWeight: 700,
                      background: z.ok ? 'rgba(2,201,168,0.12)' : 'rgba(233,75,75,0.12)',
                      color: z.ok ? '#02C9A8' : '#E94B4B',
                    }}>
                      {z.ok ? 'COMPLIANT' : 'BREACH'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Tamper analytics — tier distribution from theft scorer. */}
      <div className="glass-card" style={{ padding: 20 }}>
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert size={16} color="#F97316" />
          <span className="text-white font-semibold" style={{ fontSize: 14 }}>Tamper / Theft Analytics</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#ABC7FF' }}>
            {theftSummary?.total_meters ?? 0} meters scored
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          {[
            { key: 'critical', label: 'Critical', color: '#E94B4B' },
            { key: 'high',     label: 'High',     color: '#F97316' },
            { key: 'medium',   label: 'Medium',   color: '#F59E0B' },
            { key: 'low',      label: 'Low',      color: '#6B7280' },
          ].map(t => (
            <div key={t.key} style={{
              padding: '12px 10px', textAlign: 'center', borderRadius: 8,
              background: `${t.color}14`, border: `1px solid ${t.color}33`,
            }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontWeight: 700, textTransform: 'uppercase' }}>{t.label}</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: t.color, marginTop: 2 }}>
                {tamperTiers[t.key] ?? 0}
              </div>
            </div>
          ))}
        </div>
        {theftSummary?.as_of && (
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginTop: 12, textAlign: 'right' }}>
            Last scored: {new Date(theftSummary.as_of).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function MDMSMirror() {
  const [tab, setTab] = useState(0)
  const [veeSummary, setVeeSummary] = useState({ days: [], validated: [], estimated: [], failed: [] })
  const [veeExceptions, setVeeExceptions] = useState([])
  const [consumers, setConsumers] = useState([])
  const [tariffs, setTariffs] = useState([])
  const [ntl, setNtl] = useState([])
  const [powerQuality, setPowerQuality] = useState(null)
  const [theftSummary, setTheftSummary] = useState(null)
  const [errors, setErrors] = useState({ vee: null, consumers: null, tariffs: null, ntl: null })
  const [loading, setLoading] = useState(true)
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    const next = { vee: null, consumers: null, tariffs: null, ntl: null }

    await Promise.all([
      mdmsAPI.veeSummary({ date: new Date().toISOString().slice(0, 10) })
        .then((r) => setVeeSummary(normaliseVeeSummary(r.data)))
        .catch((e) => { next.vee = formatUpstreamError(e) }),
      mdmsAPI.veeExceptions({ page: 1, page_size: 20 })
        .then((r) => setVeeExceptions(r.data?.items ?? r.data?.exceptions ?? []))
        .catch((e) => { next.vee = next.vee || formatUpstreamError(e) }),
      mdmsAPI.consumers({ page: 1, page_size: 20 })
        .then((r) => setConsumers(r.data?.items ?? r.data?.consumers ?? []))
        .catch((e) => { next.consumers = formatUpstreamError(e) }),
      mdmsAPI.tariffs()
        .then((r) => setTariffs(r.data?.items ?? r.data?.tariffs ?? []))
        .catch((e) => { next.tariffs = formatUpstreamError(e) }),
      mdmsAPI.ntlSuspects({ page: 1, page_size: 20 })
        .then((r) => setNtl(r.data?.items ?? r.data?.suspects ?? []))
        .catch((e) => { next.ntl = formatUpstreamError(e) }),
      // Analytics tab — power quality + theft summary. Failures are
      // non-fatal; the analytics panel degrades to an inline empty state.
      mdmsAPI.powerQuality()
        .then((r) => setPowerQuality(r.data))
        .catch(() => setPowerQuality(null)),
      theftAPI.summary()
        .then((r) => setTheftSummary(r.data))
        .catch(() => setTheftSummary(null)),
    ])

    setErrors(next)
    setLoading(false)
    const anyErr = Object.values(next).find(Boolean)
    if (anyErr) toast.error('MDMS partial failure', anyErr)
  }, [toast])

  useEffect(() => { load() }, [load])

  const panels = [
    <ErrorBoundary title="VEE panel crashed" onRetry={load}>
      <VEEStatus veeSummary={veeSummary} veeExceptions={veeExceptions} error={errors.vee} onRetry={load} />
    </ErrorBoundary>,
    <ErrorBoundary title="Consumer panel crashed" onRetry={load}>
      <ConsumerData consumers={consumers} error={errors.consumers} onRetry={load} />
    </ErrorBoundary>,
    <ErrorBoundary title="Billing panel crashed" onRetry={load}>
      <BillingTariffs tariffs={tariffs} error={errors.tariffs} onRetry={load} />
    </ErrorBoundary>,
    <ErrorBoundary title="Analytics panel crashed" onRetry={load}>
      <Analytics ntl={ntl} powerQuality={powerQuality} theftSummary={theftSummary}
        error={errors.ntl} onRetry={load} />
    </ErrorBoundary>,
  ]

  return (
    <div style={{ padding: '24px 28px', minHeight: '100vh', background: '#0A0F1E' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: '#0A369022',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Database size={18} color="#56CCF2" />
          </div>
          <div>
            <h1 className="text-white font-black" style={{ fontSize: 22, lineHeight: 1 }}>MDMS Mirror Panel</h1>
            <p style={{ color: '#ABC7FF', fontSize: 12, marginTop: 2 }}>
              Source of truth: MDMS (via EMS proxy /api/v1/mdms/*) — VEE · CIS · Tariffs · NTL
            </p>
          </div>
          <button type="button" onClick={load}
            className="btn-secondary" style={{ marginLeft: 'auto', fontSize: 12 }}
            disabled={loading}>
            <RefreshCw size={13} style={{ marginRight: 4, animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 22, background: 'rgba(255,255,255,0.04)',
        padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            style={{
              padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600,
              cursor: 'pointer', border: 'none', transition: 'all 0.2s',
              background: tab === i ? 'linear-gradient(135deg,#0A3690,#56CCF2)' : 'transparent',
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
