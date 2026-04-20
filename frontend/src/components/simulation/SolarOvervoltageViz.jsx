import { useState, useEffect } from 'react'
import { Sun, Activity, AlertTriangle, CheckCircle, Gauge } from 'lucide-react'

/**
 * SolarOvervoltageViz — LV feeder droop-curtailment visualization for REQ-21.
 * Renders a horizontal 7-node feeder topology with per-node voltage heat coloring,
 * the 5-step algorithm pill progression, a live droop equation, and an inverter
 * fleet table with setpoint progress bars.
 */

const NODE_COUNT = 7
const NODE_SPACING = 110
const SVG_PADDING = 70
const NODE_Y = 100
const NODE_RADIUS = 22

const ALGO_STEPS = [
  { key: 'monitor',  label: 'Monitor'  },
  { key: 'detect',   label: 'Detect'   },
  { key: 'compute',  label: 'Compute'  },
  { key: 'curtail',  label: 'Curtail'  },
  { key: 'restore',  label: 'Restore'  },
]

// Voltage -> color gradient (230 green -> 246 amber -> 253 red)
function voltageColor(v) {
  if (v == null) return '#6B7280'
  if (v >= 253) return '#E94B4B'
  if (v >= 246) return '#F59E0B'
  return '#02C9A8'
}

function voltageBadgeColor(v) {
  if (v == null) return { bg: '#6B728020', fg: '#6B7280' }
  if (v > 253) return { bg: '#E94B4B20', fg: '#E94B4B' }
  if (v >= 246) return { bg: '#F59E0B20', fg: '#F59E0B' }
  return { bg: '#02C9A820', fg: '#02C9A8' }
}

