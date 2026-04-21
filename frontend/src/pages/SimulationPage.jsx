import { useState, useEffect } from 'react'
import { Play, SkipForward, RotateCcw, Terminal, Zap, AlertTriangle, CheckCircle, Users, WifiOff, Wifi } from 'lucide-react'
import { simulationAPI, derAPI, metersAPI } from '@/services/api'
import FaultTopology from '@/components/simulation/FaultTopology'
import SensorDashboard from '@/components/simulation/SensorDashboard'
import SolarOvervoltageViz from '@/components/simulation/SolarOvervoltageViz'
import EvChargingViz from '@/components/simulation/EvChargingViz'
import MicrogridViz from '@/components/simulation/MicrogridViz'

const TYPE_LABEL = {
  solar_overvoltage: 'REQ-21 · Solar Overvoltage',
  ev_fast_charging:  'REQ-22 · EV Fast Charging',
  peaking_microgrid: 'REQ-23 · Peaking Microgrid',
  network_fault:     'REQ-24 · Network Fault / FLISR',
  sensor_asset:      'REQ-25 · Transformer Sensors',
}

const TYPE_COLOR = {
  solar_overvoltage: '#F59E0B',
  ev_fast_charging:  '#02C9A8',
  peaking_microgrid: '#ABC7FF',
  network_fault:     '#E94B4B',
  sensor_asset:      '#F97316',
}

const STATUS_ICON = {
  idle: null,
  running: <span className="animate-pulse w-2 h-2 rounded-full bg-energy-green inline-block" />,
  completed: <CheckCircle size={12} className="text-energy-green" />,
  aborted: <AlertTriangle size={12} className="text-status-critical" />,
}

