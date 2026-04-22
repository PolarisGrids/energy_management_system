import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Battery, Car, GitMerge, Zap, Activity, TrendingUp,
  Power, PowerOff, Sliders, AlertTriangle, CheckCircle,
  RefreshCw, ChevronRight, Gauge, PlugZap, Wifi, WifiOff,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI } from '@/services/api'
import useAuthStore from '@/stores/authStore'

// ─── Shared helpers ──────────────────────────────────────────────────────────

const fmt = (v, decimals = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: decimals })

const statusBadgeClass = (status) => {
  if (!status) return 'badge-info'
  const map = {
    online: 'badge-ok', offline: 'badge-critical', curtailed: 'badge-medium',
    charging: 'badge-info', discharging: 'badge-ok', idle: 'badge-low',
    islanded: 'badge-high',
  }
  return map[status] ?? 'badge-info'
}

const typeIcon = { pv: Sun, bess: Battery, ev_charger: Car, microgrid: GitMerge }
const typeColor = { pv: '#F59E0B', bess: '#56CCF2', ev_charger: '#02C9A8', microgrid: '#ABC7FF' }
const typeLabel = { pv: 'PV Solar', bess: 'BESS Storage', ev_charger: 'EV Charging', microgrid: 'Microgrid' }

const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`)

// ─── Reusable sub-components ─────────────────────────────────────────────────

const KPITile = ({ icon: Icon, label, value, unit, sub, color = '#02C9A8' }) => (
  <div className="metric-card">
    <div className="flex items-start justify-between">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}>
        <Icon size={18} style={{ color }} />
      </div>
    </div>
    <div className="mt-3">
      <div className="text-white font-black" style={{ fontSize: 26 }}>
        {value}
        {unit && <span className="text-white/40 font-medium ml-1" style={{ fontSize: 14 }}>{unit}</span>}
      </div>
      <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>{label}</div>
      {sub && <div style={{ color, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  </div>
)

const LoadingOverlay = () => (
  <div className="flex items-center justify-center py-16">
    <div className="flex items-center gap-3 text-white/40">
      <RefreshCw size={16} className="animate-spin" />
      <span style={{ fontSize: 14 }}>Loading DER assets…</span>
    </div>
  </div>
)

const ErrorBanner = ({ message, onRetry }) => (
  <div className="glass-card p-4 flex items-center gap-3"
    style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
    <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
    <span className="text-white/80" style={{ fontSize: 14 }}>{message}</span>
    {onRetry && (
      <button onClick={onRetry} className="btn-secondary ml-auto" style={{ padding: '6px 14px', fontSize: 12 }}>
        Retry
      </button>
    )}
  </div>
)

const UtilizationBar = ({ pct, color }) => (
  <div className="mt-2">
    <div className="flex justify-between mb-1">
      <span className="text-white/40" style={{ fontSize: 11 }}>Utilization</span>
      <span style={{ fontSize: 11, color }}>{fmt(pct, 1)}%</span>
    </div>
    <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
      <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', borderRadius: 2, background: color, transition: 'width 0.4s ease' }} />
    </div>
  </div>
)

const CommandButton = ({ label, icon: Icon, onClick, loading, variant = 'secondary', color }) => (
  <button
    onClick={onClick}
    disabled={loading}
    className={variant === 'primary' ? 'btn-primary' : 'btn-secondary'}
    style={{ padding: '7px 12px', fontSize: 12, gap: 6, opacity: loading ? 0.6 : 1 }}
  >
    {Icon && <Icon size={13} />}
    {label}
  </button>
)

const SectionHeader = ({ title, children }) => (
  <div className="flex items-center justify-between mb-4">
    <h2 className="text-white font-bold" style={{ fontSize: 15 }}>{title}</h2>
    <div className="flex items-center gap-2">{children}</div>
  </div>
)

// Gauge option factory
const makeGaugeOption = (value, max, label, colorFn) => ({
  backgroundColor: 'transparent',
  series: [{
    type: 'gauge',
    startAngle: 205, endAngle: -25,
    min: 0, max,
    radius: '90%',
    itemStyle: { color: colorFn(value) },
    progress: { show: true, width: 14 },
    pointer: { show: false },
    axisLine: { lineStyle: { width: 14, color: [[1, 'rgba(171,199,255,0.08)']] } },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
    detail: {
      valueAnimation: true,
      formatter: (v) => `${fmt(v, max > 100 ? 0 : 1)}${max === 100 ? '%' : ''}`,
      color: '#fff', fontSize: 22, fontWeight: 900, fontFamily: 'Satoshi', offsetCenter: [0, 0],
    },
    title: { show: true, color: '#ABC7FF', fontSize: 11, offsetCenter: [0, '70%'], formatter: label },
    data: [{ value: Number(value.toFixed(1)) }],
  }],
})

// ─── TABS ─────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview', label: 'Overview',     icon: Activity },
  { id: 'pv',       label: 'PV Solar',     icon: Sun },
  { id: 'bess',     label: 'BESS Storage', icon: Battery },
  { id: 'ev',       label: 'EV Charging',  icon: Car },
]

// ─── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab({ assets, onCommand, cmdLoading }) {
  const navigate = useNavigate()
  const pvAssets    = assets.filter(a => a.asset_type === 'pv')
  const bessAssets  = assets.filter(a => a.asset_type === 'bess')
  const evAssets    = assets.filter(a => a.asset_type === 'ev_charger')
  const mgAssets    = assets.filter(a => a.asset_type === 'microgrid')

  // Microgrid card suppressed when the fleet has none configured — it used
  // to render a dimmed 'No Microgrid asset' tile that confused operators.
  const groups = [
    { key: 'pv',        label: 'PV Solar',   icon: Sun,      color: '#F59E0B', items: pvAssets,   route: '/der/pv' },
    { key: 'bess',      label: 'BESS',        icon: Battery,  color: '#56CCF2', items: bessAssets, route: '/der/bess' },
    { key: 'ev_charger',label: 'EV Charging', icon: Car,      color: '#02C9A8', items: evAssets,   route: '/der/ev' },
    ...(mgAssets.length > 0
      ? [{ key: 'microgrid', label: 'Microgrid', icon: GitMerge, color: '#ABC7FF', items: mgAssets, route: null }]
      : []),
  ]

  return (
    <div className="space-y-6">
      {/* Asset group cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {groups.map(({ key, label, icon: Icon, color, items, route }) => {
          const asset = items[0]
          if (!asset) return (
            <div key={key} className="glass-card p-5 flex flex-col items-center justify-center gap-2" style={{ minHeight: 160 }}>
              <Icon size={28} style={{ color: 'rgba(255,255,255,0.15)' }} />
              <span className="text-white/30" style={{ fontSize: 13 }}>No {label} asset</span>
            </div>
          )
          const util = asset.rated_capacity_kw > 0
            ? (asset.current_output_kw / asset.rated_capacity_kw) * 100 : 0

          return (
            <div key={key}
              className="glass-card p-5 flex flex-col gap-3"
              onClick={() => route && navigate(route)}
              style={{ cursor: route ? 'pointer' : 'default' }}
            >
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: `${color}20` }}>
                  <Icon size={16} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-white font-bold truncate" style={{ fontSize: 13 }}>{asset.name}</div>
                  <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
                </div>
                <span className={statusBadgeClass(asset.status)}>{asset.status}</span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-white/40" style={{ fontSize: 10 }}>Output</div>
                  <div className="text-white font-bold" style={{ fontSize: 17 }}>
                    {fmt(asset.current_output_kw, 1)}
                    <span className="text-white/40 font-normal text-xs ml-1">kW</span>
                  </div>
                </div>
                <div>
                  <div className="text-white/40" style={{ fontSize: 10 }}>Rated</div>
                  <div style={{ color, fontWeight: 700, fontSize: 17 }}>
                    {fmt(asset.rated_capacity_kw, 0)}
                    <span className="text-white/40 font-normal text-xs ml-1">kW</span>
                  </div>
                </div>
              </div>

              <UtilizationBar pct={util} color={color} />

              <div className="flex gap-2 flex-wrap mt-1">
                <CommandButton
                  label="Curtail" icon={Sliders}
                  onClick={() => onCommand(asset.id, { command: 'curtail', value: Math.round(asset.rated_capacity_kw * 0.7), issued_by: 'Operator' })}
                  loading={cmdLoading === asset.id}
                />
                <CommandButton
                  label="Connect" icon={Power}
                  onClick={() => onCommand(asset.id, { command: 'connect', value: null, issued_by: 'Operator' })}
                  loading={cmdLoading === asset.id}
                  variant="primary"
                />
                <CommandButton
                  label="Disconnect" icon={PowerOff}
                  onClick={() => onCommand(asset.id, { command: 'disconnect', value: null, issued_by: 'Operator' })}
                  loading={cmdLoading === asset.id}
                />
              </div>
            </div>
          )
        })}
      </div>

      {/* Situational awareness table */}
      <div>
        <SectionHeader title="Situational Awareness — All DER Assets" />
        <div className="glass-card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Type</th>
                <th>Status</th>
                <th>Output kW</th>
                <th>Capacity kW</th>
                <th>Loading %</th>
                <th>Latitude</th>
                <th>Longitude</th>
                <th>Last Updated</th>
              </tr>
            </thead>
            <tbody>
              {assets.length === 0 ? (
                <tr><td colSpan={9} className="text-center py-8 text-white/30">No assets found</td></tr>
              ) : assets.map((a) => {
                const loading = a.rated_capacity_kw > 0
                  ? ((a.current_output_kw / a.rated_capacity_kw) * 100).toFixed(1) : '0.0'
                const color = typeColor[a.asset_type] ?? '#ABC7FF'
                const Icon  = typeIcon[a.asset_type] ?? Zap
                return (
                  <tr key={a.id}>
                    <td>
                      <div className="flex items-center gap-2">
                        <Icon size={13} style={{ color }} />
                        <span className="text-white font-medium" style={{ fontSize: 13 }}>{a.name}</span>
                      </div>
                    </td>
                    <td>
                      <span style={{ color, fontSize: 12 }}>{typeLabel[a.asset_type] ?? a.asset_type}</span>
                    </td>
                    <td><span className={statusBadgeClass(a.status)}>{a.status}</span></td>
                    <td className="text-white font-mono">{fmt(a.current_output_kw, 1)}</td>
                    <td className="text-white/60 font-mono">{fmt(a.rated_capacity_kw, 0)}</td>
                    <td>
                      <span style={{
                        color: parseFloat(loading) > 90 ? '#E94B4B' : parseFloat(loading) > 70 ? '#F59E0B' : '#02C9A8',
                        fontWeight: 700, fontFamily: 'monospace', fontSize: 13,
                      }}>
                        {loading}%
                      </span>
                    </td>
                    <td className="text-white/40 font-mono text-xs">{a.latitude != null ? a.latitude.toFixed(5) : '—'}</td>
                    <td className="text-white/40 font-mono text-xs">{a.longitude != null ? a.longitude.toFixed(5) : '—'}</td>
                    <td className="text-white/40 text-xs">
                      {a.last_updated ? new Date(a.last_updated).toLocaleString('en-ZA') : new Date().toLocaleTimeString('en-ZA')}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── PV Solar Tab ────────────────────────────────────────────────────────────

function PVTab({ assets, onCommand, cmdLoading }) {
  const [curtailKW, setCurtailKW] = useState('')
  const asset = assets[0]

  if (!asset) return <div className="text-white/40 text-center py-16">No PV Solar asset found.</div>

  const achievementRate = asset.generation_achievement_rate ?? 0
  const gaugeColor = achievementRate >= 80 ? '#02C9A8' : achievementRate >= 60 ? '#F59E0B' : '#E94B4B'

  const hourlyGen = HOURS.map((_, h) => {
    const raw = Math.max(0, Math.sin((h - 6) * Math.PI / 12)) * asset.rated_capacity_kw * (asset.inverter_efficiency ?? 0.97)
    return parseFloat(raw.toFixed(1))
  })

  const barOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 }, formatter: (p) => `${p[0].name}<br/>${p[0].value} kW` },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: HOURS, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 3 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }, name: 'kW', nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 } },
    series: [{
      type: 'bar',
      data: hourlyGen,
      barMaxWidth: 24,
      itemStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: '#F59E0B' }, { offset: 1, color: 'rgba(245,158,11,0.2)' }],
        },
        borderRadius: [4, 4, 0, 0],
      },
    }],
  }

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPITile icon={Zap}       label="Current Output"        value={fmt(asset.current_output_kw, 1)}  unit="kW"   color="#F59E0B" />
        <KPITile icon={Gauge}     label="Rated Capacity"        value={fmt(asset.rated_capacity_kw, 0)}  unit="kW"   color="#F97316" />
        <KPITile icon={TrendingUp} label="Generation Today"     value={fmt(asset.generation_today_kwh, 0)} unit="kWh" color="#02C9A8" />
        <KPITile icon={CheckCircle} label="Achievement Rate"    value={fmt(achievementRate, 1)}           unit="%"    color={gaugeColor}
          sub={achievementRate >= 80 ? 'Target met' : 'Below target'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Gauge */}
        <div className="glass-card p-5 flex flex-col">
          <div className="text-white/60 font-bold mb-2" style={{ fontSize: 12 }}>ACHIEVEMENT RATE</div>
          <div className="flex-1" style={{ minHeight: 180 }}>
            <ReactECharts
              option={makeGaugeOption(achievementRate, 100, 'Achievement', (v) => v >= 80 ? '#02C9A8' : v >= 60 ? '#F59E0B' : '#E94B4B')}
              style={{ height: 200 }}
            />
          </div>
          {/* Details panel */}
          <div className="mt-2 space-y-2 border-t border-white/5 pt-3">
            {[
              { label: 'Panel Area',         value: `${fmt(asset.panel_area_m2, 0)} m²` },
              { label: 'Inverter Efficiency', value: `${((asset.inverter_efficiency ?? 0) * 100).toFixed(1)}%` },
              { label: 'Inverter Status',    value: asset.status === 'online' ? 'Operational' : 'Offline' },
              { label: 'Revenue Today',      value: `R ${fmt(asset.revenue_today, 0)}` },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between">
                <span className="text-white/40" style={{ fontSize: 12 }}>{label}</span>
                <span className="text-white font-medium" style={{ fontSize: 12 }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 24h generation bar */}
        <div className="glass-card p-5 lg:col-span-2 flex flex-col">
          <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>HOURLY GENERATION PROFILE — 24h (kW)</div>
          <div className="flex-1">
            <ReactECharts option={barOption} style={{ height: 240 }} />
          </div>
        </div>
      </div>

      {/* Curtailment command */}
      <div className="glass-card p-5">
        <div className="text-white font-bold mb-3" style={{ fontSize: 14 }}>Curtailment Command</div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-white/50" style={{ fontSize: 13 }}>Set output to:</span>
          <input
            type="number"
            value={curtailKW}
            onChange={(e) => setCurtailKW(e.target.value)}
            placeholder={`0 – ${asset.rated_capacity_kw} kW`}
            min={0} max={asset.rated_capacity_kw}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none"
            style={{ width: 160, fontSize: 14 }}
          />
          <span className="text-white/40" style={{ fontSize: 13 }}>kW</span>
          <button
            className="btn-primary"
            style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={!curtailKW || cmdLoading === asset.id}
            onClick={() => {
              onCommand(asset.id, { command: 'curtail', value: parseFloat(curtailKW), issued_by: 'Operator' })
              setCurtailKW('')
            }}
          >
            <Sliders size={13} className="mr-1" /> Apply Curtailment
          </button>
          <button
            className="btn-secondary"
            style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={cmdLoading === asset.id}
            onClick={() => onCommand(asset.id, { command: 'connect', value: null, issued_by: 'Operator' })}
          >
            <Power size={13} className="mr-1" /> Full Connect
          </button>
        </div>
        {cmdLoading === asset.id && (
          <div className="flex items-center gap-2 mt-3 text-white/40" style={{ fontSize: 12 }}>
            <RefreshCw size={12} className="animate-spin" /> Sending command…
          </div>
        )}
      </div>
    </div>
  )
}

// ─── BESS Storage Tab ────────────────────────────────────────────────────────

function BESSTab({ assets, onCommand, cmdLoading }) {
  const asset = assets[0]

  if (!asset) return <div className="text-white/40 text-center py-16">No BESS asset found.</div>

  const soc = asset.state_of_charge ?? 0
  const socColor = soc >= 60 ? '#02C9A8' : soc >= 30 ? '#F59E0B' : '#E94B4B'

  // Simulated SoC history: start 40%, charge mid-day, discharge evening
  const socHistory = HOURS.map((_, h) => {
    if (h < 6)  return parseFloat((40 - h * 0.5).toFixed(1))
    if (h < 14) return parseFloat((40 + (h - 6) * 4.5).toFixed(1))   // charging
    if (h < 20) return parseFloat((76 - (h - 14) * 5.5).toFixed(1))  // discharging
    return parseFloat((43 - (h - 20) * 1.5).toFixed(1))
  })

  const lineOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 }, formatter: (p) => `${p[0].name}<br/>SoC: ${p[0].value}%` },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: HOURS, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 3 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    series: [{
      type: 'line',
      data: socHistory,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#56CCF2', width: 2 },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(86,204,242,0.3)' }, { offset: 1, color: 'rgba(86,204,242,0.02)' }] },
      },
    }],
    markLine: {
      silent: true,
      lineStyle: { color: 'rgba(245,158,11,0.4)', type: 'dashed' },
      data: [{ yAxis: 30, label: { formatter: '30% low', color: '#F59E0B', fontSize: 10 } }],
    },
  }

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPITile icon={Gauge}     label="State of Charge"    value={fmt(soc, 1)}                         unit="%"    color={socColor}
          sub={soc >= 60 ? 'Healthy' : soc >= 30 ? 'Moderate' : 'Low — charge soon'} />
        <KPITile icon={Zap}       label="Output"             value={fmt(asset.current_output_kw, 1)}     unit="kW"   color="#56CCF2" />
        <KPITile icon={Battery}   label="Capacity"           value={fmt(asset.capacity_kwh, 0)}          unit="kWh"  color="#ABC7FF" />
        <KPITile icon={TrendingUp} label="Revenue Today"     value={`R ${fmt(asset.revenue_today, 0)}`}  color="#02C9A8" />
        <KPITile icon={RefreshCw} label="Charge Cycles"      value={fmt(asset.charge_cycles, 0)}         color="#F59E0B"
          sub="total lifetime" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* SoC gauge */}
        <div className="glass-card p-5 flex flex-col">
          <div className="text-white/60 font-bold mb-2" style={{ fontSize: 12 }}>STATE OF CHARGE</div>
          <div style={{ minHeight: 200 }}>
            <ReactECharts
              option={makeGaugeOption(soc, 100, 'State of Charge', (v) => v >= 60 ? '#02C9A8' : v >= 30 ? '#F59E0B' : '#E94B4B')}
              style={{ height: 210 }}
            />
          </div>
          <div className="space-y-2 border-t border-white/5 pt-3 mt-1">
            {[
              { label: 'Status',        value: asset.status },
              { label: 'Charge Cycles', value: fmt(asset.charge_cycles, 0) },
              { label: 'Energy Stored', value: `${fmt((soc / 100) * (asset.capacity_kwh ?? 0), 0)} kWh` },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between">
                <span className="text-white/40" style={{ fontSize: 12 }}>{label}</span>
                <span className="text-white font-medium" style={{ fontSize: 12 }}>{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* SoC history line */}
        <div className="glass-card p-5 lg:col-span-2 flex flex-col">
          <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>SoC HISTORY — 24h SIMULATION</div>
          <div className="flex-1">
            <ReactECharts option={lineOption} style={{ height: 240 }} />
          </div>
          <div className="flex gap-4 mt-3 text-xs text-white/40">
            <span style={{ color: '#56CCF2' }}>■</span> Charging (PV surplus midday)
            <span style={{ color: 'rgba(86,204,242,0.4)' }}>■</span> Discharging (evening peak)
          </div>
        </div>
      </div>

      {/* Commands */}
      <div className="glass-card p-5">
        <div className="text-white font-bold mb-3" style={{ fontSize: 14 }}>Battery Commands</div>
        <div className="flex gap-3 flex-wrap">
          <button className="btn-primary" style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={cmdLoading === asset.id}
            onClick={() => onCommand(asset.id, { command: 'charge', value: null, issued_by: 'Operator' })}>
            <Battery size={13} className="mr-2" /> Charge
          </button>
          <button className="btn-secondary" style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={cmdLoading === asset.id}
            onClick={() => onCommand(asset.id, { command: 'discharge', value: null, issued_by: 'Operator' })}>
            <Zap size={13} className="mr-2" /> Discharge
          </button>
          <button className="btn-secondary" style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={cmdLoading === asset.id}
            onClick={() => onCommand(asset.id, { command: 'idle', value: null, issued_by: 'Operator' })}>
            <Power size={13} className="mr-2" /> Idle
          </button>
          {cmdLoading === asset.id && (
            <span className="flex items-center gap-2 text-white/40" style={{ fontSize: 12 }}>
              <RefreshCw size={12} className="animate-spin" /> Sending…
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── EV Charging Tab ─────────────────────────────────────────────────────────

function EVTab({ assets, onCommand, cmdLoading }) {
  const [curtailKW, setCurtailKW] = useState('')
  const [portTelemetry, setPortTelemetry] = useState(null)
  const [energyHistory, setEnergyHistory] = useState(null)
  const asset = assets[0]

  // Load per-port + energy-history telemetry for the selected asset.
  useEffect(() => {
    if (!asset?.id) return
    let cancelled = false
    derAPI.telemetry({ asset_id: asset.id, window: '1h' })
      .then((res) => { if (!cancelled) setPortTelemetry(res.data) })
      .catch(() => { if (!cancelled) setPortTelemetry(null) })
    // Energy history endpoint is optional; hide the chart cleanly when absent.
    const eh = derAPI.energyHistory
      ? derAPI.energyHistory({ asset_id: asset.id })
      : Promise.reject(new Error('not-implemented'))
    eh.then((res) => { if (!cancelled) setEnergyHistory(res.data) })
      .catch(() => { if (!cancelled) setEnergyHistory(null) })
    return () => { cancelled = true }
  }, [asset?.id])

  if (!asset) return <div className="text-white/40 text-center py-16">No EV Charger asset found.</div>

  const numPorts = asset.num_ports ?? 0
  const activeSessions = asset.active_sessions ?? 0

  // Per-port breakdown — comes from the telemetry envelope if the backend
  // provides it. NEVER fall back to synthetic or hardcoded sessions arrays.
  const portRows = Array.isArray(portTelemetry?.ports) ? portTelemetry.ports : []

  const portsBarOption = portRows.length ? {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 } },
    grid: { left: 50, right: 16, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: portRows.map(p => p.port || p.label || `Port ${p.index}`), axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'Sessions', nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }, minInterval: 1 },
    series: [{
      type: 'bar',
      data: portRows.map(p => p.sessions ?? 0),
      barMaxWidth: 40,
      itemStyle: {
        color: (params) => (portRows[params.dataIndex]?.sessions ?? 0) > 0 ? '#02C9A8' : 'rgba(255,255,255,0.1)',
        borderRadius: [6, 6, 0, 0],
      },
    }],
  } : null

  // Cumulative energy dispensed hourly — strictly from real history; if the
  // backend doesn't expose it, the chart is hidden rather than synthesized.
  const historyRows = Array.isArray(energyHistory?.series) ? energyHistory.series : []
  const energyLineOption = historyRows.length ? {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,20,50,0.95)', borderColor: 'rgba(171,199,255,0.2)', textStyle: { color: '#fff', fontSize: 12 }, formatter: (p) => `${p[0].name}<br/>Cumulative: ${p[0].value} kWh` },
    grid: { left: 50, right: 16, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: historyRows.map(r => r.label || r.hour || r.ts), axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10, interval: 3 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'kWh', nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    series: [{
      type: 'line',
      data: historyRows.map(r => r.cumul_kwh ?? r.value ?? 0),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#02C9A8', width: 2 },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(2,201,168,0.3)' }, { offset: 1, color: 'rgba(2,201,168,0.02)' }] },
      },
    }],
  } : null

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPITile icon={Activity}  label="Active Sessions"        value={fmt(activeSessions, 0)}              color="#02C9A8"
          sub={`of ${numPorts} ports`} />
        <KPITile icon={PlugZap}   label="Total Ports"            value={fmt(numPorts, 0)}                    color="#56CCF2" />
        <KPITile icon={TrendingUp} label="Energy Dispensed"      value={fmt(asset.energy_dispensed_today_kwh, 0)} unit="kWh" color="#F59E0B" />
        <KPITile icon={Zap}       label="Fees Collected"         value={`R ${fmt(asset.fee_collected_today, 0)}`} color="#ABC7FF" />
        <KPITile icon={Gauge}     label="Current Load"           value={fmt(asset.current_output_kw, 1)}     unit="kW"   color="#F97316"
          sub={asset.status} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Sessions per port */}
        <div className="glass-card p-5">
          <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>SESSIONS PER PORT (CURRENT)</div>
          {portsBarOption ? (
            <ReactECharts option={portsBarOption} style={{ height: 220 }} />
          ) : (
            <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ABC7FF', fontSize: 12 }}>
              Per-port breakdown unavailable.
            </div>
          )}
        </div>

        {/* Cumulative energy line — hidden when real history is unavailable. */}
        {energyLineOption && (
          <div className="glass-card p-5">
            <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>CUMULATIVE ENERGY DISPENSED TODAY (kWh)</div>
            <ReactECharts option={energyLineOption} style={{ height: 220 }} />
          </div>
        )}
      </div>

      {/* Curtail command */}
      <div className="glass-card p-5">
        <div className="text-white font-bold mb-3" style={{ fontSize: 14 }}>Curtail EV Charger — Set Max Output</div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-white/50" style={{ fontSize: 13 }}>New max power:</span>
          <input
            type="number"
            value={curtailKW}
            onChange={(e) => setCurtailKW(e.target.value)}
            placeholder={`0 – ${asset.rated_capacity_kw} kW`}
            min={0} max={asset.rated_capacity_kw}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none"
            style={{ width: 160, fontSize: 14 }}
          />
          <span className="text-white/40" style={{ fontSize: 13 }}>kW</span>
          <button
            className="btn-primary"
            style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={!curtailKW || cmdLoading === asset.id}
            onClick={() => {
              onCommand(asset.id, { command: 'curtail', value: parseFloat(curtailKW), issued_by: 'Operator' })
              setCurtailKW('')
            }}
          >
            <Sliders size={13} className="mr-1" /> Set Limit
          </button>
          <button
            className="btn-secondary"
            style={{ padding: '8px 20px', fontSize: 13 }}
            disabled={cmdLoading === asset.id}
            onClick={() => onCommand(asset.id, { command: 'connect', value: null, issued_by: 'Operator' })}
          >
            <Power size={13} className="mr-1" /> Full Power
          </button>
          {cmdLoading === asset.id && (
            <span className="flex items-center gap-2 text-white/40" style={{ fontSize: 12 }}>
              <RefreshCw size={12} className="animate-spin" /> Sending…
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Microgrid Tab ───────────────────────────────────────────────────────────

function MicrogridTab({ assets, onCommand, cmdLoading }) {
  const [curtailKW, setCurtailKW] = useState('')
  const asset = assets[0]

  if (!asset) return <div className="text-white/40 text-center py-16">No Microgrid asset found.</div>

  const isIslanded     = asset.islanded ?? false
  const reversePower   = asset.reverse_power_flow ?? false
  const util = asset.rated_capacity_kw > 0
    ? (asset.current_output_kw / asset.rated_capacity_kw) * 100 : 0

  const outputGaugeOption = makeGaugeOption(
    Math.min(util, 100), 100, 'Load %',
    (v) => v > 90 ? '#E94B4B' : v > 70 ? '#F59E0B' : '#02C9A8'
  )

  return (
    <div className="space-y-6">
      {/* Reverse power flow warning */}
      {reversePower && (
        <div className="glass-card p-4 flex items-center gap-3 animate-slide-up"
          style={{ borderColor: 'rgba(249,115,22,0.4)', background: 'rgba(249,115,22,0.08)' }}>
          <AlertTriangle size={20} style={{ color: '#F97316' }} />
          <div>
            <div className="text-white font-bold" style={{ fontSize: 14 }}>Reverse Power Flow Detected</div>
            <div className="text-white/60" style={{ fontSize: 13 }}>
              The microgrid is exporting power back to the grid. Review generation/load balance.
            </div>
          </div>
          <button className="btn-secondary ml-auto" style={{ padding: '7px 14px', fontSize: 12 }}
            onClick={() => onCommand(asset.id, { command: 'curtail', value: asset.rated_capacity_kw * 0.8, issued_by: 'Operator' })}>
            Curtail Output
          </button>
        </div>
      )}

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Mode */}
        <div className="glass-card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: isIslanded ? 'rgba(249,115,22,0.2)' : 'rgba(2,201,168,0.2)' }}>
              {isIslanded ? <WifiOff size={18} style={{ color: '#F97316' }} /> : <Wifi size={18} style={{ color: '#02C9A8' }} />}
            </div>
            <div>
              <div className="text-white/40" style={{ fontSize: 11 }}>Operational Mode</div>
              <div className="text-white font-bold" style={{ fontSize: 15 }}>
                {isIslanded ? 'Islanded' : 'Grid-Connected'}
              </div>
            </div>
          </div>
          <span className={isIslanded ? 'badge-high' : 'badge-ok'}>
            {isIslanded ? 'Islanded — Off-grid' : 'Grid Connected'}
          </span>
        </div>

        {/* Reverse power flow */}
        <div className="glass-card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: reversePower ? 'rgba(249,115,22,0.2)' : 'rgba(2,201,168,0.2)' }}>
              <Activity size={18} style={{ color: reversePower ? '#F97316' : '#02C9A8' }} />
            </div>
            <div>
              <div className="text-white/40" style={{ fontSize: 11 }}>Reverse Power Flow</div>
              <div className="text-white font-bold" style={{ fontSize: 15 }}>
                {reversePower ? 'Active' : 'Inactive'}
              </div>
            </div>
          </div>
          <span className={reversePower ? 'badge-high' : 'badge-ok'}>
            {reversePower ? 'Exporting to Grid' : 'Normal Flow'}
          </span>
        </div>

        {/* Current output */}
        <div className="glass-card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(171,199,255,0.15)' }}>
              <GitMerge size={18} style={{ color: '#ABC7FF' }} />
            </div>
            <div>
              <div className="text-white/40" style={{ fontSize: 11 }}>Current Output</div>
              <div className="text-white font-bold" style={{ fontSize: 22 }}>
                {fmt(asset.current_output_kw, 1)}
                <span className="text-white/40 font-normal text-sm ml-1">kW</span>
              </div>
            </div>
          </div>
          <span className={statusBadgeClass(asset.status)}>{asset.status}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Output gauge */}
        <div className="glass-card p-5">
          <div className="text-white/60 font-bold mb-2" style={{ fontSize: 12 }}>OUTPUT vs RATED CAPACITY</div>
          <ReactECharts option={outputGaugeOption} style={{ height: 220 }} />
          <div className="flex justify-between mt-2 text-xs text-white/40">
            <span>Output: {fmt(asset.current_output_kw, 1)} kW</span>
            <span>Rated: {fmt(asset.rated_capacity_kw, 0)} kW</span>
          </div>
        </div>

        {/* Commands */}
        <div className="glass-card p-5 flex flex-col gap-4">
          <div className="text-white font-bold" style={{ fontSize: 14 }}>Microgrid Commands</div>

          <div className="space-y-3">
            <button className="btn-primary w-full" style={{ padding: '10px 20px', fontSize: 13 }}
              disabled={cmdLoading === asset.id}
              onClick={() => onCommand(asset.id, { command: 'connect', value: null, issued_by: 'Operator' })}>
              <Power size={14} className="mr-2" /> Connect to Grid
            </button>
            <button className="btn-secondary w-full" style={{ padding: '10px 20px', fontSize: 13 }}
              disabled={cmdLoading === asset.id}
              onClick={() => onCommand(asset.id, { command: 'island', value: null, issued_by: 'Operator' })}>
              <WifiOff size={14} className="mr-2" /> Island (Disconnect)
            </button>
          </div>

          <div className="border-t border-white/5 pt-4">
            <div className="text-white/50 mb-2" style={{ fontSize: 13 }}>Curtail Output:</div>
            <div className="flex gap-2">
              <input
                type="number"
                value={curtailKW}
                onChange={(e) => setCurtailKW(e.target.value)}
                placeholder={`kW (0–${asset.rated_capacity_kw})`}
                min={0} max={asset.rated_capacity_kw}
                className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white outline-none flex-1"
                style={{ fontSize: 13 }}
              />
              <button className="btn-secondary" style={{ padding: '8px 16px', fontSize: 13 }}
                disabled={!curtailKW || cmdLoading === asset.id}
                onClick={() => {
                  onCommand(asset.id, { command: 'curtail', value: parseFloat(curtailKW), issued_by: 'Operator' })
                  setCurtailKW('')
                }}>
                <Sliders size={13} /> Apply
              </button>
            </div>
          </div>

          {cmdLoading === asset.id && (
            <div className="flex items-center gap-2 text-white/40" style={{ fontSize: 12 }}>
              <RefreshCw size={12} className="animate-spin" /> Sending command…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DERManagement() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('overview')
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const [cmdLoading, setCmdLoading] = useState(null)
  const [cmdFeedback, setCmdFeedback] = useState(null)

  const loadAssets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await derAPI.list()
      setAssets(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to load DER assets. Check API connectivity.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAssets() }, [loadAssets])

  const handleCommand = useCallback(async (id, cmd) => {
    setCmdLoading(id)
    setCmdFeedback(null)
    try {
      await derAPI.command(id, cmd)
      setCmdFeedback({ type: 'ok', msg: `Command "${cmd.command}" sent successfully.` })
      await loadAssets()
    } catch (err) {
      setCmdFeedback({ type: 'err', msg: err.response?.data?.detail ?? 'Command failed.' })
    } finally {
      setCmdLoading(null)
      setTimeout(() => setCmdFeedback(null), 4000)
    }
  }, [loadAssets])

  const pvAssets  = assets.filter(a => a.asset_type === 'pv')
  const bessAssets = assets.filter(a => a.asset_type === 'bess')
  const evAssets  = assets.filter(a => a.asset_type === 'ev_charger')
  const mgAssets  = assets.filter(a => a.asset_type === 'microgrid')

  return (
    <div className="space-y-5 animate-slide-up">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>DER Management</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-15 · REQ-16 · REQ-17 · REQ-20 — Distributed Energy Resource Control
          </div>
        </div>
        <button
          onClick={loadAssets}
          disabled={loading}
          className="btn-secondary flex items-center gap-2"
          style={{ padding: '8px 16px', fontSize: 13 }}
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Command feedback */}
      {cmdFeedback && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{
            borderColor: cmdFeedback.type === 'ok' ? 'rgba(2,201,168,0.3)' : 'rgba(233,75,75,0.3)',
            background: cmdFeedback.type === 'ok' ? 'rgba(2,201,168,0.08)' : 'rgba(233,75,75,0.08)',
          }}>
          {cmdFeedback.type === 'ok'
            ? <CheckCircle size={15} style={{ color: '#02C9A8' }} />
            : <AlertTriangle size={15} style={{ color: '#E94B4B' }} />}
          <span style={{ fontSize: 13, color: cmdFeedback.type === 'ok' ? '#02C9A8' : '#E94B4B' }}>
            {cmdFeedback.msg}
          </span>
        </div>
      )}

      {/* Error state */}
      {error && !loading && <ErrorBanner message={error} onRetry={loadAssets} />}

      {/* Tab bar */}
      <div className="glass-card p-1 flex gap-1 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => {
          const fleetRoute = id === 'pv' ? '/der/pv' : id === 'bess' ? '/der/bess' : id === 'ev' ? '/der/ev' : null
          return (
            <button
              key={id}
              onClick={() => fleetRoute ? navigate(fleetRoute) : setActiveTab(id)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold transition-all whitespace-nowrap"
              style={{
                fontSize: 13,
                background: activeTab === id ? 'rgba(2,201,168,0.15)' : 'transparent',
                color: activeTab === id ? '#02C9A8' : 'rgba(255,255,255,0.5)',
                borderBottom: activeTab === id ? '2px solid #02C9A8' : '2px solid transparent',
              }}
            >
              <Icon size={14} />
              {label}
              {id !== 'overview' && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10,
                  background: activeTab === id ? 'rgba(2,201,168,0.2)' : 'rgba(255,255,255,0.06)',
                  color: activeTab === id ? '#02C9A8' : 'rgba(255,255,255,0.3)',
                }}>
                  {id === 'pv' ? pvAssets.length : id === 'bess' ? bessAssets.length : id === 'ev' ? evAssets.length : mgAssets.length}
                </span>
              )}
              {fleetRoute && (
                <ChevronRight size={12} style={{ color: 'rgba(255,255,255,0.3)' }} />
              )}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      {loading ? (
        <LoadingOverlay />
      ) : (
        <div key={activeTab} className="animate-slide-up">
          {activeTab === 'overview'  && <OverviewTab  assets={assets}     onCommand={handleCommand} cmdLoading={cmdLoading} />}
          {activeTab === 'pv'        && <PVTab         assets={pvAssets}   onCommand={handleCommand} cmdLoading={cmdLoading} />}
          {activeTab === 'bess'      && <BESSTab       assets={bessAssets} onCommand={handleCommand} cmdLoading={cmdLoading} />}
          {activeTab === 'ev'        && <EVTab         assets={evAssets}   onCommand={handleCommand} cmdLoading={cmdLoading} />}
          {activeTab === 'microgrid' && <MicrogridTab  assets={mgAssets}   onCommand={handleCommand} cmdLoading={cmdLoading} />}
        </div>
      )}
    </div>
  )
}
