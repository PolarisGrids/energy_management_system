// Inverter drill-down — route: /der/inverters/:inverterId
//
// Reads:
//   * /der/inverters/:id                           → equipment record
//   * /der/inverters/:id/telemetry?window=1h|24h…  → per-inverter time series
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, Cpu, Gauge, RefreshCw, Thermometer, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'

const POLL_MS = 30_000
const ACCENT = '#F59E0B'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

export default function DERInverterDetail() {
  const { inverterId } = useParams()
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [inverter, setInverter] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [banner, setBanner] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  const loadInverter = useCallback(async () => {
    try {
      const { data } = await derAPI.getInverter(inverterId)
      setInverter(data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load inverter.')
    }
  }, [inverterId])

  const loadTelemetry = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await derAPI.inverterTelemetry(inverterId, { window })
      const rows = Array.isArray(data) ? data : (data?.readings || data?.telemetry || [])
      setTelemetry(rows)
      setBanner(data?.banner ?? (rows.length === 0 ? 'No inverter telemetry in window.' : null))
      setRefreshedAt(new Date())
    } catch {
      setTelemetry([])
      setBanner('Failed to load inverter telemetry.')
    } finally {
      setLoading(false)
    }
  }, [inverterId, window])

  useEffect(() => {
    loadInverter()
    loadTelemetry()
    const id = setInterval(loadTelemetry, POLL_MS)
    return () => clearInterval(id)
  }, [loadInverter, loadTelemetry])

  const status = (inverter?.status || '').toLowerCase()
  const badgeClass =
    status === 'online' ? 'badge-ok'
    : status === 'fault' ? 'badge-critical'
    : status === 'maintenance' ? 'badge-medium'
    : 'badge-low'

  const latest = telemetry[telemetry.length - 1] || {}

  const powerChart = useMemo(() => buildLineChart(
    telemetry, 'ac_power_kw', 'AC Power', 'kW', ACCENT,
  ), [telemetry])
  const voltageChart = useMemo(() => buildLineChart(
    telemetry, 'ac_voltage_v', 'AC Voltage', 'V', '#56CCF2',
  ), [telemetry])
  const tempChart = useMemo(() => buildLineChart(
    telemetry, 'temperature_c', 'Temperature', '°C', '#E94B4B',
  ), [telemetry])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="glass-card px-3 py-2 text-white/70 hover:text-white">
            <ArrowLeft size={14} className="inline" /> Back
          </button>
          <div>
            <div className="text-white/40" style={{ fontSize: 11 }}>
              Inverter <span className="font-mono">{inverterId}</span>
            </div>
            <h1 className="text-white font-black" style={{ fontSize: 20 }}>
              {inverter?.manufacturer || 'Inverter'} · {inverter?.model || '—'}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <DERTimeRangePicker value={window} onChange={setWindow} accent={ACCENT} />
          <button onClick={loadTelemetry} className="glass-card px-3 py-2 text-white/70">
            <RefreshCw size={12} className="inline" />
          </button>
        </div>
      </div>

      {error && <Banner color="#E94B4B" message={error} />}
      {banner && <Banner color={ACCENT} message={banner} />}

      {/* ── Equipment card ───────────────────────────────────────────── */}
      {inverter && (
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-bold flex items-center gap-2" style={{ fontSize: 14 }}>
              <Cpu size={14} /> Equipment
            </h2>
            <span className={badgeClass}>{inverter.status || 'unknown'}</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DetailField label="Serial number" value={inverter.serial_number || '—'} mono />
            <DetailField label="Rated AC" value={inverter.rated_ac_kw != null ? `${fmt(inverter.rated_ac_kw, 1)} kW` : '—'} />
            <DetailField label="Rated DC" value={inverter.rated_dc_kw != null ? `${fmt(inverter.rated_dc_kw, 1)} kW` : '—'} />
            <DetailField label="Firmware" value={inverter.firmware_version || '—'} mono />
            <DetailField label="MPPT trackers" value={inverter.num_mppt_trackers ?? '—'} />
            <DetailField label="Strings" value={inverter.num_strings ?? '—'} />
            <DetailField label="Phase" value={inverter.phase_config || '—'} />
            <DetailField label="Comms" value={inverter.comms_protocol || '—'} />
            <DetailField label="AC voltage (nominal)" value={inverter.ac_voltage_nominal_v != null ? `${fmt(inverter.ac_voltage_nominal_v, 0)} V` : '—'} />
            <DetailField label="Installed" value={inverter.installation_date || '—'} />
            <DetailField label="Warranty" value={inverter.warranty_expires || '—'} />
            <DetailField label="IP address" value={inverter.ip_address || '—'} mono small />
          </div>
        </div>
      )}

      {/* ── Live KPIs ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPI icon={Zap}        label="AC Power"     value={`${fmt(latest.ac_power_kw, 1)} kW`}  color={ACCENT} />
        <KPI icon={Gauge}      label="AC Voltage"   value={`${fmt(latest.ac_voltage_v, 0)} V`}  color="#56CCF2" />
        <KPI icon={Gauge}      label="Efficiency"   value={`${fmt(latest.efficiency_pct, 1)}%`} color="#02C9A8" />
        <KPI icon={Thermometer} label="Temperature" value={`${fmt(latest.temperature_c, 1)}°C`} color="#E94B4B" />
      </div>

      {/* ── Charts ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title={`AC POWER — ${windowLabel(window)}`} subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}>
          <ReactECharts option={powerChart} style={{ height: 240 }} notMerge />
        </ChartCard>
        <ChartCard title={`AC VOLTAGE — ${windowLabel(window)}`}>
          <ReactECharts option={voltageChart} style={{ height: 240 }} notMerge />
        </ChartCard>
        <ChartCard title={`TEMPERATURE — ${windowLabel(window)}`}>
          <ReactECharts option={tempChart} style={{ height: 240 }} notMerge />
        </ChartCard>
      </div>
    </div>
  )
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function KPI({ icon: Icon, label, value, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${color}20` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 20 }}>{value}</div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>{label}</div>
      </div>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="text-white/60 font-bold" style={{ fontSize: 12 }}>{title}</div>
        {subtitle && <div className="text-white/30" style={{ fontSize: 11 }}>{subtitle}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  )
}

function Banner({ message, color }) {
  return (
    <div className="glass-card p-3 flex items-center gap-3" style={{ borderColor: `${color}4D`, background: `${color}14` }}>
      <AlertTriangle size={16} style={{ color }} />
      <span className="text-white/80" style={{ fontSize: 13 }}>{message}</span>
    </div>
  )
}

function DetailField({ label, value, mono, small }) {
  return (
    <div>
      <div className="text-white/40" style={{ fontSize: 11 }}>{label}</div>
      <div className={`text-white ${mono ? 'font-mono' : 'font-semibold'}`} style={{ fontSize: small ? 12 : 13 }}>
        {value ?? '—'}
      </div>
    </div>
  )
}

function windowLabel(w) {
  return w === '1h' ? 'last hour' : w === '24h' ? 'last 24 h' : w === '7d' ? 'last 7 days' : 'last 30 days'
}

function buildLineChart(rows, field, seriesName, unit, accent) {
  const points = (rows || []).map((r) => [r.ts || r.timestamp, Number(r[field] ?? 0)])
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
      name: unit,
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [{
      name: seriesName,
      type: 'line',
      data: points,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: accent, width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: accent + '4D' },
            { offset: 1, color: accent + '08' },
          ],
        },
      },
    }],
  }
}
