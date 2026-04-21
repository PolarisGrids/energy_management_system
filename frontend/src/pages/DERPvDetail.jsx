// W5 — PV consumer detail page (drill-down from fleet view).
//
// Reads:
//   * /der/telemetry?asset_id=...&window=  →  KPIs + recent power curve
//   * /der/{asset_id}/inverters             →  equipment list + health
//   * /der/{asset_id}/metrology?window=     →  daily generation / export rollup
//
// Route: /der/pv/:assetId
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, CheckCircle, Cpu,
  RefreshCw, Sun, TrendingUp, Zap,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'

import { derAPI } from '@/services/api'
import DERTimeRangePicker from '@/components/der/DERTimeRangePicker'

const POLL_MS = 30_000

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const achColor = (v) =>
  v == null ? '#ABC7FF' : v >= 80 ? '#02C9A8' : v >= 60 ? '#F59E0B' : '#E94B4B'

export default function DERPvDetail() {
  const { assetId } = useParams()
  const navigate = useNavigate()

  const [window, setWindow] = useState('24h')
  const [telemetry, setTelemetry] = useState({ assets: [], aggregate: [], banner: null })
  const [inverters, setInverters] = useState([])
  const [metrology, setMetrology] = useState({ daily: [], banner: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  // ── Data loads ────────────────────────────────────────────────────────
  const loadTelemetry = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await derAPI.telemetry({ asset_id: assetId, window })
      setTelemetry({
        assets: data.assets || [],
        aggregate: data.aggregate || [],
        banner: data.banner ?? null,
      })
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load telemetry.')
    } finally {
      setLoading(false)
    }
  }, [assetId, window])

  const loadInverters = useCallback(async () => {
    try {
      const { data } = await derAPI.listInverters(assetId)
      setInverters(data || [])
    } catch {
      setInverters([])
    }
  }, [assetId])

  const loadMetrology = useCallback(async () => {
    try {
      const { data } = await derAPI.metrology(assetId, {
        window: window === '1h' || window === '24h' ? '7d' : window === '7d' ? '7d' : '30d',
        daily_only: true,
      })
      setMetrology({ daily: data.daily || [], banner: data.banner ?? null })
    } catch {
      setMetrology({ daily: [], banner: null })
    }
  }, [assetId, window])

  useEffect(() => {
    loadTelemetry()
    loadInverters()
    loadMetrology()
    const id = setInterval(loadTelemetry, POLL_MS)
    return () => clearInterval(id)
  }, [loadTelemetry, loadInverters, loadMetrology])

  const asset = telemetry.assets[0]
  const consumer = asset?.consumer

  // ── Derived KPIs ──────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const aggKwh = (telemetry.aggregate || []).reduce(
      (s, p) => s + (p.total_kw ?? 0), 0
    ) / (window === '30d' ? 1 : 60) // 30d uses hourly buckets, others 1-min
    const eqHours =
      asset?.capacity_kw && aggKwh ? aggKwh / asset.capacity_kw : null
    return {
      output: asset?.current_output_kw,
      capacity: asset?.capacity_kw,
      generated: aggKwh,
      achievement: asset?.achievement_rate_pct,
      equivalentHours: eqHours,
    }
  }, [asset, telemetry.aggregate, window])

  const generationChart = useMemo(
    () => buildGenerationChart(telemetry.aggregate),
    [telemetry.aggregate],
  )

  const dailyChart = useMemo(
    () => buildDailyChart(metrology.daily),
    [metrology.daily],
  )

  // ── Empty / loading shells ────────────────────────────────────────────
  if (loading && !asset) {
    return (
      <div className="flex items-center justify-center py-16 text-white/40">
        <RefreshCw size={16} className="animate-spin mr-3" />
        Loading consumer detail…
      </div>
    )
  }

  if (!asset) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/der/pv')}
          className="btn-secondary inline-flex items-center gap-2"
          style={{ fontSize: 13, padding: '8px 14px' }}
        >
          <ArrowLeft size={13} /> Back to fleet
        </button>
        <div
          className="glass-card p-6 text-white/60 text-center"
          data-testid="der-pv-detail-missing"
        >
          {error || `No PV asset found with id "${assetId}".`}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-slide-up" data-testid="der-pv-detail-page">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <button
            onClick={() => navigate('/der/pv')}
            className="text-white/40 hover:text-white inline-flex items-center gap-1 mb-2"
            style={{ fontSize: 12 }}
          >
            <ArrowLeft size={11} /> Back to PV fleet
          </button>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>
            {consumer?.name || asset.name || asset.id}
          </h1>
          <div className="text-white/40 flex items-center gap-3 flex-wrap" style={{ fontSize: 12 }}>
            <span className="font-mono">{asset.id}</span>
            {asset.feeder_id && <span>· Feeder {asset.feeder_id}</span>}
            {asset.dtr_id && <span>· DTR {asset.dtr_id}</span>}
            {consumer?.account_no && <span>· Acct {consumer.account_no}</span>}
            {consumer?.tariff_code && <span>· Tariff {consumer.tariff_code}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DERTimeRangePicker value={window} onChange={setWindow} accent="#F59E0B" />
          <button
            onClick={loadTelemetry}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
            style={{ padding: '8px 16px', fontSize: 13 }}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {telemetry.banner && (
        <Banner color="#F59E0B" message={telemetry.banner} testid="der-pv-detail-banner" />
      )}
      {error && <Banner color="#E94B4B" message={error} />}

      {/* ── KPIs ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="der-pv-detail-kpis">
        <KPI
          icon={Zap} label="Current Output"
          value={fmt(kpis.output, 1)} unit="kW" color="#F59E0B"
        />
        <KPI
          icon={TrendingUp} label="Generated (window)"
          value={fmt(kpis.generated, 0)} unit="kWh" color="#02C9A8"
        />
        <KPI
          icon={CheckCircle} label="Achievement"
          value={kpis.achievement == null ? '—' : fmt(kpis.achievement, 1)}
          unit={kpis.achievement == null ? '' : '%'}
          color={achColor(kpis.achievement)}
        />
        <KPI
          icon={Sun} label="Equivalent Hours"
          value={fmt(kpis.equivalentHours, 2)} unit="h" color="#ABC7FF"
        />
      </div>

      {/* ── Charts ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title={`GENERATION CURVE — ${windowLabel(window)}`}
          subtitle={refreshedAt ? `updated ${refreshedAt.toLocaleTimeString('en-ZA')}` : null}
        >
          <ReactECharts option={generationChart} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard
          title="DAILY GENERATION — billing-grade rollup"
          subtitle={metrology.banner ? 'no metrology yet' : null}
        >
          <ReactECharts option={dailyChart} style={{ height: 260 }} notMerge />
        </ChartCard>
      </div>

      {/* ── Inverter health ─────────────────────────────────────────── */}
      <div data-testid="der-pv-detail-inverters">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-white font-bold flex items-center gap-2" style={{ fontSize: 15 }}>
            <Cpu size={15} /> Inverters
            <span className="text-white/40 font-normal" style={{ fontSize: 12 }}>
              ({inverters.length})
            </span>
          </h2>
        </div>
        {inverters.length === 0 ? (
          <div className="glass-card p-5 text-white/40 text-center" style={{ fontSize: 13 }}>
            No inverters registered for this consumer.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {inverters.map((inv) => (
              <InverterCard
                key={inv.id}
                inverter={inv}
                onClick={() => navigate(`/der/inverters/${encodeURIComponent(inv.id)}`)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Consumer card ───────────────────────────────────────────── */}
      {consumer && (
        <div className="glass-card p-5">
          <h2 className="text-white font-bold mb-3" style={{ fontSize: 15 }}>
            Consumer
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DetailField label="Name" value={consumer.name} />
            <DetailField label="Account" value={consumer.account_no || '—'} mono />
            <DetailField label="Tariff" value={consumer.tariff_code || '—'} />
            <DetailField label="Consumer ID" value={consumer.id} mono small />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Subcomponents ──────────────────────────────────────────────────────────

function KPI({ icon: Icon, label, value, unit, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: `${color}20` }}
      >
        <Icon size={18} style={{ color }} />
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 24 }}>
          {value}
          {unit && (
            <span className="text-white/40 font-medium ml-1" style={{ fontSize: 13 }}>
              {unit}
            </span>
          )}
        </div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 12 }}>
          {label}
        </div>
      </div>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="glass-card p-5 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="text-white/60 font-bold" style={{ fontSize: 12 }}>
          {title}
        </div>
        {subtitle && (
          <div className="text-white/30" style={{ fontSize: 11 }}>
            {subtitle}
          </div>
        )}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  )
}

function Banner({ message, color, testid }) {
  return (
    <div
      className="glass-card p-3 flex items-center gap-3"
      data-testid={testid}
      style={{ borderColor: `${color}4D`, background: `${color}14` }}
    >
      <AlertTriangle size={16} style={{ color }} />
      <span className="text-white/80" style={{ fontSize: 13 }}>
        {message}
      </span>
    </div>
  )
}

function InverterCard({ inverter, onClick }) {
  const status = (inverter.status || '').toLowerCase()
  const badgeClass =
    status === 'online'
      ? 'badge-ok'
      : status === 'fault'
      ? 'badge-critical'
      : status === 'maintenance'
      ? 'badge-medium'
      : 'badge-low'
  return (
    <div
      className="glass-card p-4 cursor-pointer hover:brightness-110 transition"
      data-testid={`der-inverter-card-${inverter.id}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && onClick) onClick() }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(245,158,11,0.15)' }}
          >
            <Cpu size={16} style={{ color: '#F59E0B' }} />
          </div>
          <div>
            <div className="text-white font-bold" style={{ fontSize: 13 }}>
              {inverter.manufacturer || 'Unknown'} · {inverter.model || '—'}
            </div>
            <div className="text-white/40 font-mono" style={{ fontSize: 11 }}>
              SN {inverter.serial_number || '—'}
            </div>
          </div>
        </div>
        <span className={badgeClass}>{inverter.status || 'unknown'}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <DetailField label="Rated AC" value={inverter.rated_ac_kw != null ? `${fmt(inverter.rated_ac_kw, 1)} kW` : '—'} />
        <DetailField label="Rated DC" value={inverter.rated_dc_kw != null ? `${fmt(inverter.rated_dc_kw, 1)} kW` : '—'} />
        <DetailField label="MPPT trackers" value={inverter.num_mppt_trackers ?? '—'} />
        <DetailField label="Phase" value={inverter.phase_config || '—'} />
        <DetailField label="Firmware" value={inverter.firmware_version || '—'} small />
        <DetailField label="Comms" value={inverter.comms_protocol || '—'} small />
      </div>
    </div>
  )
}

function DetailField({ label, value, mono, small }) {
  return (
    <div>
      <div className="text-white/40" style={{ fontSize: 10 }}>
        {label}
      </div>
      <div
        className={mono ? 'font-mono' : ''}
        style={{
          color: '#fff',
          fontSize: small ? 11 : 13,
          fontWeight: small ? 500 : 700,
        }}
      >
        {value}
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────

function windowLabel(w) {
  return w === '1h'
    ? 'last hour'
    : w === '24h'
    ? 'last 24 h'
    : w === '7d'
    ? 'last 7 days'
    : 'last 30 days'
}

function buildGenerationChart(aggregate) {
  const points = (aggregate || []).map((p) => [p.ts, p.total_kw])
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
      type: 'value', name: 'kW',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        type: 'line',
        data: points,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#F59E0B', width: 2 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245,158,11,0.4)' },
              { offset: 1, color: 'rgba(245,158,11,0.02)' },
            ],
          },
        },
      },
    ],
  }
}

function buildDailyChart(daily) {
  const rows = (daily || []).slice().sort((a, b) => (a.date < b.date ? -1 : 1))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.2)',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 11 },
      top: 0, right: 0,
    },
    grid: { left: 48, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: 'category', data: rows.map((r) => r.date.slice(5)),
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', name: 'kWh',
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        name: 'Generated',
        type: 'bar',
        stack: 'energy',
        data: rows.map((r) => Number(r.kwh_generated || 0).toFixed(1)),
        barMaxWidth: 14,
        itemStyle: { color: '#02C9A8', borderRadius: [4, 4, 0, 0] },
      },
      {
        name: 'Exported',
        type: 'bar',
        stack: 'export',
        data: rows.map((r) => Number(r.kwh_exported || 0).toFixed(1)),
        barMaxWidth: 14,
        itemStyle: { color: '#56CCF2', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
}
