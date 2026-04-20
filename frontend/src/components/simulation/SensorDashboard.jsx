/**
 * SensorDashboard — Transformer sensor monitoring visualization for REQ-25.
 * Renders gauge charts, status indicators, and trend lines for DCU-connected sensors.
 */
import { useState, useEffect, useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { Thermometer, Droplets, Activity, Waves, AlertTriangle, CheckCircle } from 'lucide-react'
import { sensorsAPI } from '@/services/api'

// ─── Sensor metadata ─────────────────────────────────────────────────────────

const SENSOR_META = {
  winding_temp:    { label: 'Winding Temp',   icon: Thermometer, color: '#EF4444', unit: 'degC', displayUnit: '\u00B0C' },
  oil_temp:        { label: 'Oil Temp',        icon: Thermometer, color: '#F97316', unit: 'degC', displayUnit: '\u00B0C' },
  oil_level:       { label: 'Oil Level',       icon: Droplets,    color: '#3B82F6', unit: '%',    displayUnit: '%' },
  vibration:       { label: 'Vibration',       icon: Activity,    color: '#8B5CF6', unit: 'mm/s', displayUnit: 'mm/s' },
  humidity:        { label: 'Humidity',        icon: Waves,       color: '#06B6D4', unit: '%',    displayUnit: '%' },
  current_phase_a: { label: 'Phase A Current', icon: Activity,    color: '#F59E0B', unit: 'A',    displayUnit: 'A' },
  current_phase_b: { label: 'Phase B Current', icon: Activity,    color: '#10B981', unit: 'A',    displayUnit: 'A' },
  current_phase_c: { label: 'Phase C Current', icon: Activity,    color: '#EC4899', unit: 'A',    displayUnit: 'A' },
}

const PRIMARY_SENSORS = ['winding_temp', 'oil_temp', 'oil_level', 'vibration']

const STATUS_COLOR = {
  normal:   '#02C9A8',
  warning:  '#F59E0B',
  critical: '#E94B4B',
  offline:  '#6B7280',
}

// ─── Gauge chart option builder ──────────────────────────────────────────────

function buildGaugeOption(value, min, max, warning, critical, label, unit, sensorType) {
  // For oil_level, thresholds are inverted (warning when LOW)
  const isInverted = sensorType === 'oil_level'

  let color
  if (isInverted) {
    color = value <= critical ? '#E94B4B' : value <= warning ? '#F59E0B' : '#02C9A8'
  } else {
    color = value >= critical ? '#E94B4B' : value >= warning ? '#F59E0B' : '#02C9A8'
  }

  return {
    series: [{
      type: 'gauge',
      startAngle: 220,
      endAngle: -40,
      min,
      max,
      radius: '100%',
      progress: { show: true, width: 10, itemStyle: { color } },
      axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(255,255,255,0.06)']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      anchor: { show: false },
      title: { show: true, offsetCenter: [0, '65%'], fontSize: 10, color: 'rgba(255,255,255,0.4)' },
      detail: {
        valueAnimation: true,
        fontSize: 22,
        fontWeight: 'bold',
        offsetCenter: [0, '25%'],
        color: 'white',
        formatter: `{value}`,
      },
      data: [{ value: Math.round(value * 10) / 10, name: `${label} (${unit})` }],
    }],
  }
}

// ─── Trend chart option builder ──────────────────────────────────────────────

function buildTrendOption(history, warning, critical, color, unit, sensorType) {
  if (!history || history.length === 0) return null

  const times = history.map(h => {
    const d = new Date(h.timestamp)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  })
  const values = history.map(h => h.value)

  const markLines = []
  if (warning != null) markLines.push({ yAxis: warning, label: { formatter: 'WARN', fontSize: 9, color: '#F59E0B' }, lineStyle: { color: '#F59E0B', type: 'dashed', width: 1 } })
  if (critical != null) markLines.push({ yAxis: critical, label: { formatter: 'CRIT', fontSize: 9, color: '#E94B4B' }, lineStyle: { color: '#E94B4B', type: 'dashed', width: 1 } })

  return {
    grid: { top: 8, right: 8, bottom: 24, left: 40 },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { fontSize: 9, color: 'rgba(255,255,255,0.3)', interval: Math.floor(times.length / 6) },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 9, color: 'rgba(255,255,255,0.3)' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
    },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '30' }, { offset: 1, color: color + '05' }] } },
      markLine: markLines.length > 0 ? { silent: true, symbol: 'none', data: markLines } : undefined,
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,20,50,0.9)',
      borderColor: 'rgba(171,199,255,0.15)',
      textStyle: { color: 'white', fontSize: 11 },
      formatter: (params) => `${params[0].axisValue}<br/>${params[0].value} ${unit}`,
    },
  }
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function SensorDashboard({ transformerId, networkState, scenarioParams }) {
  const [sensors, setSensors] = useState([])
  const [historyMap, setHistoryMap] = useState({})
  const [expandedSensor, setExpandedSensor] = useState(null)

  const sensorValues = networkState?.sensor_values || {}
  const loadingPercent = networkState?.loading_percent ?? 0

  // Fetch sensors from API on mount
  useEffect(() => {
    if (!transformerId) return
    sensorsAPI.byTransformer(transformerId)
      .then(({ data }) => setSensors(data))
      .catch(() => {})
  }, [transformerId])

  // Fetch history for expanded sensor
  useEffect(() => {
    if (!expandedSensor) return
    if (historyMap[expandedSensor]) return
    sensorsAPI.history(expandedSensor, 24)
      .then(({ data }) => setHistoryMap(prev => ({ ...prev, [expandedSensor]: data })))
      .catch(() => {})
  }, [expandedSensor])

  // Build effective sensor data from network_state (real-time from simulation)
  const effectiveSensors = useMemo(() => {
    if (Object.keys(sensorValues).length === 0) return sensors

    return sensors.map(s => {
      const liveVal = sensorValues[s.sensor_type]
      if (liveVal == null) return s

      let status = 'normal'
      if (s.sensor_type === 'oil_level') {
        if (s.threshold_critical && liveVal <= s.threshold_critical) status = 'critical'
        else if (s.threshold_warning && liveVal <= s.threshold_warning) status = 'warning'
      } else {
        if (s.threshold_critical && liveVal >= s.threshold_critical) status = 'critical'
        else if (s.threshold_warning && liveVal >= s.threshold_warning) status = 'warning'
      }

      return { ...s, value: liveVal, status }
    })
  }, [sensors, sensorValues])

  const primarySensors = effectiveSensors.filter(s => PRIMARY_SENSORS.includes(s.sensor_type))
  const phaseSensors = effectiveSensors.filter(s => s.sensor_type.startsWith('current_phase'))
  const otherSensors = effectiveSensors.filter(s => !PRIMARY_SENSORS.includes(s.sensor_type) && !s.sensor_type.startsWith('current_phase'))

  const warningCount = effectiveSensors.filter(s => s.status === 'warning').length
  const criticalCount = effectiveSensors.filter(s => s.status === 'critical').length

  const txName = scenarioParams?.transformer_name || 'T-005'
  const txCapacity = scenarioParams?.transformer_capacity_kva || 315
  const voltageClass = scenarioParams?.voltage_class || '11kV/400V'

  return (
    <div className="space-y-4">
      {/* Transformer overview header */}
      <div className="glass-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(249,115,22,0.15)' }}>
              <Thermometer size={18} style={{ color: '#F97316' }} />
            </div>
            <div>
              <div className="text-white font-bold" style={{ fontSize: 15 }}>
                Transformer {txName} — DCU Sensor Array
              </div>
              <div className="text-white/40" style={{ fontSize: 12 }}>
                {voltageClass} | {txCapacity} kVA | 8 sensors via DCU
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {criticalCount > 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
                style={{ background: 'rgba(233,75,75,0.15)', border: '1px solid rgba(233,75,75,0.3)' }}>
                <AlertTriangle size={12} style={{ color: '#E94B4B' }} />
                <span className="text-xs font-bold" style={{ color: '#E94B4B' }}>{criticalCount} CRITICAL</span>
              </div>
            )}
            {warningCount > 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
                style={{ background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)' }}>
                <AlertTriangle size={12} style={{ color: '#F59E0B' }} />
                <span className="text-xs font-bold" style={{ color: '#F59E0B' }}>{warningCount} WARNING</span>
              </div>
            )}
            {criticalCount === 0 && warningCount === 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
                style={{ background: 'rgba(2,201,168,0.15)', border: '1px solid rgba(2,201,168,0.3)' }}>
                <CheckCircle size={12} style={{ color: '#02C9A8' }} />
                <span className="text-xs font-bold" style={{ color: '#02C9A8' }}>ALL NORMAL</span>
              </div>
            )}
          </div>
        </div>

        {/* Loading bar */}
        <div>
          <div className="flex justify-between mb-1">
            <span className="text-white/40" style={{ fontSize: 10 }}>TRANSFORMER LOADING</span>
            <span className="font-bold" style={{
              fontSize: 12,
              color: loadingPercent >= 90 ? '#E94B4B' : loadingPercent >= 75 ? '#F59E0B' : '#02C9A8',
            }}>{loadingPercent.toFixed(1)}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-white/5">
            <div className="h-2 rounded-full transition-all duration-700" style={{
              width: `${Math.min(loadingPercent, 100)}%`,
              background: loadingPercent >= 90 ? '#E94B4B' : loadingPercent >= 75 ? '#F59E0B' : '#02C9A8',
            }} />
          </div>
        </div>
      </div>

      {/* Primary sensor gauges */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {primarySensors.map(sensor => {
          const meta = SENSOR_META[sensor.sensor_type] || {}
          const Icon = meta.icon || Activity
          const gaugeMin = sensor.sensor_type === 'oil_level' ? 60 : 0
          const gaugeMax = sensor.sensor_type === 'winding_temp' ? 120
            : sensor.sensor_type === 'oil_temp' ? 100
            : sensor.sensor_type === 'oil_level' ? 100
            : sensor.sensor_type === 'vibration' ? 4 : 100

          return (
            <div
              key={sensor.id}
              className="glass-card p-3 cursor-pointer transition-all hover:border-white/10"
              style={{
                borderColor: sensor.status === 'critical' ? 'rgba(233,75,75,0.4)'
                  : sensor.status === 'warning' ? 'rgba(245,158,11,0.4)'
                  : 'rgba(171,199,255,0.06)',
              }}
              onClick={() => setExpandedSensor(expandedSensor === sensor.id ? null : sensor.id)}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <Icon size={12} style={{ color: meta.color }} />
                  <span className="text-white/50 font-medium" style={{ fontSize: 10 }}>{meta.label}</span>
                </div>
                <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLOR[sensor.status] }} />
              </div>
              <ReactECharts
                option={buildGaugeOption(
                  sensor.value, gaugeMin, gaugeMax,
                  sensor.threshold_warning, sensor.threshold_critical,
                  meta.label, meta.displayUnit, sensor.sensor_type
                )}
                style={{ height: 120 }}
                opts={{ renderer: 'canvas' }}
              />
              <div className="text-center">
                <span className="text-white/30" style={{ fontSize: 9 }}>
                  Warn: {sensor.threshold_warning}{meta.displayUnit} | Crit: {sensor.threshold_critical}{meta.displayUnit}
                </span>
              </div>

              {/* Trend chart if expanded */}
              {expandedSensor === sensor.id && historyMap[sensor.id] && (
                <div className="mt-3 pt-3 border-t" style={{ borderColor: 'rgba(171,199,255,0.08)' }}>
                  <div className="text-white/40 font-bold mb-1" style={{ fontSize: 9 }}>24H TREND</div>
                  <ReactECharts
                    option={buildTrendOption(
                      historyMap[sensor.id].history,
                      sensor.threshold_warning, sensor.threshold_critical,
                      meta.color, meta.displayUnit, sensor.sensor_type
                    )}
                    style={{ height: 100 }}
                    opts={{ renderer: 'canvas' }}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Phase currents + other sensors */}
      {(phaseSensors.length > 0 || otherSensors.length > 0) && (
        <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
          {[...phaseSensors, ...otherSensors].map(sensor => {
            const meta = SENSOR_META[sensor.sensor_type] || { label: sensor.sensor_type, color: '#ABC7FF', displayUnit: sensor.unit }
            return (
              <div key={sensor.id} className="glass-card p-3">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATUS_COLOR[sensor.status] }} />
                  <span className="text-white/40 font-medium" style={{ fontSize: 9 }}>{meta.label}</span>
                </div>
                <div className="text-white font-bold" style={{ fontSize: 18 }}>
                  {sensor.value?.toFixed(1)}
                  <span className="text-white/30 font-normal ml-1" style={{ fontSize: 11 }}>{meta.displayUnit}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