export default function SimulationPage() {
  const [scenarios, setScenarios] = useState([])
  const [active, setActive] = useState(null)
  const [loading, setLoading] = useState(true)
  const [cmdLog, setCmdLog] = useState([])

  const load = async () => {
    try {
      const { data } = await simulationAPI.list()
      setScenarios(data)
      if (active) {
        const updated = data.find(s => s.id === active.id)
        if (updated) setActive(updated)
      }
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const start = async (id) => {
    await simulationAPI.start(id, {})
    await load()
    const s = scenarios.find(s => s.id === id)
    log(`▶ Started: ${s?.name}`)
  }

  const nextStep = async () => {
    if (!active) return
    const { data } = await simulationAPI.nextStep(active.id)
    setActive(data)
    const step = data.steps?.[data.current_step - 1]
    log(`→ Step ${data.current_step}: ${step?.description ?? ''}`)
    if (data.status === 'completed') log('✓ Scenario completed')
    load()
  }

  const reset = async (id) => {
    await simulationAPI.reset(id)
    log(`⟳ Reset scenario`)
    load()
  }

  const sendCmd = async (cmd, targetId, value) => {
    if (!active) return
    const { data } = await simulationAPI.command(active.id, { command: cmd, target_id: targetId, value, issued_by: 'Operator' })
    log(`⚡ Command: ${cmd} → ${JSON.stringify(data.result)}`)
    load()
  }

  const log = (msg) => setCmdLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 50))

  const currentStep = active ? active.steps?.[active.current_step - 1] : null
  const currentState = currentStep?.network_state || {}

  return (
    <div className="flex gap-4 h-full animate-slide-up">
      {/* Scenario list */}
      <div className="flex flex-col gap-3 w-72 shrink-0">
        <h2 className="text-white font-bold" style={{ fontSize: 16 }}>Demo Scenarios</h2>
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-20 rounded-card" />)
        ) : scenarios.map(s => (
          <div
            key={s.id}
            onClick={() => setActive(s)}
            className={`glass-card p-4 cursor-pointer transition-all ${active?.id === s.id ? 'ring-1 ring-energy-green' : 'hover:border-white/10'}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: TYPE_COLOR[s.scenario_type] }} />
              <span className="text-white font-bold text-sm truncate">{TYPE_LABEL[s.scenario_type] ?? s.name}</span>
              {STATUS_ICON[s.status]}
            </div>
            <div className="flex items-center gap-2 mt-2">
              {s.status === 'idle' || s.status === 'completed' || s.status === 'aborted' ? (
                <button onClick={(e) => { e.stopPropagation(); start(s.id) }} className="btn-primary py-1.5 px-3 text-xs">
                  <Play size={11} className="inline mr-1" /> Start
                </button>
              ) : null}
              {s.status !== 'idle' && (
                <button onClick={(e) => { e.stopPropagation(); reset(s.id) }} className="btn-secondary py-1.5 px-3 text-xs">
                  <RotateCcw size={11} className="inline mr-1" /> Reset
                </button>
              )}
            </div>
            {s.status === 'running' && (
              <div className="mt-2">
                <div className="flex justify-between text-xs text-white/40 mb-1">
                  <span>Step {s.current_step}/{s.total_steps}</span>
                  <span>{Math.round((s.current_step / s.total_steps) * 100)}%</span>
                </div>
                <div className="w-full h-1 rounded-full bg-white/10">
                  <div className="h-1 rounded-full transition-all" style={{ width: `${(s.current_step / s.total_steps) * 100}%`, background: TYPE_COLOR[s.scenario_type] }} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Main panel — overflow-y-auto so the sample-design sim viz (which is
          taller than the viewport) scrolls cleanly. */}
      <div className="flex-1 flex flex-col gap-4 overflow-y-auto overflow-x-hidden min-h-0">
        {active ? (
          <>
            {/* Scenario header */}
            <div className="glass-card p-5">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: `${TYPE_COLOR[active.scenario_type]}20` }}>
                  <Zap size={18} style={{ color: TYPE_COLOR[active.scenario_type] }} />
                </div>
                <div>
                  <div className="text-white font-black" style={{ fontSize: 18 }}>{active.name}</div>
                  <div className="text-white/50 text-sm">{active.description}</div>
                </div>
                <div className="ml-auto flex gap-2">
                  {active.status === 'running' && (
                    <button onClick={nextStep} className="btn-primary py-2 px-4">
                      <SkipForward size={14} className="inline mr-1" /> Next Step
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Current step */}
            {currentStep && (
              <div className="glass-card p-5">
                <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
                  STEP {active.current_step} / {active.total_steps}
                </div>
                <div className="text-white font-bold text-lg mb-4">{currentStep.description}</div>

                {/* Network state values */}
                {Object.keys(currentState).length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                    {Object.entries(currentState).filter(([, v]) => typeof v === 'number').map(([k, v]) => (
                      <div key={k} className="bg-white/5 rounded-lg p-3">
                        <div className="text-white/40 mb-1" style={{ fontSize: 11 }}>{k.replace(/_/g, ' ').toUpperCase()}</div>
                        <div className="text-white font-bold" style={{ fontSize: 20 }}>{typeof v === 'number' ? v.toFixed(v > 10 ? 1 : 3) : String(v)}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Available commands */}
                {currentStep.commands_available?.length > 0 && active.status === 'running' && (
                  <div>
                    <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>AVAILABLE COMMANDS</div>
                    <div className="flex flex-wrap gap-2">
                      {currentStep.commands_available.map((cmd, i) => (
                        <button
                          key={i}
                          onClick={() => sendCmd(cmd.cmd, cmd.target_id, null)}
                          className="btn-secondary py-2 px-4 text-sm"
                          style={{ borderColor: `${TYPE_COLOR[active.scenario_type]}40`, color: TYPE_COLOR[active.scenario_type] }}
                        >
                          ⚡ {cmd.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Fault Topology Diagram — only for network_fault scenario */}
            {active.scenario_type === 'network_fault' && active.status === 'running' && currentStep && (
              <FaultTopology
                scenario={active}
                currentStep={active.current_step}
                networkState={currentState}
              />
            )}

            {/* Solar droop-curtailment viz — only for solar_overvoltage scenario */}
            {active.scenario_type === 'solar_overvoltage' && active.status === 'running' && currentStep && (
              <SolarOvervoltageViz
                scenario={active}
                currentStep={active.current_step}
                networkState={currentState}
              />
            )}

            {/* EV fast-charge hub viz — only for ev_fast_charging scenario */}
            {active.scenario_type === 'ev_fast_charging' && active.status === 'running' && currentStep && (
              <EvChargingViz
                scenario={active}
                currentStep={active.current_step}
                networkState={currentState}
                onCommand={(cmd) => sendCmd(cmd.command, cmd.target_id, cmd.value)}
              />
            )}

            {/* Peaking microgrid / VPP viz — only for peaking_microgrid scenario */}
            {active.scenario_type === 'peaking_microgrid' && active.status === 'running' && currentStep && (
              <MicrogridViz
                scenario={active}
                currentStep={active.current_step}
                networkState={currentState}
              />
            )}

            {/* Sensor Dashboard — only for sensor_asset scenario */}
            {active.scenario_type === 'sensor_asset' && active.status === 'running' && currentStep && (
              <SensorDashboard
                transformerId={active.parameters?.transformer_id ?? active.transformer_id}
                networkState={currentState}
                scenarioParams={active.parameters}
              />
            )}

            {/* Fault scenario — affected customers summary cards */}
            {active.scenario_type === 'network_fault' && active.status === 'running' && currentState.phase && currentState.phase !== 'normal' && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <WifiOff size={12} className="text-status-critical" />
                    <span className="text-white/40" style={{ fontSize: 10 }}>METERS OFFLINE</span>
                  </div>
                  <div className="text-white font-black" style={{ fontSize: 24, color: (currentState.meters_offline || 0) > 0 ? '#E94B4B' : '#02C9A8' }}>
                    {currentState.meters_offline ?? 0}
                  </div>
                </div>
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Wifi size={12} className="text-energy-green" />
                    <span className="text-white/40" style={{ fontSize: 10 }}>METERS ONLINE</span>
                  </div>
                  <div className="text-white font-black" style={{ fontSize: 24, color: '#02C9A8' }}>
                    {currentState.meters_online ?? 0}
                  </div>
                </div>
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Zap size={12} style={{ color: '#F59E0B' }} />
                    <span className="text-white/40" style={{ fontSize: 10 }}>FEEDER CURRENT</span>
                  </div>
                  <div className="text-white font-black" style={{ fontSize: 24 }}>
                    {currentState.feeder_current_a?.toFixed(0) ?? '—'}<span className="text-white/40 text-sm ml-1">A</span>
                  </div>
                </div>
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle size={12} style={{ color: '#ABC7FF' }} />
                    <span className="text-white/40" style={{ fontSize: 10 }}>RESTORATION</span>
                  </div>
                  <div className="font-black" style={{
                    fontSize: 24,
                    color: currentState.restoration_percent === 100 ? '#02C9A8' :
                           currentState.restoration_percent > 0 ? '#ABC7FF' : '#6B7280'
                  }}>
                    {currentState.restoration_percent ?? 0}<span className="text-white/40 text-sm ml-1">%</span>
                  </div>
                </div>
              </div>
            )}

            {/* Steps timeline */}
            <div className="glass-card p-5 flex-1 overflow-auto">
              <div className="text-white/40 font-bold mb-3" style={{ fontSize: 11 }}>SCENARIO STEPS</div>
              <div className="space-y-2">
                {active.steps?.map((step, i) => {
                  const done = i < active.current_step
                  const current = i === active.current_step - 1 && active.status === 'running'
                  return (
                    <div key={step.id}
                      className={`flex items-start gap-3 p-3 rounded-lg transition-colors ${
                        current ? 'bg-energy-green/10 border border-energy-green/20' :
                        done ? 'opacity-50' : 'opacity-30'
                      }`}
                    >
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                        done ? 'bg-energy-green text-white' :
                        current ? 'bg-energy-green/20 text-energy-green border border-energy-green' :
                        'bg-white/5 text-white/30'
                      }`}>
                        {done ? '✓' : step.step_number}
                      </div>
                      <div className="text-sm" style={{ color: current ? 'white' : undefined }}>{step.description}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        ) : (
          <div className="glass-card flex-1 flex items-center justify-center">
            <div className="text-center text-white/40">
              <Zap size={40} className="mx-auto mb-3 opacity-30" />
              <div className="font-bold">Select a scenario to begin</div>
              <div className="text-sm mt-1">5 demo scenarios available (REQ-21 to REQ-25)</div>
            </div>
          </div>
        )}

        {/* Command log */}
        <div className="glass-card p-4" style={{ maxHeight: 160 }}>
          <div className="flex items-center gap-2 mb-2">
            <Terminal size={12} className="text-accent-blue" />
            <span className="text-white/40 font-bold" style={{ fontSize: 11 }}>COMMAND LOG</span>
          </div>
          <div className="overflow-auto space-y-1" style={{ maxHeight: 100 }}>
            {cmdLog.length === 0 ? (
              <div className="text-white/20 text-xs">No commands issued yet</div>
            ) : cmdLog.map((line, i) => (
              <div key={i} className="text-xs font-mono" style={{ color: '#02C9A8' }}>{line}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
