// Spec 018 W3.T16 — EV Fast-Charging scenario runner (US18).
// Route: /simulation/ev-fast-charging.
//
// Start scenario → watch DTR loading curve → when > 100%, show
// overload alarm + forecast chart → operator "Curtail" dispatches
// `EV_CHARGER_SET_POWER` command.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Play, Square, SkipForward, AlertTriangle, Zap, Car, Sliders, RotateCcw, CheckCircle,
} from 'lucide-react'
import ReactECharts from 'echarts-for-react'
import { derAPI, simulationProxyAPI } from '@/services/api'

const SCENARIO_NAME = 'ev_fast_charging'
const OVERLOAD_PCT = 100
const DEFAULT_CURTAIL_PCT = 60

export default function EvFastChargingRunner() {
  const [scenarioStatus, setScenarioStatus] = useState(null)
  const [assets, setAssets] = useState([])
  const [history, setHistory] = useState([])  // [{ ts, loading_pct }]
  const [forecast, setForecast] = useState([])  // next 12 points
  const [commandLog, setCommandLog] = useState([])
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refreshStatus = useCallback(async () => {
    try {
      const { data } = await simulationProxyAPI.scenarioStatus(SCENARIO_NAME)
      setScenarioStatus(data)
    } catch (err) { /* non-fatal */ }
  }, [])

  const poll = useCallback(async () => {
    try {
      const { data } = await derAPI.telemetry({ type: 'ev', window: '1h' })
      setAssets(data.assets || [])
      // DTR loading %: fleet kW / rated kVA (if available in details).
      const totalKw = (data.assets || []).reduce((s, a) => s + (a.current_output_kw ?? 0), 0)
      const rated = (data.assets || []).reduce((s, a) => s + (a.details?.dtr_rating_kva ?? a.capacity_kw ?? 0), 0)
      const loadingPct = rated > 0 ? (totalKw / rated) * 100 : 0
      const ts = new Date().toISOString()
      setHistory((h) => [...h.slice(-119), { ts, loading_pct: Number(loadingPct.toFixed(1)) }])
      // Forecast: linear extrapolation of the last 6 points, projecting 12 steps forward.
      setHistory((hist) => {
        const last = [...hist.slice(-119), { ts, loading_pct: Number(loadingPct.toFixed(1)) }]
        const recent = last.slice(-6)
        if (recent.length >= 2) {
          const slope = (recent[recent.length - 1].loading_pct - recent[0].loading_pct) / (recent.length - 1)
          const base = recent[recent.length - 1].loading_pct
          const fc = Array.from({ length: 12 }, (_, i) => {
            const t = new Date(Date.now() + (i + 1) * 5000).toISOString()
            return { ts: t, loading_pct: Math.max(0, base + slope * (i + 1)) }
          })
          setForecast(fc)
        }
        return last
      })
    } catch (err) { /* non-fatal */ }
  }, [])

  useEffect(() => {
    refreshStatus()
    const id = setInterval(() => { poll(); refreshStatus() }, 5000)
    return () => clearInterval(id)
  }, [poll, refreshStatus])

  const onStart = useCallback(async () => {
    setBusy(true); setError(null); setHistory([]); setForecast([])
    setCommandLog([]); setAcknowledged(false)
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

  const latestLoad = history.length ? history[history.length - 1].loading_pct : 0
  const overload = latestLoad >= OVERLOAD_PCT

  const onCurtail = useCallback(async () => {
    setBusy(true); setError(null)
    const evs = assets.filter((a) => a.type === 'ev' || a.type === 'ev_charger')
    for (const ev of evs) {
      const setpoint = (ev.capacity_kw ?? 22) * (DEFAULT_CURTAIL_PCT / 100)
      try {
        await derAPI.command(ev.id, { command_type: 'EV_CHARGER_SET_POWER', setpoint })
        setCommandLog((log) => [...log, {
          ts: new Date().toISOString(), asset: ev.id, setpoint, status: 'SENT',
        }])
      } catch (err) {
        setCommandLog((log) => [...log, {
          ts: new Date().toISOString(), asset: ev.id, setpoint,
          status: 'FAILED', error: err?.response?.data?.detail ?? 'error',
        }])
      }
    }
    setBusy(false)
  }, [assets])

  const onRelease = useCallback(async () => {
    setBusy(true); setError(null)
    const evs = assets.filter((a) => a.type === 'ev' || a.type === 'ev_charger')
    for (const ev of evs) {
      try {
        await derAPI.command(ev.id, {
          command_type: 'EV_CHARGER_SET_POWER', setpoint: ev.capacity_kw ?? 22,
        })
        setCommandLog((log) => [...log, {
          ts: new Date().toISOString(), asset: ev.id, setpoint: ev.capacity_kw,
          status: 'RELEASED',
        }])
      } catch (err) { /* ignore */ }
    }
    setAcknowledged(false)
    setBusy(false)
  }, [assets])

  const chartOption = useMemo(() => {
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { data: ['Actual', 'Forecast'], textStyle: { color: 'rgba(255,255,255,0.6)' }, top: 0 },
      grid: { left: 48, right: 20, top: 28, bottom: 40 },
      xAxis: {
        type: 'time',
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      },
      yAxis: {
        type: 'value', name: '%', min: 0, max: 150,
        nameTextStyle: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
        axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      },
      series: [
        {
          name: 'Actual', type: 'line',
          data: history.map((p) => [p.ts, p.loading_pct]),
          smooth: true, symbol: 'none',
          lineStyle: { color: overload ? '#E94B4B' : '#02C9A8', width: 2 },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: overload ? 'rgba(233,75,75,0.3)' : 'rgba(2,201,168,0.3)' },
                { offset: 1, color: 'rgba(255,255,255,0.02)' },
              ],
            },
          },
          markLine: {
            silent: true,
            lineStyle: { color: 'rgba(245,158,11,0.5)', type: 'dashed' },
            data: [{ yAxis: OVERLOAD_PCT, label: { formatter: '100% — overload', color: '#F59E0B' } }],
          },
        },
        {
          name: 'Forecast', type: 'line',
          data: forecast.map((p) => [p.ts, p.loading_pct]),
          smooth: true, symbol: 'none',
          lineStyle: { color: '#F59E0B', width: 2, type: 'dashed' },
        },
      ],
    }
  }, [history, forecast, overload])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="ev-fast-charging-runner">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>EV Fast-Charging Scenario</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-22 · US18 — Transformer overload + EV charger curtailment
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onStart} disabled={busy} className="btn-primary"
            style={{ padding: '8px 16px', fontSize: 13 }} data-testid="start-scenario">
            <Play size={13} className="mr-1.5" /> Start
          </button>
          <button onClick={onStep} disabled={busy} className="btn-secondary"
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

      {overload && (
        <div className="glass-card p-4 flex items-center gap-3 animate-slide-up"
          data-testid="overload-banner"
          style={{ borderColor: 'rgba(233,75,75,0.4)', background: 'rgba(233,75,75,0.10)' }}>
          <AlertTriangle size={20} style={{ color: '#E94B4B' }} />
          <div className="flex-1">
            <div className="text-white font-bold" style={{ fontSize: 14 }}>
              DTR overload — loading {latestLoad.toFixed(1)}% ({'>'}{OVERLOAD_PCT}%)
            </div>
            <div className="text-white/70" style={{ fontSize: 12 }}>
              {acknowledged
                ? 'Ready to curtail EV chargers to mitigate overload.'
                : 'Operator acknowledgement required before curtailment.'}
            </div>
          </div>
          {!acknowledged ? (
            <button className="btn-primary" style={{ padding: '8px 16px', fontSize: 13 }}
              onClick={() => setAcknowledged(true)} data-testid="acknowledge-btn">
              <CheckCircle size={13} className="mr-1.5" /> Acknowledge
            </button>
          ) : (
            <>
              <button className="btn-primary" style={{ padding: '8px 16px', fontSize: 13 }}
                disabled={busy} onClick={onCurtail} data-testid="curtail-btn">
                <Sliders size={13} className="mr-1.5" /> Curtail
              </button>
              <button className="btn-secondary" style={{ padding: '8px 16px', fontSize: 13 }}
                disabled={busy} onClick={onRelease} data-testid="release-btn">
                <RotateCcw size={13} className="mr-1.5" /> Release
              </button>
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass-card p-5 lg:col-span-2">
          <div className="text-white/60 font-bold mb-3" style={{ fontSize: 12 }}>
            DTR LOADING — actual + forecast
          </div>
          <ReactECharts option={chartOption} style={{ height: 280 }} notMerge
            data-testid="loading-chart" />
        </div>
        <div className="glass-card p-5">
          <div className="text-white/60 font-bold mb-3 flex items-center gap-2" style={{ fontSize: 12 }}>
            <Sliders size={12} /> ALGORITHM
          </div>
          <div className="space-y-2 text-white/70" style={{ fontSize: 12 }}>
            <div><span className="text-white/40">Inputs:</span> total EV-charger kW, DTR rated kVA.</div>
            <div>
              <span className="text-white/40">Trigger:</span> loading {'>'}{' '}
              <span className="text-[#F59E0B] font-bold">{OVERLOAD_PCT}%</span>.
            </div>
            <div>
              <span className="text-white/40">Forecast:</span> linear extrapolation of last
              6 samples, 12 steps ahead.
            </div>
            <div>
              <span className="text-white/40">Setpoint:</span>{' '}
              <code className="text-[#02C9A8]">rated × 0.{DEFAULT_CURTAIL_PCT}</code>.
            </div>
            <div>
              <span className="text-white/40">Command:</span>{' '}
              <code>EV_CHARGER_SET_POWER</code> via{' '}
              <code>POST /api/v1/der/&#123;id&#125;/command</code>.
            </div>
          </div>
        </div>
      </div>

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
              <span className="text-[#F59E0B]">
                EV_CHARGER_SET_POWER → {Number(c.setpoint ?? 0).toFixed(1)} kW
              </span>
              <span style={{ color: c.status === 'FAILED' ? '#E94B4B' : '#02C9A8' }}>{c.status}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <Car size={14} style={{ color: '#02C9A8' }} />
          <h2 className="text-white font-bold" style={{ fontSize: 14 }}>EV Chargers</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="charger-tiles">
          {assets.map((a) => (
            <div key={a.id} className="glass-card p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: 'rgba(2,201,168,0.2)' }}>
                  <Car size={13} style={{ color: '#02C9A8' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-white font-bold truncate" style={{ fontSize: 12 }}>{a.name || a.id}</div>
                  <div className="text-white/40 truncate" style={{ fontSize: 10 }}>{a.id}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-white/80" style={{ fontSize: 11 }}>
                <div>
                  <div className="text-white/40">Load</div>
                  <div className="font-mono font-bold">{Number(a.current_output_kw ?? 0).toFixed(1)} kW</div>
                </div>
                <div>
                  <div className="text-white/40">State</div>
                  <div className="font-mono font-bold">{a.state || '—'}</div>
                </div>
              </div>
            </div>
          ))}
          {assets.length === 0 && (
            <div className="text-white/30 col-span-full text-center py-4" style={{ fontSize: 12 }}>
              No EV chargers reported.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
