import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Zap, TrendingDown, TrendingUp, Building2, Layers, Users,
  Home, RefreshCw, DollarSign, Sun, Droplets, BatteryCharging,
  Thermometer, Lightbulb, Wrench, AlertTriangle, Sliders,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { energySavingsAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null || Number.isNaN(v)
    ? '—'
    : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const fmtZar = (v) =>
  v == null || Number.isNaN(v)
    ? '—'
    : `R ${Number(v).toLocaleString('en-ZA', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`

const CATEGORY_ICON = { ac: Thermometer, water_pump: Droplets, ev_charger: BatteryCharging, geyser: Sun, lighting: Lightbulb, other: Wrench }
const CATEGORY_COLOR = { ac: '#56CCF2', water_pump: '#02C9A8', ev_charger: '#F59E0B', geyser: '#E94B4B', lighting: '#ABC7FF', other: '#9CA3AF' }
const LEVEL_ICON = { company: Building2, department: Layers, branch: Home, customer: Users }
const LEVEL_LABEL = { company: 'Company', department: 'Department', branch: 'Branch / Site', customer: 'Customer' }

const KPITile = ({ icon: Icon, label, value, unit, sub, color = '#02C9A8', testId }) => (
  <div className="metric-card" data-testid={testId}>
    <div className="flex items-start justify-between">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${color}20` }}>
        <Icon size={18} style={{ color }} />
      </div>
    </div>
    <div className="mt-3">
      <div className="text-white font-black" style={{ fontSize: 24 }}>
        {value}{unit && <span className="text-white/40 font-medium ml-1" style={{ fontSize: 13 }}>{unit}</span>}
      </div>
      <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
      {sub && <div style={{ color, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  </div>
)

const SkeletonCard = () => (
  <div className="metric-card gap-3">
    <div className="skeleton w-10 h-10 rounded-xl" />
    <div className="skeleton h-7 w-24 mt-3" />
    <div className="skeleton h-3 w-32 mt-1" />
  </div>
)

function findNode(node, id) {
  if (!node) return null
  if (node.id === id) return node
  for (const c of node.children || []) { const h = findNode(c, id); if (h) return h }
  return null
}

function HierarchyPicker({ tree, selected, onSelect }) {
  if (!tree) return null
  const company = tree
  const depts = company.children || []
  const deptNode = depts.find((d) => d.id === selected.department) || null
  const branches = deptNode ? (deptNode.children || []) : []
  const branchNode = branches.find((b) => b.id === selected.branch) || null
  const customers = branchNode ? (branchNode.children || []) : []
  const selectClass = 'bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none text-sm min-w-[180px]'
  const handle = (level, value) => {
    const next = { ...selected, [level]: value }
    const order = ['company', 'department', 'branch', 'customer']
    const idx = order.indexOf(level)
    for (let i = idx + 1; i < order.length; i++) next[order[i]] = ''
    const effectiveId = next.customer || next.branch || next.department || next.company || company.id
    onSelect({ selection: next, effectiveId })
  }
  return (
    <div className="glass-card p-4 flex items-center gap-3 flex-wrap" data-testid="savings-hierarchy-picker">
      <Layers size={14} style={{ color: '#56CCF2' }} />
      <span className="text-white/50" style={{ fontSize: 12 }}>Scope:</span>
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(2,201,168,0.12)', border: '1px solid rgba(2,201,168,0.25)' }}>
        <Building2 size={14} style={{ color: '#02C9A8' }} />
        <span className="text-white font-semibold" style={{ fontSize: 13 }}>{company.name}</span>
      </div>
      <select value={selected.department || ''} onChange={(e) => handle('department', e.target.value)} className={selectClass} data-testid="savings-dept-select">
        <option value="">Department — All</option>
        {depts.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
      </select>
      <select value={selected.branch || ''} onChange={(e) => handle('branch', e.target.value)} className={selectClass} disabled={!deptNode} data-testid="savings-branch-select">
        <option value="">Branch — All</option>
        {branches.map((b) => (<option key={b.id} value={b.id}>{b.name}</option>))}
      </select>
      <select value={selected.customer || ''} onChange={(e) => handle('customer', e.target.value)} className={selectClass} disabled={!branchNode} data-testid="savings-customer-select">
        <option value="">Customer — All</option>
        {customers.map((c) => (<option key={c.id} value={c.id}>{c.name}</option>))}
      </select>
    </div>
  )
}

function TariffCard({ tariff, onUpdate, saving }) {
  const [local, setLocal] = useState(null)
  useEffect(() => { if (tariff) setLocal({ peak_rate: tariff.peak_rate, standard_rate: tariff.standard_rate, offpeak_rate: tariff.offpeak_rate, peak_windows: tariff.peak_windows, offpeak_windows: tariff.offpeak_windows }) }, [tariff])
  if (!local) return null
  const bump = (f, v) => setLocal((p) => ({ ...p, [f]: v }))
  const dirty = local.peak_rate !== tariff.peak_rate || local.standard_rate !== tariff.standard_rate || local.offpeak_rate !== tariff.offpeak_rate
  const inputClass = 'bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-white outline-none text-sm w-full'
  return (
    <div className="glass-card p-5" data-testid="tariff-card">
      <div className="flex items-center gap-2 mb-3">
        <DollarSign size={16} style={{ color: '#F59E0B' }} />
        <h3 className="text-white font-bold" style={{ fontSize: 14 }}>TOU Tariff — Eskom Megaflex</h3>
        <span className="ml-2 text-white/30" style={{ fontSize: 11 }}>R / kWh · weekday bands</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <div className="text-white/50 font-medium" style={{ fontSize: 11 }}>Peak ({local.peak_windows})</div>
          <input type="number" step="0.01" min="0" value={local.peak_rate} onChange={(e) => bump('peak_rate', parseFloat(e.target.value || '0'))} className={inputClass} data-testid="tariff-peak-rate" />
        </div>
        <div>
          <div className="text-white/50 font-medium" style={{ fontSize: 11 }}>Standard</div>
          <input type="number" step="0.01" min="0" value={local.standard_rate} onChange={(e) => bump('standard_rate', parseFloat(e.target.value || '0'))} className={inputClass} data-testid="tariff-standard-rate" />
        </div>
        <div>
          <div className="text-white/50 font-medium" style={{ fontSize: 11 }}>Off-peak ({local.offpeak_windows})</div>
          <input type="number" step="0.01" min="0" value={local.offpeak_rate} onChange={(e) => bump('offpeak_rate', parseFloat(e.target.value || '0'))} className={inputClass} data-testid="tariff-offpeak-rate" />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-3">
        <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: 12, background: dirty ? 'rgba(2,201,168,0.15)' : undefined, color: dirty ? '#02C9A8' : undefined }} disabled={!dirty || saving} onClick={() => onUpdate(local)} data-testid="tariff-save">
          {saving ? 'Saving…' : 'Apply'}
        </button>
      </div>
    </div>
  )
}

function TouProfileChart({ summary }) {
  if (!summary) return null
  const hours = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`)
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 } },
    legend: { data: ['Off-peak', 'Standard', 'Peak'], textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 }, top: 0, right: 0 },
    grid: { left: 50, right: 16, top: 36, bottom: 44 },
    xAxis: { type: 'category', data: hours, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 2 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'kW', nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    series: [
      { name: 'Off-peak', type: 'bar', stack: 'tou', data: summary.hourly_offpeak_kw, itemStyle: { color: '#02C9A8' }, barMaxWidth: 18 },
      { name: 'Standard', type: 'bar', stack: 'tou', data: summary.hourly_standard_kw, itemStyle: { color: '#ABC7FF' }, barMaxWidth: 18 },
      { name: 'Peak', type: 'bar', stack: 'tou', data: summary.hourly_peak_kw, itemStyle: { color: '#E94B4B', borderRadius: [6, 6, 0, 0] }, barMaxWidth: 18 },
    ],
  }
  return (
    <div className="glass-card p-5" data-testid="tou-profile-chart">
      <div className="mb-3">
        <h3 className="text-white font-bold" style={{ fontSize: 14 }}>24h Consumption by TOU Band</h3>
        <div className="text-white/40" style={{ fontSize: 12, marginTop: 2 }}>Stacked — peak (red) · standard (blue-grey) · off-peak (teal)</div>
      </div>
      <ReactECharts option={option} style={{ height: 260 }} />
    </div>
  )
}

