/**
 * SensorMonitoring — Standalone page for monitoring all transformer sensor assets (REQ-25).
 * Grid of transformer cards with drill-down to detailed sensor views and trend charts.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Thermometer, Droplets, Activity, Waves, AlertTriangle, CheckCircle,
  RefreshCw, ChevronRight, ArrowLeft, Settings,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { sensorsAPI } from '@/services/api'

// ─── Constants ───────────────────────────────────────────────────────────────

const SENSOR_META = {
  winding_temp:    { label: 'Winding Temp',   icon: Thermometer, color: '#EF4444', displayUnit: '\u00B0C' },
  oil_temp:        { label: 'Oil Temp',        icon: Thermometer, color: '#F97316', displayUnit: '\u00B0C' },
  oil_level:       { label: 'Oil Level',       icon: Droplets,    color: '#3B82F6', displayUnit: '%' },
  vibration:       { label: 'Vibration',       icon: Activity,    color: '#8B5CF6', displayUnit: 'mm/s' },
  humidity:        { label: 'Humidity',        icon: Waves,       color: '#06B6D4', displayUnit: '%' },
  current_phase_a: { label: 'Phase A',         icon: Activity,    color: '#F59E0B', displayUnit: 'A' },
  current_phase_b: { label: 'Phase B',         icon: Activity,    color: '#10B981', displayUnit: 'A' },
  current_phase_c: { label: 'Phase C',         icon: Activity,    color: '#EC4899', displayUnit: 'A' },
}

const STATUS_CONFIG = {
  normal:   { color: '#02C9A8', bg: 'rgba(2,201,168,0.12)',   label: 'Normal' },
  warning:  { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)',  label: 'Warning' },
  critical: { color: '#E94B4B', bg: 'rgba(233,75,75,0.12)',   label: 'Critical' },
  offline:  { color: '#6B7280', bg: 'rgba(107,114,128,0.12)', label: 'Offline' },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function groupSensorsByTransformer(sensors) {
  const map = {}
  for (const s of sensors) {
    if (!map[s.transformer_id]) {
      map[s.transformer_id] = { transformerId: s.transformer_id, sensors: [], name: null }
    }
    map[s.transformer_id].sensors.push(s)
    // Extract transformer name from sensor name (e.g., "Winding Temperature -- TX-1201")
    if (!map[s.transformer_id].name) {
      const parts = s.name.split('\u2014')
      if (parts.length > 1) map[s.transformer_id].name = parts[parts.length - 1].trim()
    }
  }
  return Object.values(map)
}

function getTransformerStatus(sensors) {
  if (sensors.some(s => s.status === 'critical')) return 'critical'
  if (sensors.some(s => s.status === 'warning')) return 'warning'
  return 'normal'
}

function buildDetailTrendOption(history, warning, critical, color, displayUnit, sensorType) {
  if (!history || history.length === 0) return null

  const times = history.map(h => {
    const d = new Date(h.timestamp)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  })
  const values = history.map(h => h.value)

  const markLines = []
  if (warning != null) {
    markLines.push({
      yAxis: warning,
      label: { formatter: 'WARNING', fontSize: 10, color: '#F59E0B', position: 'insideEndTop' },
      lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.5 },
    })
  }
  if (critical != null) {
    markLines.push({
      yAxis: critical,
      label: { formatter: 'CRITICAL', fontSize: 10, color: '#E94B4B', position: 'insideEndTop' },
      lineStyle: { color: '#E94B4B', type: 'dashed', width: 1.5 },
    })
  }

  return {
    grid: { top: 16, right: 12, bottom: 30, left: 48 },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { fontSize: 10, color: 'rgba(255,255,255,0.3)', interval: Math.floor(times.length / 8) },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: 'rgba(255,255,255,0.3)' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
    },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2.5, color },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: color + '25' }, { offset: 1, color: color + '03' }],
        },
      },
      markLine: markLines.length > 0 ? { silent: true, symbol: 'none', data: markLines } : undefined,
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.95)',
      borderColor: 'rgba(171,199,255,0.15)',
      textStyle: { color: 'white', fontSize: 12 },
      formatter: (params) => `${params[0].axisValue}<br/><b>${params[0].value}</b> ${displayUnit}`,
    },
  }
}

function buildGaugeOption(value, min, max, warning, critical, color, sensorType) {
  const isInverted = sensorType === 'oil_level'
  let gaugeColor
  if (isInverted) {
    gaugeColor = value <= critical ? '#E94B4B' : value <= warning ? '#F59E0B' : '#02C9A8'
  } else {
    gaugeColor = value >= critical ? '#E94B4B' : value >= warning ? '#F59E0B' : '#02C9A8'
  }

  return {
    series: [{
      type: 'gauge',
      startAngle: 220,
      endAngle: -40,
      min, max,
      radius: '100%',
      progress: { show: true, width: 12, itemStyle: { color: gaugeColor } },
      axisLine: { lineStyle: { width: 12, color: [[1, 'rgba(255,255,255,0.04)']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      anchor: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        fontSize: 28,
        fontWeight: 'bold',
        offsetCenter: [0, '15%'],
        color: 'white',
        formatter: '{value}',
      },
      data: [{ value: Math.round(value * 10) / 10 }],
    }],
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function TransformerCard({ group, onSelect }) {
  const overallStatus = getTransformerStatus(group.sensors)
  const cfg = STATUS_CONFIG[overallStatus]
  const winding = group.sensors.find(s => s.sensor_type === 'winding_temp')
  const oil = group.sensors.find(s => s.sensor_type === 'oil_temp')
  const oilLevel = group.sensors.find(s => s.sensor_type === 'oil_level')
  const vibration = group.sensors.find(s => s.sensor_type === 'vibration')

  return (
    <div
      className="glass-card p-4 cursor-pointer transition-all hover:border-white/15"
      style={{ borderColor: overallStatus !== 'normal' ? cfg.color + '40' : undefined }}
      onClick={() => onSelect(group)}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: cfg.bg }}>
            <Thermometer size={14} style={{ color: cfg.color }} />
          </div>
          <div>
            <div className="text-white font-bold text-sm">{group.name || `TX-${group.transformerId}`}</div>
            <div className="text-white/30" style={{ fontSize: 10 }}>{group.sensors.length} sensors</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded text-xs font-bold"
            style={{ background: cfg.bg, color: cfg.color }}>
            {cfg.label.toUpperCase()}
          </span>
          <ChevronRight size={14} className="text-white/20" />
        </div>
      </div>

      {/* Quick sensor readouts */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { s: winding, label: 'Winding', unit: '\u00B0C' },
          { s: oil, label: 'Oil Temp', unit: '\u00B0C' },
          { s: oilLevel, label: 'Oil Lvl', unit: '%' },
          { s: vibration, label: 'Vibration', unit: 'mm/s' },
        ].map(({ s, label, unit }, i) => (
          <div key={i} className="bg-white/3 rounded-lg p-2 text-center">
            <div className="text-white/30" style={{ fontSize: 9 }}>{label}</div>
            <div className="font-bold" style={{
              fontSize: 14,
              color: s ? (STATUS_CONFIG[s.status]?.color || 'white') : 'rgba(255,255,255,0.2)',
            }}>
              {s ? s.value?.toFixed(1) : '--'}
            </div>
            <div className="text-white/20" style={{ fontSize: 8 }}>{unit}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Detail View ─────────────────────────────────────────────────────────────

function TransformerDetail({ group, onBack }) {
  const [historyMap, setHistoryMap] = useState({})
  const [loadingHistory, setLoadingHistory] = useState(true)

  useEffect(() => {
    setLoadingHistory(true)
    const primaryIds = group.sensors
      .filter(s => ['winding_temp', 'oil_temp', 'oil_level', 'vibration'].includes(s.sensor_type))
      .map(s => s.id)

    Promise.all(
      primaryIds.map(id =>
        sensorsAPI.history(id, 24)
          .then(({ data }) => ({ id, data }))
          .catch(() => null)
      )
    ).then(results => {
      const map = {}
      for (const r of results) {
        if (r) map[r.id] = r.data
      }
      setHistoryMap(map)
      setLoadingHistory(false)
    })
  }, [group.transformerId])

  const overallStatus = getTransformerStatus(group.sensors)
  const cfg = STATUS_CONFIG[overallStatus]

  const primarySensors = group.sensors.filter(s =>
    ['winding_temp', 'oil_temp', 'oil_level', 'vibration'].includes(s.sensor_type)
  )
  const phaseSensors = group.sensors.filter(s => s.sensor_type.startsWith('current_phase'))
  const otherSensors = group.sensors.filter(s =>
    !['winding_temp', 'oil_temp', 'oil_level', 'vibration'].includes(s.sensor_type) &&
    !s.sensor_type.startsWith('current_phase')
  )

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="btn-secondary p-2">
            <ArrowLeft size={14} />
          </button>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: cfg.bg }}>
            <Thermometer size={18} style={{ color: cfg.color }} />
          </div>
          <div>
            <div className="text-white font-bold" style={{ fontSize: 16 }}>
              {group.name || `Transformer ${group.transformerId}`} — Sensor Detail
            </div>
            <div className="text-white/40" style={{ fontSize: 12 }}>
              11kV/400V | {group.sensors.length} DCU-connected sensors | Real-time monitoring
            </div>
          </div>
          <div className="ml-auto">
            <span className="px-3 py-1.5 rounded-lg text-xs font-bold"
              style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}30` }}>
              {cfg.label.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Primary sensors with gauges + trends */}
      <div className="grid grid-cols-2 gap-4">
        {primarySensors.map(sensor => {
          const meta = SENSOR_META[sensor.sensor_type] || {}
          const history = historyMap[sensor.id]
          const gaugeMin = sensor.sensor_type === 'oil_level' ? 60 : 0
          const gaugeMax = sensor.sensor_type === 'winding_temp' ? 120
            : sensor.sensor_type === 'oil_temp' ? 100
            : sensor.sensor_type === 'oil_level' ? 100
            : 4

          return (
            <div key={sensor.id} className="glass-card p-4" style={{
              borderColor: sensor.status !== 'normal' ? (STATUS_CONFIG[sensor.status]?.color + '40') : undefined,
            }}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {meta.icon && <meta.icon size={14} style={{ color: meta.color }} />}
                  <span className="text-white font-bold text-sm">{meta.label}</span>
                </div>
                <span className="px-2 py-0.5 rounded text-xs font-bold"
                  style={{
                    background: STATUS_CONFIG[sensor.status]?.bg,
                    color: STATUS_CONFIG[sensor.status]?.color,
                  }}>
                  {sensor.status?.toUpperCase()}
                </span>
              </div>

              <div className="flex gap-3">
                {/* Gauge */}
                <div style={{ width: 130, height: 130, flexShrink: 0 }}>
                  <ReactECharts
                    option={buildGaugeOption(
                      sensor.value, gaugeMin, gaugeMax,
                      sensor.threshold_warning, sensor.threshold_critical,
                      meta.color, sensor.sensor_type
                    )}
                    style={{ height: 130, width: 130 }}
                    opts={{ renderer: 'canvas' }}
                  />
                </div>

                {/* Trend */}
                <div className="flex-1">
                  {loadingHistory ? (
                    <div className="flex items-center justify-center h-full text-white/20 text-xs">
                      <RefreshCw size={12} className="animate-spin mr-2" /> Loading trend...
                    </div>
                  ) : history ? (
                    <ReactECharts
                      option={buildDetailTrendOption(
                        history.history,
                        sensor.threshold_warning, sensor.threshold_critical,
                        meta.color, meta.displayUnit, sensor.sensor_type
                      )}
                      style={{ height: 130 }}
                      opts={{ renderer: 'canvas' }}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-white/20 text-xs">
                      No trend data available
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-between mt-2 pt-2 border-t" style={{ borderColor: 'rgba(171,199,255,0.06)' }}>
                <span className="text-white/30" style={{ fontSize: 10 }}>
                  Warning: {sensor.threshold_warning} {meta.displayUnit}
                </span>
                <span className="text-white/30" style={{ fontSize: 10 }}>
                  Critical: {sensor.threshold_critical} {meta.displayUnit}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Phase currents */}
      {phaseSensors.length > 0 && (
        <div className="glass-card p-4">
          <div className="text-white/40 font-bold mb-3" style={{ fontSize: 11 }}>PHASE CURRENTS</div>
          <div className="grid grid-cols-3 gap-4">
            {phaseSensors.map(sensor => {
              const meta = SENSOR_META[sensor.sensor_type] || {}
              const pct = sensor.threshold_critical ? (sensor.value / sensor.threshold_critical * 100) : 0
              return (
                <div key={sensor.id} className="bg-white/3 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white/50 font-medium" style={{ fontSize: 11 }}>{meta.label}</span>
                    <span className="w-2 h-2 rounded-full" style={{ background: STATUS_CONFIG[sensor.status]?.color }} />
                  </div>
                  <div className="text-white font-black" style={{ fontSize: 24 }}>
                    {sensor.value?.toFixed(1)}
                    <span className="text-white/30 font-normal ml-1" style={{ fontSize: 12 }}>A</span>
                  </div>
                  <div className="mt-2">
                    <div className="w-full h-1.5 rounded-full bg-white/5">
                      <div className="h-1.5 rounded-full transition-all" style={{
                        width: `${Math.min(pct, 100)}%`,
                        background: meta.color,
                      }} />
                    </div>
                    <div className="text-white/20 mt-1" style={{ fontSize: 9 }}>
                      {pct.toFixed(0)}% of rated ({sensor.threshold_critical} A)
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Other sensors */}
      {otherSensors.length > 0 && (
        <div className="glass-card p-4">
          <div className="text-white/40 font-bold mb-3" style={{ fontSize: 11 }}>ADDITIONAL SENSORS</div>
          <div className="grid grid-cols-3 gap-3">
            {otherSensors.map(sensor => {
              const meta = SENSOR_META[sensor.sensor_type] || { label: sensor.sensor_type, displayUnit: sensor.unit, color: '#ABC7FF' }
              return (
                <div key={sensor.id} className="bg-white/3 rounded-lg p-3">
                  <span className="text-white/40" style={{ fontSize: 10 }}>{meta.label}</span>
                  <div className="text-white font-bold mt-1" style={{ fontSize: 18 }}>
                    {sensor.value?.toFixed(1)}
                    <span className="text-white/30 font-normal ml-1" style={{ fontSize: 11 }}>{meta.displayUnit}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function SensorMonitoring() {
  const [sensors, setSensors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState(null)

  const fetchSensors = useCallback(async () => {
    try {
      setError(null)
      const { data } = await sensorsAPI.list()
      setSensors(data)
    } catch (err) {
      setError('Failed to load sensor data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSensors()
    // Poll every 10 seconds for real-time feel
    const interval = setInterval(fetchSensors, 10000)
    return () => clearInterval(interval)
  }, [fetchSensors])

  const groups = groupSensorsByTransformer(sensors)

  const totalSensors = sensors.length
  const criticalCount = sensors.filter(s => s.status === 'critical').length
  const warningCount = sensors.filter(s => s.status === 'warning').length
  const normalCount = sensors.filter(s => s.status === 'normal').length

  if (selectedGroup) {
    // Update selected group with latest sensor data
    const updatedGroup = groups.find(g => g.transformerId === selectedGroup.transformerId)
    return (
      <div className="animate-slide-up">
        <TransformerDetail
          group={updatedGroup || selectedGroup}
          onBack={() => setSelectedGroup(null)}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Transformer Sensor Monitoring</h1>
          <p className="text-white/40" style={{ fontSize: 13 }}>
            DCU-connected sensors across instrumented transformers
          </p>
        </div>
        <button onClick={fetchSensors} className="btn-secondary py-2 px-4">
          <RefreshCw size={14} className={`inline mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <div className="metric-card">
          <div className="text-white/40 mb-1" style={{ fontSize: 10 }}>TOTAL SENSORS</div>
          <div className="text-white font-black" style={{ fontSize: 28 }}>{totalSensors}</div>
          <div style={{ fontSize: 11, color: '#ABC7FF', marginTop: 4 }}>{groups.length} transformers</div>
        </div>
        <div className="metric-card">
          <div className="text-white/40 mb-1" style={{ fontSize: 10 }}>NORMAL</div>
          <div className="font-black" style={{ fontSize: 28, color: '#02C9A8' }}>{normalCount}</div>
          <div className="flex items-center gap-1 mt-1">
            <CheckCircle size={10} style={{ color: '#02C9A8' }} />
            <span style={{ fontSize: 11, color: '#02C9A8' }}>Within thresholds</span>
          </div>
        </div>
        <div className="metric-card">
          <div className="text-white/40 mb-1" style={{ fontSize: 10 }}>WARNING</div>
          <div className="font-black" style={{ fontSize: 28, color: '#F59E0B' }}>{warningCount}</div>
          <div className="flex items-center gap-1 mt-1">
            <AlertTriangle size={10} style={{ color: '#F59E0B' }} />
            <span style={{ fontSize: 11, color: '#F59E0B' }}>Approaching limits</span>
          </div>
        </div>
        <div className="metric-card">
          <div className="text-white/40 mb-1" style={{ fontSize: 10 }}>CRITICAL</div>
          <div className="font-black" style={{ fontSize: 28, color: '#E94B4B' }}>{criticalCount}</div>
          <div className="flex items-center gap-1 mt-1">
            <AlertTriangle size={10} style={{ color: '#E94B4B' }} />
            <span style={{ fontSize: 11, color: '#E94B4B' }}>Action required</span>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="glass-card p-4 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 14 }}>{error}</span>
          <button onClick={fetchSensors} className="btn-secondary ml-auto" style={{ padding: '6px 14px', fontSize: 12 }}>
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && sensors.length === 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-40 rounded-card" />
          ))}
        </div>
      ) : (
        /* Transformer cards grid */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map(group => (
            <TransformerCard key={group.transformerId} group={group} onSelect={setSelectedGroup} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && groups.length === 0 && !error && (
        <div className="glass-card p-12 flex items-center justify-center">
          <div className="text-center text-white/30">
            <Thermometer size={40} className="mx-auto mb-3 opacity-30" />
            <div className="font-bold">No sensor data available</div>
            <div className="text-sm mt-1">Run the seed script to add transformer sensors</div>
          </div>
        </div>
      )}
    </div>
  )
}
