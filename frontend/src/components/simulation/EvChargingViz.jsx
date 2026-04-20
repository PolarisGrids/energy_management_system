import { useState, useEffect } from 'react'
import { Zap, Thermometer, Car, Plug, Activity } from 'lucide-react'
import { useToast } from '@/components/ui/Toast'

/**
 * EvChargingViz — TX-07 fast-charge hub visualization for REQ-22.
 * Renders a KPI header, transformer loading bar with amber/red zones, a 4-bay strip
 * with SoC bars and OCPP setpoint line, a 4-hour demand forecast bar chart, and
 * three OCPP command buttons.
 */

const FORECAST_BUCKETS = 16 // 15-min × 4h

function loadingColor(pct, t1 = 80, t2 = 100) {
  if (pct == null) return '#6B7280'
  if (pct >= t2) return '#E94B4B'
  if (pct >= t1) return '#F59E0B'
  return '#02C9A8'
}

function tempColor(t, warn, alarm, trip) {
  if (t == null) return '#6B7280'
  if (t >= trip)  return '#E94B4B'
  if (t >= alarm) return '#F59E0B'
  if (t >= warn)  return '#ABC7FF'
  return '#02C9A8'
}

function stationPill(state) {
  const map = {
    normal:     { bg: '#02C9A820', fg: '#02C9A8', label: 'NORMAL' },
    overload:   { bg: '#E94B4B20', fg: '#E94B4B', label: 'OVERLOAD' },
    curtailed:  { bg: '#F59E0B20', fg: '#F59E0B', label: 'CURTAILED' },
  }
  return map[state] || { bg: 'rgba(255,255,255,0.06)', fg: 'rgba(255,255,255,0.5)', label: (state || 'IDLE').toUpperCase() }
}