function BeforeAfterChart({ scenario }) {
  if (!scenario) return null
  const b = scenario.before, a = scenario.after
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 }, formatter: (p) => p.map((i) => `${i.seriesName}: R ${Number(i.value).toFixed(2)}`).join('<br/>') },
    legend: { data: ['Before shift', 'After shift'], textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 }, top: 0, right: 0 },
    grid: { left: 60, right: 16, top: 36, bottom: 40 },
    xAxis: { type: 'category', data: ['Peak', 'Standard', 'Off-peak'], axisLabel: { color: 'rgba(255,255,255,0.6)', fontSize: 12 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'ZAR', nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    series: [
      { name: 'Before shift', type: 'bar', data: [b.peak.cost, b.standard.cost, b.offpeak.cost], itemStyle: { color: '#E94B4B', borderRadius: [6, 6, 0, 0] }, barMaxWidth: 40 },
      { name: 'After shift', type: 'bar', data: [a.peak.cost, a.standard.cost, a.offpeak.cost], itemStyle: { color: '#02C9A8', borderRadius: [6, 6, 0, 0] }, barMaxWidth: 40 },
    ],
  }
  return (
    <div className="glass-card p-5" data-testid="before-after-chart">
      <div className="mb-3">
        <h3 className="text-white font-bold" style={{ fontSize: 14 }}>Before / After Shift — Cost by TOU Band</h3>
        <div className="text-white/40" style={{ fontSize: 12, marginTop: 2 }}>Red = current · Teal = after shifting flagged peak hours to off-peak</div>
      </div>
      <ReactECharts option={option} style={{ height: 260 }} />
    </div>
  )
}

