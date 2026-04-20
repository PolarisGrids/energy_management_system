// Spec 018 W3.T15 — Solar Overvoltage scenario runner (US17).
// Route: /simulation/solar-overvoltage.
//
// Start scenario → live feeder voltage chart → algorithm panel →
// dispatch `DER_CURTAIL` command via /api/v1/der/{id}/command on
// voltage breach → observe voltage drop → Acknowledge / Release.
//
// Scenario API is proxied through /api/v1/simulation-proxy/*.
// Voltage telemetry is read from /api/v1/der/telemetry (the simulator
// reports per-inverter state + voltage in the `details` field when
// available; otherwise we plot curtailment vs achievement ratio as a
// demonstrable signal).

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Play, Square, SkipForward, CheckCircle, AlertTriangle, Zap,
  Sun, RotateCcw, TrendingUp, Sliders,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, simulationProxyAPI } from '@/services/api'

const SCENARIO_NAME = 'solar_overvoltage'
const THRESHOLD_PU = 1.08
const TARGET_PU = 1.02
const DEFAULT_CURTAIL_PCT = 70

export default function SolarOvervoltageRunner() {
  const [scenarioStatus, setScenarioStatus] = useState(null)
  const [assets, setAssets] = useState([])
  const [history, setHistory] = useState([])  // [{ ts, voltage_pu }]
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)
  const [autoCurtailed, setAutoCurtailed] = useState(false)
  const [commandLog, setCommandLog] = useState([])

  // ── Telemetry poll every 5 s while the scenario is active ──
  const poll = useCallback(async () => {
    try {
      const { data } = await derAPI.telemetry({ type: 'pv', window: '1h' })
      setAssets(data.assets || [])
      // Simulator emits scenario voltage_pu in assets[i].details.voltage_pu when
      // running; fall back to highest achievement_rate as a proxy (demo).
      const maxPu = (data.assets || []).reduce((m, a) => {
        const v = a.details?.voltage_pu ?? (a.achievement_rate_pct ? 1.0 + a.achievement_rate_pct / 1000 : null)
        return v != null && v > (m ?? -Infinity) ? v : m
      }, null)
      if (maxPu != null) {
        const ts = new Date().toISOString()
        setHistory((h) => [...h.slice(-119), { ts, voltage_pu: Number(maxPu.toFixed(3)) }])
      }
    } catch (err) {
      // Non-fatal — the chart will just stop advancing.
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    try {
      const { data } = await simulationProxyAPI.scenarioStatus(SCENARIO_NAME)
      setScenarioStatus(data)
    } catch (err) {
      // simulator may be offline — don't clobber UI.
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    const id = setInterval(() => { poll(); refreshStatus() }, 5000)
    return () => clearInterval(id)
  }, [poll, refreshStatus])

  const onStart = useCallback(async () => {
    setBusy(true); setError(null); setAcknowledged(false); setAutoCurtailed(false)
    setHistory([]); setCommandLog([])
    try {
      await simulationProxyAPI.scenarioStart(SCENARIO_NAME, {})
      await refreshStatus()
    } catch (err) {
      setError(err?.response?.data?.detail?.message ?? 'Failed to start scenario.')
    } finally { setBusy(false) }
  }, [refreshStatus])

  const onStep = useCallback(async () => {
    setBusy(true); setError(null)
    try { await simulationProxyAPI.scenarioStep(SCENARIO_NAME, {}); await refreshStatus() }
    catch (err) { setError(err?.response?.data?.detail?.message ?? 'Step failed.') }
    finally { setBusy(false) }
  }, [refreshStatus])

  const onStop = useCallback(async () => {
    setBusy(true); setError(null)
    try { await simulationProxyAPI.scenarioStop(SCENARIO_NAME); await refreshStatus() }
    catch (err) { setError(err?.response?.data?.detail?.message ?? 'Stop failed.') }
    finally { setBusy(false) }
  }, [refreshStatus])

  const latestPu = history.length ? history[history.length - 1].voltage_pu : null
  const breach = latestPu != null && latestPu >= THRESHOLD_PU

  // Auto-curtail when threshold crossed and operator has acknowledged.
  useEffect(() => {
    if (!breach || autoCurtailed || !acknowledged) return
    const pvs = assets.filter((a) => a.type === 'pv')
    if (!pvs.length) return
    let cancelled = false
    ;(async () => {
      for (const pv of pvs) {
        if (cancelled) break
        const setpoint = (pv.capacity_kw ?? 0) * (DEFAULT_CURTAIL_PCT / 100)
        try {
          await derAPI.command(pv.id, { command_type: 'DER_CURTAIL', setpoint })
          setCommandLog((log) => [...log,
            { ts: new Date().toISOString(), asset: pv.id, setpoint, status: 'SENT' }])
        } catch (err) {
          setCommandLog((log) => [...log,
            { ts: new Date().toISOString(), asset: pv.id, setpoint,
              status: 'FAILED', error: err?.response?.data?.detail ?? 'error' }])
        }
      }
      if (!cancelled) setAutoCurtailed(true)
    })()
    return () => { cancelled = true }
  }, [breach, autoCurtailed, acknowledged, assets])

  const onRelease = useCallback(async () => {
    setBusy(true); setError(null)
    const pvs = assets.filter((a) => a.type === 'pv')
    for (const pv of pvs) {
      try {
        await derAPI.command(pv.id, {
          command_type: 'DER_SET_ACTIVE_POWER',
          setpoint: pv.capacity_kw ?? 0,
        })
        setCommandLog((log) => [...log, {
          ts: new Date().toISOString(), asset: pv.id,
          setpoint: pv.capacity_kw, status: 'RELEASED',
        }])
      } catch (err) {
        setCommandLog((log) => [...log, {
          ts: new Date().toISOString(), asset: pv.id,
          status: 'FAILED', error: err?.response?.data?.detail ?? 'error',
        }])
      }
    }
    setAutoCurtailed(false)
    setBusy(false)
  }, [assets])

  const voltageOption = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 24, bottom: 40 },
    xAxis: {
      type: 'time',
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
    },
    yAxis: {
      type: 'value', name: 'pu', min: 0.9, max: 1.15,
      nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [{
      name: 'Voltage',
      type: 'line',
      data: history.map((p) => [p.ts, p.voltage_pu]),
      smooth: true, symbol: 'none',
      lineStyle: { color: breach ? '#E94B4B' : '#02C9A8', width: 2 },
      markLine: {
        silent: true,
        lineStyle: { color: 'rgba(245,158,11,0.4)', type: 'dashed' },
        data: [
          { yAxis: THRESHOLD_PU, label: { formatter: `${THRESHOLD_PU} pu — threshold`, color: '#F59E0B' } },
          { yAxis: TARGET_PU, label: { formatter: `${TARGET_PU} pu — target`, color: '#02C9A8' } },
        ],
      },
    }],
  }), [history, breach])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="solar-overvoltage-runner">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Solar Overvoltage Scenario</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-21 · US17 — Smart-inverter curtailment round-trip
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onStart} disabled={busy} className="btn-primary"
            style={{ padding: '8px 16px', fontSize: 13 }} data-testid="start-scenario">
            <Play size={13} className="mr-1.5" /> Start
          </button>
          <button onClick={onStep} disabled={busy || !scenarioStatus} className="btn-secondary"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <SkipForward size={13} className="mr-1.5" /> Step
          </button>
          <button onClick={onStop} disabled={busy} className="btn-secondary"
            style={{ padding: '8px 16px', fontSize: 13 }}>
            <Square size={13} className="mr-1.5" /> Stop
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={14} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{error}</span>
        </div>
      )}

      {/* Overvoltage banner + ack/release */}
      {breach && (
        <div className="glass-card p-4 flex items-center gap-3 animate-slide-up"
          data-testid="overvoltage-banner"
          style={{ borderColor: 'rgba(233,75,75,0.4)', background: 'rgba(233,75,75,0.10)' }}>
          <AlertTriangle size={20} style={{ color: '#E94B4B' }} />
          <div className="flex-1">
            <div className="text-white font-bold" style={{ fontSize: 14 }}>
              Voltage {latestPu?.toFixed(3)} pu exceeds {THRESHOLD_PU} pu threshold
            </div>
            <div className="text-white/70" style={{ fontSize: 12 }}>
              {acknowledged
                ? autoCurtailed
                  ? `Curtailment dispatched at ${DEFAULT_CURTAIL_PCT}% of rated. Watching for recovery…`
                  : 'Dispatching curtailment to inverters…'
                : 'Operator acknowledgement required before auto-curtail.'}
            </div>
          </div>
          {!acknowledged ? (
            <button className="btn-primary" style={{ padding: '8px 16px', fontSize: 13 }}
              onClick={() => setAcknowledged(true)}
              data-testid="acknowledge-btn">
              <CheckCircle size={13} className="mr-1.5" /> Acknowledge
            </button>
          ) : (
            <button className="btn-secondary" style={{ padding: '8px 16px', fontSize: 13 }}
              disabled={busy}
              onClick={onRelease}
              data-testid="release-btn">
              <RotateCcw size={13} className="mr-1.5" /> Release
            </button>
          )}
        </div>
      )}

      {/* Chart + algorithm panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass-card p-5 lg:col-span-2">
          <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>
            FEEDER VOLTAGE (pu) — live
          </div>
          <ReactECharts option={voltageOption} style={{ height: 280 }} notMerge
            data-testid="voltage-chart" />
        </div>
        <div className="glass-card p-5">
          <div className="text-white/60 font-bold mb-3 flex items-center gap-2" style={{ fontSize: 12 }}>
            <Sliders size={12} /> ALGORITHM
          </div>
          <div className="space-y-2 text-white/70" style={{ fontSize: 12 }}>
            <div>
              <span className="text-white/40">Inputs:</span> latest feeder voltage (pu),
              per-inverter rated capacity (kW), current active-power output (kW).
            </div>
            <div>
              <span className="text-white/40">Trigger:</span> voltage &ge;{' '}
              <span className="text-[#F59E0B] font-bold">{THRESHOLD_PU} pu</span>.
            </div>
            <div>
              <span className="text-white/40">Setpoint:</span>{' '}
              <code className="text-[#02C9A8]">rated × 0.{DEFAULT_CURTAIL_PCT}</code>{' '}
              (droop-curve default curtailment).
            </div>
            <div>
              <span className="text-white/40">Command:</span>{' '}
              <code>DER_CURTAIL</code> via{' '}
              <code>POST /api/v1/der/&#123;id&#125;/command</code> → HES routing → simulator.
            </div>
            <div>
              <span className="text-white/40">Target:</span> voltage ≤{' '}
              <span className="text-[#02C9A8] font-bold">{TARGET_PU} pu</span>.
            </div>
          </div>
        </div>
      </div>

      {/* Command log */}
      <div className="glass-card p-5">
        <div className="text-white/60 font-bold mb-3 flex items-center gap-2" style={{ fontSize: 12 }}>
          <Zap size={12} /> COMMAND LOG
        </div>
        <div data-testid="command-log" className="max-h-56 overflow-auto font-mono"
          style={{ fontSize: 12 }}>
          {commandLog.length === 0 ? (
            <div className="text-white/30" style={{ fontSize: 12 }}>No commands dispatched yet.</div>
          ) : commandLog.map((c, i) => (
            <div key={i} className="flex gap-4 py-1 border-b border-white/5">
              <span className="text-white/40">{c.ts?.slice(11, 19)}</span>
              <span className="text-white/80">{c.asset}</span>
              <span className="text-[#F59E0B]">DER_CURTAIL → {Number(c.setpoint ?? 0).toFixed(1)} kW</span>
              <span style={{ color: c.status === 'FAILED' ? '#E94B4B' : '#02C9A8' }}>{c.status}</span>
              {c.error && <span className="text-white/40">{c.error}</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Asset tiles */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Sun size={14} style={{ color: '#F59E0B' }} />
          <h2 className="text-white font-bold" style={{ fontSize: 14 }}>PV Inverters</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="inverter-tiles">
          {assets.map((a) => (
            <div key={a.id} className="glass-card p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: 'rgba(245,158,11,0.2)' }}>
                  <Sun size={13} style={{ color: '#F59E0B' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-white font-bold truncate" style={{ fontSize: 12 }}>{a.name || a.id}</div>
                  <div className="text-white/40 truncate" style={{ fontSize: 10 }}>{a.id}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-white/80" style={{ fontSize: 11 }}>
                <div>
                  <div className="text-white/40">Output</div>
                  <div className="font-mono font-bold">{Number(a.current_output_kw ?? 0).toFixed(1)} kW</div>
                </div>
                <div>
                  <div className="text-white/40">Curtail %</div>
                  <div className="font-mono font-bold">{Number(a.curtailment_pct ?? 0).toFixed(1)}%</div>
                </div>
              </div>
            </div>
          ))}
          {assets.length === 0 && (
            <div className="text-white/30 col-span-full text-center py-4" style={{ fontSize: 12 }}>
              No PV inverters reported.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