export default function EvChargingViz({ scenario, currentStep, networkState, onCommand }) {
  const params = scenario?.parameters || {}
  const tempWarn  = params.winding_temp_warn_c ?? 80
  const tempAlarm = params.winding_temp_alarm_c ?? 90
  const tempTrip  = params.winding_temp_trip_c ?? 105

  const txLoadingPct     = networkState?.tx_loading_pct ?? null
  const windingTempC     = networkState?.winding_temp_c ?? null
  const stationKw        = networkState?.station_kw ?? 0
  const activeSessions   = networkState?.active_sessions ?? 0
  const stationStatus    = networkState?.station_status || 'normal'
  const bays             = networkState?.bays || []
  const forecast         = networkState?.forecast || []
  const stationSetpointKw = networkState?.station_setpoint_kw ?? null

  const pill = stationPill(stationStatus)
  const toast = useToast()

  // Heartbeat tick for tiny animations (keeps rhythm consistent with other viz)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 800)
    return () => clearInterval(id)
  }, [])

  const issue = (cmd, label) => {
    if (onCommand) onCommand(cmd)
    else if (toast?.info) toast.info(`OCPP: ${label}`, 'Demo preview — command not dispatched.')
  }

  // Compute forecast scale
  const forecastMax = Math.max(
    ...forecast.map(f => Math.max(f?.predicted_kw ?? 0, f?.curtailed_kw ?? 0)),
    1,
  )

  return (
    <div className="glass-card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'rgba(2,201,168,0.15)' }}>
            <Zap size={18} style={{ color: '#02C9A8' }} />
          </div>
          <div>
            <div className="text-white font-black" style={{ fontSize: 15 }}>
              TX-07 Fast-Charge Hub
            </div>
            <div className="text-white/40" style={{ fontSize: 11 }}>
              {params.transformer_name || 'TX-07'} · {params.rated_kva || 500} kVA · {bays.length || 4} bays
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {currentStep != null && (
            <div className="text-right">
              <div className="text-white/40 font-bold" style={{ fontSize: 10 }}>STEP</div>
              <div className="text-white font-black" style={{ fontSize: 14 }}>#{currentStep}</div>
            </div>
          )}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
            style={{ background: pill.bg, border: `1px solid ${pill.fg}40` }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: pill.fg }} />
            <span className="font-black" style={{ fontSize: 11, color: pill.fg }}>{pill.label}</span>
          </div>
        </div>
      </div>

      {/* 4 KPI cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.03)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Activity size={11} style={{ color: loadingColor(txLoadingPct) }} />
            <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>TX LOADING</span>
          </div>
          <div className="font-black" style={{ fontSize: 22, color: loadingColor(txLoadingPct) }}>
            {txLoadingPct != null ? `${txLoadingPct.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.03)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Thermometer size={11} style={{ color: tempColor(windingTempC, tempWarn, tempAlarm, tempTrip) }} />
            <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>WINDING TEMP</span>
          </div>
          <div className="font-black" style={{ fontSize: 22, color: tempColor(windingTempC, tempWarn, tempAlarm, tempTrip) }}>
            {windingTempC != null ? `${windingTempC.toFixed(1)}` : '—'}
            <span className="text-white/40 font-normal ml-1" style={{ fontSize: 12 }}>°C</span>
          </div>
        </div>
        <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.03)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Zap size={11} style={{ color: '#ABC7FF' }} />
            <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>STATION</span>
          </div>
          <div className="text-white font-black" style={{ fontSize: 22 }}>
            {stationKw.toFixed(0)}
            <span className="text-white/40 font-normal ml-1" style={{ fontSize: 12 }}>kW</span>
          </div>
        </div>
        <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.03)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Car size={11} style={{ color: '#56CCF2' }} />
            <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>ACTIVE SESSIONS</span>
          </div>
          <div className="text-white font-black" style={{ fontSize: 22 }}>
            {activeSessions}
            <span className="text-white/40 font-normal ml-1" style={{ fontSize: 12 }}>/ {bays.length || 4}</span>
          </div>
        </div>
      </div>

      {/* Transformer loading bar */}
      <div className="mb-4">
        <div className="flex justify-between mb-1">
          <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>
            TRANSFORMER LOADING (0–150%)
          </span>
          <span className="font-bold" style={{ fontSize: 11, color: loadingColor(txLoadingPct) }}>
            {txLoadingPct != null ? `${txLoadingPct.toFixed(1)}%` : '—'}
          </span>
        </div>
        <div className="relative w-full h-4 rounded-full overflow-hidden"
          style={{ background: 'rgba(255,255,255,0.04)' }}>
          {/* Amber zone 80–100% */}
          <div className="absolute top-0 h-full" style={{
            left: `${(80 / 150) * 100}%`,
            width: `${((100 - 80) / 150) * 100}%`,
            background: 'rgba(245,158,11,0.15)',
          }} />
          {/* Red zone 100–150% */}
          <div className="absolute top-0 h-full" style={{
            left: `${(100 / 150) * 100}%`,
            width: `${((150 - 100) / 150) * 100}%`,
            background: 'rgba(233,75,75,0.18)',
          }} />
          {/* Threshold line at 100% */}
          <div className="absolute top-0 h-full w-px" style={{
            left: `${(100 / 150) * 100}%`,
            background: 'rgba(233,75,75,0.6)',
          }} />
          {/* Value bar */}
          {txLoadingPct != null && (
            <div className="absolute top-0 left-0 h-full transition-all duration-700" style={{
              width: `${Math.min((txLoadingPct / 150) * 100, 100)}%`,
              background: loadingColor(txLoadingPct),
              opacity: 0.85,
            }} />
          )}
          {/* Value marker */}
          {txLoadingPct != null && (
            <div className="absolute top-0 h-full w-0.5" style={{
              left: `${Math.min((txLoadingPct / 150) * 100, 100)}%`,
              background: 'white',
            }} />
          )}
        </div>
        <div className="flex justify-between mt-1" style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>
          <span>0%</span>
          <span>80%</span>
          <span>100%</span>
          <span>150%</span>
        </div>
      </div>

      {/* 4 bays strip */}
      <div className="mb-4">
        <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
          CHARGING BAYS
        </div>
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => {
            const bay = bays[i] || {}
            const plugged = !!bay.plugged
            const connector = (bay.connector || 'CCS2').toUpperCase()
            const soc = bay.soc_pct ?? 0
            const rated = bay.rated_kw ?? params.bay_rated_kw ?? 50
            const current = bay.current_kw ?? 0
            const setpoint = bay.setpoint_kw ?? rated
            const bayId = bay.id || `BAY-${i + 1}`
            const setpointPct = rated > 0 ? Math.min((setpoint / rated) * 100, 100) : 100
            const currentPct = rated > 0 ? Math.min((current / rated) * 100, 100) : 0

            return (
              <div key={bayId} className="relative p-3 rounded-lg overflow-hidden"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: plugged ? '1px solid rgba(2,201,168,0.25)' : '1px solid rgba(255,255,255,0.06)',
                }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5">
                    <Plug size={12} style={{ color: plugged ? '#02C9A8' : 'rgba(255,255,255,0.3)' }} />
                    <span className="text-white font-bold" style={{ fontSize: 11 }}>{bayId}</span>
                  </div>
                  <span className="px-1.5 py-0.5 rounded" style={{
                    fontSize: 9,
                    background: connector === 'CHADEMO' ? 'rgba(86,204,242,0.15)' : 'rgba(171,199,255,0.15)',
                    color: connector === 'CHADEMO' ? '#56CCF2' : '#ABC7FF',
                    fontWeight: 700,
                  }}>
                    {connector}
                  </span>
                </div>

                {/* SoC bar */}
                <div className="mb-2">
                  <div className="flex justify-between mb-1">
                    <span className="text-white/40" style={{ fontSize: 9 }}>SoC</span>
                    <span className="text-white font-bold" style={{ fontSize: 10 }}>{soc.toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full"
                    style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <div className="h-2 rounded-full transition-all duration-700" style={{
                      width: `${Math.max(0, Math.min(soc, 100))}%`,
                      background: '#02C9A8',
                    }} />
                  </div>
                </div>

                {/* Current / rated with setpoint dashed line */}
                <div className="mb-1">
                  <div className="flex justify-between mb-1">
                    <span className="text-white/40" style={{ fontSize: 9 }}>POWER</span>
                    <span className="text-white font-bold" style={{ fontSize: 10 }}>
                      {current.toFixed(0)}<span className="text-white/40"> / {rated.toFixed(0)} kW</span>
                    </span>
                  </div>
                  <div className="relative w-full h-2 rounded-full"
                    style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <div className="h-2 rounded-full transition-all duration-700" style={{
                      width: `${currentPct}%`,
                      background: '#ABC7FF',
                    }} />
                    {/* OCPP setpoint dashed limit line */}
                    <div className="absolute top-0 h-full" style={{
                      left: `${setpointPct}%`,
                      width: '0',
                      borderLeft: '2px dashed #F59E0B',
                    }} />
                  </div>
                  <div className="text-white/40 mt-1" style={{ fontSize: 8 }}>
                    Setpoint {setpoint.toFixed(0)} kW
                  </div>
                </div>

                {!plugged && (
                  <div className="absolute inset-0 flex items-center justify-center"
                    style={{ background: 'rgba(10,15,30,0.72)' }}>
                    <span className="font-black tracking-wider" style={{
                      fontSize: 14,
                      color: 'rgba(255,255,255,0.5)',
                      opacity: 0.7 + (tick % 2) * 0.1,
                    }}>
                      IDLE
                    </span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Demand forecast chart */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-white/40 font-bold" style={{ fontSize: 11 }}>
            DEMAND FORECAST · NEXT 4 HOURS
          </span>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: 'rgba(255,255,255,0.2)' }} />
              <span className="text-white/40" style={{ fontSize: 10 }}>Predicted</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: '#02C9A8' }} />
              <span className="text-white/40" style={{ fontSize: 10 }}>Curtailed Limit</span>
            </div>
          </div>
        </div>
        <div className="flex items-end gap-1 h-24 px-1"
          style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {Array.from({ length: FORECAST_BUCKETS }).map((_, i) => {
            const b = forecast[i] || {}
            const predicted = b.predicted_kw ?? 0
            const curtailed = b.curtailed_kw ?? 0
            const predH = (predicted / forecastMax) * 100
            const curtH = (curtailed / forecastMax) * 100
            return (
              <div key={i} className="flex-1 flex items-end gap-px h-full">
                <div className="flex-1" style={{
                  height: `${predH}%`,
                  background: 'rgba(255,255,255,0.18)',
                  borderTopLeftRadius: 2,
                  borderTopRightRadius: 2,
                  transition: 'height 700ms',
                }} />
                <div className="flex-1" style={{
                  height: `${curtH}%`,
                  background: '#02C9A8',
                  opacity: 0.85,
                  borderTopLeftRadius: 2,
                  borderTopRightRadius: 2,
                  transition: 'height 700ms',
                }} />
              </div>
            )
          })}
        </div>
        <div className="flex justify-between mt-1 px-1" style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>
          <span>now</span>
          <span>+1h</span>
          <span>+2h</span>
          <span>+3h</span>
          <span>+4h</span>
        </div>
      </div>

      {/* OCPP commands panel */}
      <div>
        <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
          OCPP COMMANDS
          {stationSetpointKw != null && (
            <span className="ml-2 text-white/60 font-normal">
              (current envelope: {stationSetpointKw.toFixed(0)} kW)
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-secondary py-2 px-4 text-sm"
            onClick={() => issue({ command: 'set_station_setpoint', value: 140 }, 'Station setpoint 140 kW')}
          >
            Station setpoint 140 kW
          </button>
          <button
            className="btn-secondary py-2 px-4 text-sm"
            onClick={() => issue({ command: 'smart_reduce_bays' }, 'Bay-by-bay smart reduce')}
          >
            Bay-by-bay smart reduce
          </button>
          <button
            className="btn-secondary py-2 px-4 text-sm"
            onClick={() => issue({ command: 'release_envelope' }, 'Release envelope')}
          >
            Release envelope
          </button>
        </div>
      </div>
    </div>
  )
}