function ApplianceTable({ appliances, shiftOverrides, onShiftChange, tariff }) {
  if (!appliances) return null
  if (appliances.length === 0) {
    return <div className="glass-card p-8 text-center text-white/40" data-testid="appliance-empty">No appliances registered for this scope yet.</div>
  }
  const delta = Number(tariff?.peak_rate || 0) - Number(tariff?.offpeak_rate || 0)
  return (
    <div className="glass-card overflow-x-auto" data-testid="appliance-table">
      <table className="data-table">
        <thead>
          <tr><th>Appliance</th><th>Count</th><th>kW</th><th>Running hrs (P/S/O)</th><th>Shift peak → off-peak</th><th>Saving / day</th></tr>
        </thead>
        <tbody>
          {appliances.map((a) => {
            const Icon = CATEGORY_ICON[a.category] || Wrench
            const color = CATEGORY_COLOR[a.category] || '#9CA3AF'
            const override = shiftOverrides[a.id]
            const shiftHours = override !== undefined ? override : a.shiftable_peak_hours
            const maxShift = a.peak_hours
            const saving = a.typical_kw * a.count * shiftHours * delta
            return (
              <tr key={a.id}>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${color}20` }}>
                      <Icon size={14} style={{ color }} />
                    </div>
                    <div>
                      <div className="text-white font-semibold" style={{ fontSize: 13 }}>{a.display_name}</div>
                      <div className="text-white/40" style={{ fontSize: 11 }}>{a.category.replace('_', ' ')}</div>
                    </div>
                  </div>
                </td>
                <td className="text-white" style={{ fontSize: 13 }}>{a.count}</td>
                <td className="text-white" style={{ fontSize: 13 }}>{fmt(a.typical_kw, 2)}</td>
                <td>
                  <span style={{ color: '#E94B4B', fontWeight: 700 }}>{fmt(a.peak_hours, 1)}</span>{' / '}
                  <span style={{ color: '#ABC7FF' }}>{fmt(a.standard_hours, 1)}</span>{' / '}
                  <span style={{ color: '#02C9A8', fontWeight: 700 }}>{fmt(a.offpeak_hours, 1)}</span>
                </td>
                <td style={{ minWidth: 200 }}>
                  <div className="flex items-center gap-2">
                    <input type="range" min={0} max={maxShift} step={0.5} value={shiftHours} onChange={(e) => onShiftChange(a.id, parseFloat(e.target.value))} className="flex-1" data-testid={`shift-slider-${a.id}`} />
                    <span style={{ color: '#02C9A8', fontSize: 12, fontWeight: 700, minWidth: 44 }}>{fmt(shiftHours, 1)} h</span>
                  </div>
                </td>
                <td><span style={{ color: saving > 0 ? '#02C9A8' : '#6B7280', fontWeight: 700 }}>{fmtZar(saving)}</span></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function SavingsAnalysisTab() {
  const [tree, setTree] = useState(null)
  const [tariff, setTariff] = useState(null)
  const [selection, setSelection] = useState({ company: '', department: '', branch: '', customer: '' })
  const [effectiveId, setEffectiveId] = useState(null)
  const [summary, setSummary] = useState(null)
  const [appliances, setAppliances] = useState([])
  const [scenario, setScenario] = useState(null)
  const [shiftOverrides, setShiftOverrides] = useState({})
  const [loading, setLoading] = useState(true)
  const [tariffSaving, setTariffSaving] = useState(false)
  const [error, setError] = useState(null)

  const loadBase = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [t, r] = await Promise.all([energySavingsAPI.hierarchy(), energySavingsAPI.tariff()])
      setTree(t.data); setTariff(r.data)
      const rootId = t.data?.id || null
      setEffectiveId(rootId); setSelection((p) => ({ ...p, company: rootId || '' }))
    } catch (e) { setError(e.response?.data?.detail ?? 'Failed to load savings analysis.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadBase() }, [loadBase])

  const loadForScope = useCallback(async (orgUnitId, overrides) => {
    if (!orgUnitId) return
    try {
      const [sumRes, appRes] = await Promise.all([energySavingsAPI.summary(orgUnitId), energySavingsAPI.appliances(orgUnitId)])
      setSummary(sumRes.data); setAppliances(appRes.data)
      const ov = Object.keys(overrides || {}).length ? Object.entries(overrides).map(([id, hrs]) => ({ appliance_usage_id: id, shift_hours: hrs })) : undefined
      const scenRes = await energySavingsAPI.shiftScenario({ org_unit_id: orgUnitId, overrides: ov })
      setScenario(scenRes.data)
    } catch (e) { setError(e.response?.data?.detail ?? 'Failed to compute savings scenario.') }
  }, [])

  useEffect(() => { if (effectiveId) loadForScope(effectiveId, shiftOverrides) }, [effectiveId, shiftOverrides, loadForScope])

  const handleSelection = ({ selection: next, effectiveId: nextId }) => { setSelection(next); setEffectiveId(nextId); setShiftOverrides({}) }
  const handleShiftChange = (id, h) => setShiftOverrides((p) => ({ ...p, [id]: h }))
  const handleTariffUpdate = async (payload) => {
    setTariffSaving(true)
    try { const res = await energySavingsAPI.updateTariff(payload); setTariff(res.data); if (effectiveId) loadForScope(effectiveId, shiftOverrides) }
    catch (e) { setError(e.response?.data?.detail ?? 'Failed to update tariff.') }
    finally { setTariffSaving(false) }
  }
  const applyAllSuggested = () => setShiftOverrides({})
  const resetShifts = () => setShiftOverrides(Object.fromEntries(appliances.map((a) => [a.id, 0])))

  const breadcrumb = useMemo(() => {
    if (!tree || !effectiveId) return null
    const path = []
    if (selection.company && tree) path.push(tree)
    const d = (tree?.children || []).find((x) => x.id === selection.department); if (d) path.push(d)
    const b = d?.children?.find((x) => x.id === selection.branch); if (b) path.push(b)
    const c = b?.children?.find((x) => x.id === selection.customer); if (c) path.push(c)
    return path
  }, [tree, selection, effectiveId])

  if (loading) return (
    <div className="space-y-6" data-testid="savings-loading">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">{Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      <div className="glass-card p-8 text-center text-white/40">Loading savings analysis…</div>
    </div>
  )

  if (error) return (
    <div role="alert" className="glass-card p-5 flex items-center gap-3" style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
      <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
      <div className="flex-1">
        <div className="text-white font-bold" style={{ fontSize: 13 }}>Savings analysis unavailable</div>
        <div className="text-white/70 mt-0.5" style={{ fontSize: 12 }}>{error}</div>
      </div>
      <button onClick={loadBase} className="btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }}>Retry</button>
    </div>
  )

  return (
    <div className="space-y-6" data-testid="savings-analysis-tab">
      <HierarchyPicker tree={tree} selected={selection} onSelect={handleSelection} />
      {breadcrumb && breadcrumb.length > 0 && (
        <div className="flex items-center gap-2 text-white/40" style={{ fontSize: 12 }}>
          <span>Viewing:</span>
          {breadcrumb.map((n, i) => {
            const Icon = LEVEL_ICON[n.level] || Layers
            return (
              <span key={n.id} className="flex items-center gap-1">
                {i > 0 && <span className="text-white/20">›</span>}
                <Icon size={12} />
                <span style={{ color: 'rgba(255,255,255,0.75)' }}>{n.name}</span>
                <span className="text-white/25">({LEVEL_LABEL[n.level]})</span>
              </span>
            )
          })}
        </div>
      )}
      {summary && scenario && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KPITile icon={Zap} label="Daily consumption" value={fmt(summary.total_kwh, 0)} unit="kWh" color="#56CCF2" sub={`${summary.customer_count} customer${summary.customer_count === 1 ? '' : 's'} · ${summary.appliance_count} appl.`} testId="kpi-total-kwh" />
          <KPITile icon={TrendingUp} label="Peak kWh" value={fmt(summary.peak.kwh, 0)} unit="kWh" color="#E94B4B" sub={fmtZar(summary.peak.cost)} testId="kpi-peak" />
          <KPITile icon={Sliders} label="Standard kWh" value={fmt(summary.standard.kwh, 0)} unit="kWh" color="#ABC7FF" sub={fmtZar(summary.standard.cost)} testId="kpi-standard" />
          <KPITile icon={TrendingDown} label="Off-peak kWh" value={fmt(summary.offpeak.kwh, 0)} unit="kWh" color="#02C9A8" sub={fmtZar(summary.offpeak.cost)} testId="kpi-offpeak" />
          <KPITile icon={DollarSign} label="Potential saving / day" value={fmtZar(scenario.saving_cost)} color="#F59E0B" sub={`${fmt(scenario.saving_pct, 1)}% · ${fmt(scenario.saving_kwh, 0)} kWh shifted`} testId="kpi-saving" />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><TouProfileChart summary={summary} /></div>
        <TariffCard tariff={tariff} onUpdate={handleTariffUpdate} saving={tariffSaving} />
      </div>
      <BeforeAfterChart scenario={scenario} />
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-white font-bold" style={{ fontSize: 15 }}>Appliances — Running Hours & Shift Potential</h3>
            <div className="text-white/40" style={{ fontSize: 12, marginTop: 2 }}>Drag each slider to model how many peak hours move to off-peak. Saving assumes the (peak − off-peak) rate differential on the hours you shift.</div>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={applyAllSuggested} data-testid="apply-suggested"><RefreshCw size={12} className="inline mr-1" />Apply suggested</button>
            <button className="btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={resetShifts} data-testid="reset-shifts">Reset to 0</button>
          </div>
        </div>
        <ApplianceTable appliances={appliances} shiftOverrides={shiftOverrides} onShiftChange={handleShiftChange} tariff={tariff} />
      </div>
    </div>
  )
}