export default function SolarOvervoltageViz({ scenario, currentStep, networkState }) {
  const params = scenario?.parameters || {}
  const standards = params.standards || []
  const vRef = params.v_ref ?? 230
  const kKwPerV = params.k_kw_per_v ?? params.droop_k_kw_per_v ?? 10

  const vTip = networkState?.v_tip ?? networkState?.v_tip_v ?? null
  const nodeVoltages = networkState?.node_voltages || networkState?.feeder_voltages || {}
  const algorithmStep = networkState?.algorithm_step || 'monitor'
  const inverters = networkState?.inverters || null
  const deltaV = vTip != null ? (vTip - vRef) : 0
  const deltaP = kKwPerV * deltaV

  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 800)
    return () => clearInterval(id)
  }, [])

  const svgWidth = SVG_PADDING * 2 + NODE_COUNT * NODE_SPACING
  const svgHeight = 200

  // Build nodes: N1..N7
  const nodes = Array.from({ length: NODE_COUNT }).map((_, i) => {
    const id = `N${i + 1}`
    const v = nodeVoltages[id] ?? nodeVoltages[id.toLowerCase()] ?? null
    return { id, index: i, voltage: v, x: SVG_PADDING + (i + 1) * NODE_SPACING, y: NODE_Y }
  })

  const lastNode = nodes[nodes.length - 1]
  const vTipBadge = voltageBadgeColor(vTip)
  const activeStepIdx = ALGO_STEPS.findIndex(s => s.key === algorithmStep)
  const equationActive = algorithmStep === 'compute' || algorithmStep === 'curtail'

  return (
    <div className="glass-card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'rgba(245,158,11,0.15)' }}>
            <Sun size={18} style={{ color: '#F59E0B' }} />
          </div>
          <div>
            <div className="text-white font-black" style={{ fontSize: 15 }}>
              LV Feeder Droop Curtailment
            </div>
            <div className="text-white/40" style={{ fontSize: 11 }}>
              {params.feeder_name || 'LV-F07'} · 230V nominal · {NODE_COUNT} nodes
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
            style={{ background: vTipBadge.bg, border: `1px solid ${vTipBadge.fg}40` }}>
            <Gauge size={12} style={{ color: vTipBadge.fg }} />
            <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>V_TIP</span>
            <span className="font-black" style={{ fontSize: 18, color: vTipBadge.fg }}>
              {vTip != null ? `${vTip.toFixed(1)} V` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Feeder topology SVG */}
      <div className="overflow-x-auto">
        <svg width={svgWidth} height={svgHeight} viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          style={{ minWidth: svgWidth }}>
          <defs>
            <pattern id="solarFlow" patternUnits="userSpaceOnUse" width="24" height="4">
              <rect width="24" height="4" fill="none" />
              <rect x={tick % 2 === 0 ? 0 : 12} y="0" width="12" height="4"
                fill="#02C9A8" opacity="0.6" rx="2" />
            </pattern>
            <filter id="solarNodeGlow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Substation on left */}
          <g transform={`translate(${SVG_PADDING - 20}, ${NODE_Y})`}>
            <rect x="-20" y="-25" width="40" height="50" rx="6"
              fill="#0d1117" stroke="#02C9A8" strokeWidth="1.5" />
            <text x="0" y="-30" textAnchor="middle" fill="#02C9A8" fontSize="9" fontWeight="bold">
              SUBSTATION
            </text>
            <line x1="-10" y1="-10" x2="10" y2="-10" stroke="#02C9A8" strokeWidth="2" />
            <line x1="-10" y1="0" x2="10" y2="0" stroke="#02C9A8" strokeWidth="2" />
            <line x1="-10" y1="10" x2="10" y2="10" stroke="#02C9A8" strokeWidth="2" />
          </g>

          {/* Feeder line from substation to last node */}
          {lastNode && (
            <>
              <line
                x1={SVG_PADDING}
                y1={NODE_Y}
                x2={lastNode.x}
                y2={NODE_Y}
                stroke="#ABC7FF"
                strokeWidth="3"
                opacity="0.35"
              />
              <line
                x1={SVG_PADDING}
                y1={NODE_Y}
                x2={lastNode.x}
                y2={NODE_Y}
                stroke="url(#solarFlow)"
                strokeWidth="5"
                opacity="0.5"
              />
            </>
          )}

          {/* Nodes */}
          {nodes.map(n => {
            const color = voltageColor(n.voltage)
            const isTip = n.id === `N${NODE_COUNT}`
            const high = n.voltage != null && n.voltage >= 246
            return (
              <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                {high && (
                  <circle r={NODE_RADIUS + 5} fill="none" stroke={color} strokeWidth="1"
                    opacity="0.3" filter="url(#solarNodeGlow)">
                    <animate attributeName="r"
                      values={`${NODE_RADIUS + 3};${NODE_RADIUS + 7};${NODE_RADIUS + 3}`}
                      dur="1.5s" repeatCount="indefinite" />
                  </circle>
                )}
                <circle r={NODE_RADIUS} fill="#0d1117" stroke={color} strokeWidth="2.5" />
                <circle r="8" fill={color} opacity="0.25" />
                <text y="4" textAnchor="middle" fill="white" fontSize="10" fontWeight="bold">
                  {n.id}
                </text>
                {/* Voltage label */}
                <text y={NODE_RADIUS + 16} textAnchor="middle" fill={color}
                  fontSize="10" fontWeight="700">
                  {n.voltage != null ? `${n.voltage.toFixed(1)} V` : '—'}
                </text>
                {isTip && (
                  <text y={-NODE_RADIUS - 8} textAnchor="middle" fill="#ABC7FF"
                    fontSize="8" fontWeight="bold">
                    TIP
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {/* Algorithm step pills */}
      <div className="mt-4">
        <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
          ALGORITHM STATE
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {ALGO_STEPS.map((s, i) => {
            const active = i === activeStepIdx
            const done = i < activeStepIdx
            return (
              <div key={s.key} className="flex items-center gap-2">
                <div
                  className={`px-3 py-1.5 rounded-full font-bold transition-all ${active ? 'animate-pulse' : ''}`}
                  style={{
                    fontSize: 10,
                    background: active
                      ? 'rgba(2,201,168,0.2)'
                      : done
                        ? 'rgba(171,199,255,0.1)'
                        : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${active ? '#02C9A8' : done ? 'rgba(171,199,255,0.25)' : 'rgba(255,255,255,0.08)'}`,
                    color: active ? '#02C9A8' : done ? '#ABC7FF' : 'rgba(255,255,255,0.4)',
                  }}
                >
                  {done && <CheckCircle size={10} className="inline mr-1" />}
                  {s.label.toUpperCase()}
                </div>
                {i < ALGO_STEPS.length - 1 && (
                  <div className="w-4 h-px" style={{
                    background: done ? '#ABC7FF60' : 'rgba(255,255,255,0.1)',
                  }} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Droop equation panel */}
      <div className="mt-4 p-3 rounded-lg"
        style={{
          background: equationActive ? 'rgba(2,201,168,0.08)' : 'rgba(255,255,255,0.02)',
          border: `1px solid ${equationActive ? 'rgba(2,201,168,0.25)' : 'rgba(255,255,255,0.06)'}`,
        }}>
        <div className="flex items-center gap-2 mb-1">
          <Activity size={11} style={{ color: equationActive ? '#02C9A8' : 'rgba(255,255,255,0.4)' }} />
          <span className="font-bold" style={{
            fontSize: 10,
            color: equationActive ? '#02C9A8' : 'rgba(255,255,255,0.4)',
          }}>DROOP CURTAILMENT</span>
        </div>
        {equationActive && vTip != null ? (
          <div className="font-mono text-white" style={{ fontSize: 13 }}>
            ΔP = k × (V_tip − V_ref) ={' '}
            <span style={{ color: '#ABC7FF' }}>{kKwPerV}</span> ×{' '}
            <span style={{ color: '#F59E0B' }}>{deltaV.toFixed(2)} V</span> ={' '}
            <span style={{ color: '#02C9A8', fontWeight: 700 }}>{deltaP.toFixed(1)} kW</span>
          </div>
        ) : (
          <div className="text-white/40" style={{ fontSize: 11 }}>
            Curtailment inactive — monitoring feeder voltage.
          </div>
        )}
      </div>

      {/* Inverter fleet table */}
      <div className="mt-4">
        <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
          INVERTER FLEET
        </div>
        {!inverters || inverters.length === 0 ? (
          <div className="p-4 rounded-lg text-center text-white/40"
            style={{ background: 'rgba(255,255,255,0.02)', fontSize: 11 }}>
            Awaiting step data…
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ fontSize: 11 }}>
              <thead>
                <tr className="text-white/40 font-bold text-left" style={{ fontSize: 10 }}>
                  <th className="py-2 px-2">ID</th>
                  <th className="py-2 px-2">NODE</th>
                  <th className="py-2 px-2 text-right">RATED</th>
                  <th className="py-2 px-2 text-right">AVAIL</th>
                  <th className="py-2 px-2 text-right">SETPT</th>
                  <th className="py-2 px-2">UTILIZATION</th>
                  <th className="py-2 px-2 text-right">CURT %</th>
                </tr>
              </thead>
              <tbody>
                {inverters.map(inv => {
                  const curtailing = !!inv.is_curtailing
                  const avail = inv.available_kw ?? inv.rated_kw ?? 0
                  const setpt = inv.setpoint_kw ?? avail
                  const ratio = avail > 0 ? Math.max(0, Math.min(1, setpt / avail)) : 0
                  const curtPct = inv.curtailed_pct ?? (avail > 0 ? Math.max(0, (1 - ratio) * 100) : 0)
                  return (
                    <tr key={inv.id || inv.inverter_id}
                      style={{
                        background: curtailing ? 'rgba(233,75,75,0.08)' : 'transparent',
                        borderTop: '1px solid rgba(255,255,255,0.04)',
                      }}>
                      <td className="py-2 px-2 text-white font-bold">
                        {inv.id || inv.inverter_id}
                      </td>
                      <td className="py-2 px-2 text-white/60">{inv.node || '—'}</td>
                      <td className="py-2 px-2 text-right text-white/60">
                        {(inv.rated_kw ?? 0).toFixed(1)}
                      </td>
                      <td className="py-2 px-2 text-right text-white/60">
                        {avail.toFixed(1)}
                      </td>
                      <td className="py-2 px-2 text-right font-bold"
                        style={{ color: curtailing ? '#E94B4B' : '#02C9A8' }}>
                        {setpt.toFixed(1)}
                      </td>
                      <td className="py-2 px-2">
                        <div className="w-full h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
                          <div className="h-1.5 rounded-full transition-all duration-700" style={{
                            width: `${ratio * 100}%`,
                            background: curtailing ? '#E94B4B' : '#02C9A8',
                          }} />
                        </div>
                      </td>
                      <td className="py-2 px-2 text-right font-bold"
                        style={{ color: curtPct > 0 ? '#F59E0B' : 'rgba(255,255,255,0.4)' }}>
                        {curtPct.toFixed(0)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Footer legend */}
      <div className="flex items-center gap-3 mt-4 flex-wrap pt-3 border-t"
        style={{ borderColor: 'rgba(171,199,255,0.08)' }}>
        <div className="flex items-center gap-1.5">
          <AlertTriangle size={10} className="text-white/40" />
          <span className="text-white/40 font-bold" style={{ fontSize: 10 }}>STANDARDS:</span>
        </div>
        {standards.length > 0 ? standards.map((s, i) => (
          <span key={i} className="px-2 py-0.5 rounded"
            style={{
              fontSize: 10,
              background: 'rgba(171,199,255,0.08)',
              border: '1px solid rgba(171,199,255,0.15)',
              color: '#ABC7FF',
            }}>
            {s}
          </span>
        )) : (
          <span className="text-white/30" style={{ fontSize: 10 }}>—</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {[
            { color: '#02C9A8', label: '<246V' },
            { color: '#F59E0B', label: '≥246V' },
            { color: '#E94B4B', label: '>253V' },
          ].map(item => (
            <div key={item.label} className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ background: item.color }} />
              <span className="text-white/40" style={{ fontSize: 10 }}>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
