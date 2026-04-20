import { useState, useEffect } from 'react'
import { Zap, AlertTriangle, Wrench, CheckCircle, Wifi, WifiOff } from 'lucide-react'

/**
 * FaultTopology — SVG network topology diagram for the FLISR scenario.
 * Shows a horizontal feeder line with transformer nodes, switches, fault location,
 * and animated power flow. Colors update per step to reflect the scenario state.
 */

const NODE_SPACING = 160
const NODE_Y = 120
const SVG_PADDING = 60
const NODE_RADIUS = 28
const SWITCH_SIZE = 14

// Status colour map
const STATUS_COLORS = {
  energised:     '#02C9A8', // green
  faulted:       '#E94B4B', // red
  fault_located: '#F59E0B', // amber
  isolated:      '#6B7280', // gray
  restored_alt:  '#ABC7FF', // blue
  offline:       '#6B7280', // gray
}

const SWITCH_COLORS = {
  closed:  '#02C9A8',
  open:    '#6B7280',
  tripped: '#E94B4B',
}

export default function FaultTopology({ scenario, currentStep, networkState }) {
  const params = scenario?.parameters || {}
  const topology = params.topology || { nodes: [], switches: [] }
  const nodes = topology.nodes || []
  const paramSwitches = topology.switches || []

  // Current state from step
  const switchStates = networkState?.switches || {}
  const topoStatus = networkState?.topology_status || {}
  const faultLocation = networkState?.fault_location || params?.fault_segment || {}
  const firstDarkMeter = networkState?.first_dark_meter || null
  const restorationPct = networkState?.restoration_percent ?? null
  const metersOnline = networkState?.meters_online ?? null
  const metersOffline = networkState?.meters_offline ?? null
  const phase = networkState?.phase || 'normal'
  const workOrder = networkState?.work_order || null
  const crewStatus = networkState?.crew_status || null

  const svgWidth = Math.max(nodes.length * NODE_SPACING + SVG_PADDING * 2, 600)
  const svgHeight = 240

  // Build positions for nodes
  const nodePositions = nodes.map((node, i) => ({
    ...node,
    x: SVG_PADDING + i * NODE_SPACING + NODE_SPACING / 2,
    y: NODE_Y,
    status: topoStatus[String(node.id)] || 'energised',
  }))

  // Build switch items between adjacent nodes
  const switchNames = ['SW-1', 'SW-2', 'SW-3']
  const switchItems = []
  for (let i = 0; i < nodePositions.length - 1; i++) {
    const a = nodePositions[i]
    const b = nodePositions[i + 1]
    const name = switchNames[i] || `SW-${i + 1}`
    switchItems.push({
      name,
      x: (a.x + b.x) / 2,
      y: NODE_Y,
      state: switchStates[name] || 'closed',
    })
  }

  // Tie switch at the end
  const tieState = switchStates['TIE-1'] || 'open'
  const lastNode = nodePositions[nodePositions.length - 1]
  const tieX = lastNode ? lastNode.x + NODE_SPACING * 0.6 : svgWidth - SVG_PADDING

  // Identify fault segment nodes
  const faultUpstream = faultLocation.upstream || faultLocation.upstream_transformer
  const faultDownstream = faultLocation.downstream || faultLocation.downstream_transformer

  // Animation key for power flow
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 800)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-white/40 font-bold" style={{ fontSize: 11 }}>
            NETWORK TOPOLOGY — {params.feeder_name || 'Feeder F-003'}
          </div>
          {phase !== 'normal' && faultUpstream && faultDownstream && (
            <div className="flex items-center gap-2 mt-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold"
                style={{ background: '#E94B4B20', color: '#E94B4B' }}>
                <Zap size={10} /> Fault: {faultUpstream} — {faultDownstream}
              </span>
              {firstDarkMeter && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold"
                  style={{ background: '#F59E0B20', color: '#F59E0B' }}>
                  <WifiOff size={10} /> First Dark: {firstDarkMeter}
                </span>
              )}
              {workOrder && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold"
                  style={{ background: '#ABC7FF20', color: '#ABC7FF' }}>
                  <Wrench size={10} /> {workOrder}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-4">
          {restorationPct !== null && phase !== 'normal' && phase !== 'fault_occurs' && phase !== 'fault_detection' && (
            <div className="text-right">
              <div className="text-white/40" style={{ fontSize: 10 }}>RESTORATION</div>
              <div className="text-white font-black" style={{ fontSize: 22, color: restorationPct === 100 ? '#02C9A8' : '#ABC7FF' }}>
                {restorationPct}%
              </div>
            </div>
          )}
          {metersOffline !== null && metersOffline > 0 && (
            <div className="text-right">
              <div className="text-white/40" style={{ fontSize: 10 }}>AFFECTED</div>
              <div className="font-black" style={{ fontSize: 22, color: '#E94B4B' }}>
                {metersOffline}
              </div>
            </div>
          )}
          {metersOnline !== null && (
            <div className="text-right">
              <div className="text-white/40" style={{ fontSize: 10 }}>ONLINE</div>
              <div className="font-black" style={{ fontSize: 22, color: '#02C9A8' }}>
                {metersOnline}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <svg width={svgWidth} height={svgHeight} viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          style={{ minWidth: svgWidth }}>
          <defs>
            {/* Animated dash for power flow */}
            <pattern id="powerFlow" patternUnits="userSpaceOnUse" width="20" height="4">
              <rect width="20" height="4" fill="none" />
              <rect x={tick % 2 === 0 ? 0 : 10} y="0" width="10" height="4" fill="#02C9A8" opacity="0.6" rx="2" />
            </pattern>
            <pattern id="powerFlowAlt" patternUnits="userSpaceOnUse" width="20" height="4">
              <rect width="20" height="4" fill="none" />
              <rect x={tick % 2 === 0 ? 0 : 10} y="0" width="10" height="4" fill="#ABC7FF" opacity="0.6" rx="2" />
            </pattern>
            {/* Glow filter for fault */}
            <filter id="faultGlow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="greenGlow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Substation icon on left */}
          <g transform={`translate(${SVG_PADDING - 10}, ${NODE_Y})`}>
            <rect x="-20" y="-25" width="40" height="50" rx="6" fill="#1a1f2e" stroke="#02C9A8" strokeWidth="1.5" />
            <text x="0" y="-30" textAnchor="middle" fill="#02C9A8" fontSize="9" fontWeight="bold">
              SUBSTATION
            </text>
            <line x1="-10" y1="-10" x2="10" y2="-10" stroke="#02C9A8" strokeWidth="2" />
            <line x1="-10" y1="0" x2="10" y2="0" stroke="#02C9A8" strokeWidth="2" />
            <line x1="-10" y1="10" x2="10" y2="10" stroke="#02C9A8" strokeWidth="2" />
            {/* Line to first node */}
            {nodePositions.length > 0 && (
              <line x1="20" y1="0" x2={nodePositions[0].x - SVG_PADDING + 10 - NODE_RADIUS} y2="0"
                stroke="#02C9A8" strokeWidth="3" opacity="0.8" />
            )}
          </g>

          {/* Feeder lines between nodes */}
          {nodePositions.map((node, i) => {
            if (i === 0) return null
            const prev = nodePositions[i - 1]
            const sw = switchItems[i - 1]
            const swState = sw?.state || 'closed'
            const isEnergised = node.status === 'energised' || node.status === 'restored_alt'
            const prevEnergised = prev.status === 'energised' || prev.status === 'restored_alt'
            const isFault = node.status === 'faulted' || node.status === 'fault_located'

            let lineColor = '#2a2f3e'
            let lineWidth = 3
            let lineOpacity = 0.4

            if (swState === 'closed' && prevEnergised && isEnergised) {
              lineColor = node.status === 'restored_alt' ? '#ABC7FF' : '#02C9A8'
              lineOpacity = 0.8
              lineWidth = 3
            } else if (swState === 'tripped' || isFault) {
              lineColor = '#E94B4B'
              lineOpacity = 0.6
              lineWidth = 3
            }

            return (
              <g key={`line-${i}`}>
                {/* Base line */}
                <line
                  x1={prev.x + NODE_RADIUS + 2} y1={NODE_Y}
                  x2={node.x - NODE_RADIUS - 2} y2={NODE_Y}
                  stroke={lineColor} strokeWidth={lineWidth} opacity={lineOpacity}
                  strokeDasharray={swState === 'open' ? '6 4' : 'none'}
                />
                {/* Animated power flow overlay */}
                {swState === 'closed' && prevEnergised && isEnergised && (
                  <line
                    x1={prev.x + NODE_RADIUS + 2} y1={NODE_Y}
                    x2={node.x - NODE_RADIUS - 2} y2={NODE_Y}
                    stroke={`url(#${node.status === 'restored_alt' ? 'powerFlowAlt' : 'powerFlow'})`}
                    strokeWidth={5} opacity="0.5"
                  />
                )}
                {/* Fault lightning bolt */}
                {isFault && swState === 'tripped' && (
                  <g transform={`translate(${(prev.x + node.x) / 2}, ${NODE_Y - 30})`} filter="url(#faultGlow)">
                    <polygon
                      points="-4,-12 2,-2 -2,-2 4,12 -1,2 3,2"
                      fill="#E94B4B" stroke="#FF6B6B" strokeWidth="0.5"
                    />
                  </g>
                )}
              </g>
            )
          })}

          {/* Switch indicators */}
          {switchItems.map((sw, i) => {
            const color = SWITCH_COLORS[sw.state] || '#6B7280'
            return (
              <g key={`sw-${i}`} transform={`translate(${sw.x}, ${NODE_Y + 30})`}>
                <rect x={-SWITCH_SIZE} y={-SWITCH_SIZE / 2} width={SWITCH_SIZE * 2} height={SWITCH_SIZE}
                  rx="3" fill="#1a1f2e" stroke={color} strokeWidth="1.5" />
                {sw.state === 'closed' && (
                  <line x1={-SWITCH_SIZE + 3} y1="0" x2={SWITCH_SIZE - 3} y2="0"
                    stroke={color} strokeWidth="2" />
                )}
                {sw.state === 'open' && (
                  <>
                    <line x1={-SWITCH_SIZE + 3} y1="0" x2={-2} y2="0"
                      stroke={color} strokeWidth="2" />
                    <line x1={2} y1="0" x2={SWITCH_SIZE - 3} y2="0"
                      stroke={color} strokeWidth="2" />
                    <circle cx="0" cy="0" r="2" fill="none" stroke={color} strokeWidth="1" />
                  </>
                )}
                {sw.state === 'tripped' && (
                  <>
                    <line x1={-SWITCH_SIZE + 3} y1="2" x2={SWITCH_SIZE - 3} y2="-3"
                      stroke={color} strokeWidth="2" />
                  </>
                )}
                <line x1="0" y1={-SWITCH_SIZE / 2} x2="0" y2={-SWITCH_SIZE / 2 - 10}
                  stroke={color} strokeWidth="1" opacity="0.5" />
                <text x="0" y={SWITCH_SIZE + 6} textAnchor="middle" fill={color} fontSize="8" fontWeight="bold">
                  {sw.name}
                </text>
                <text x="0" y={SWITCH_SIZE + 16} textAnchor="middle" fill="#ffffff40" fontSize="7">
                  {sw.state.toUpperCase()}
                </text>
              </g>
            )
          })}

          {/* Tie switch to alternate feeder */}
          {lastNode && (
            <g>
              <line x1={lastNode.x + NODE_RADIUS + 2} y1={NODE_Y}
                x2={tieX - 15} y2={NODE_Y}
                stroke={SWITCH_COLORS[tieState]} strokeWidth="2"
                strokeDasharray={tieState === 'open' ? '4 3' : 'none'}
                opacity="0.6" />
              <g transform={`translate(${tieX}, ${NODE_Y})`}>
                <rect x="-15" y="-20" width="30" height="40" rx="5"
                  fill="#1a1f2e" stroke={tieState === 'closed' ? '#ABC7FF' : '#6B7280'} strokeWidth="1.5"
                  strokeDasharray={tieState === 'open' ? '3 2' : 'none'} />
                <text x="0" y="3" textAnchor="middle" fill={tieState === 'closed' ? '#ABC7FF' : '#6B7280'}
                  fontSize="7" fontWeight="bold">TIE</text>
                <text x="0" y="-25" textAnchor="middle" fill="#ABC7FF" fontSize="8" fontWeight="bold">
                  ALT FEED
                </text>
                <text x="0" y="30" textAnchor="middle" fill="#ffffff40" fontSize="7">
                  {tieState.toUpperCase()}
                </text>
              </g>
            </g>
          )}

          {/* Transformer nodes */}
          {nodePositions.map((node, i) => {
            const color = STATUS_COLORS[node.status] || '#6B7280'
            const isFault = node.status === 'faulted' || node.status === 'fault_located'
            const isRestored = node.status === 'restored_alt'
            const isFirst = node.name === faultUpstream || node.name === faultDownstream

            return (
              <g key={`node-${i}`} transform={`translate(${node.x}, ${node.y})`}>
                {/* Outer glow for fault */}
                {isFault && (
                  <circle r={NODE_RADIUS + 6} fill="none" stroke="#E94B4B" strokeWidth="1"
                    opacity="0.3" filter="url(#faultGlow)">
                    <animate attributeName="r" values={`${NODE_RADIUS + 4};${NODE_RADIUS + 8};${NODE_RADIUS + 4}`}
                      dur="1.5s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.3;0.1;0.3"
                      dur="1.5s" repeatCount="indefinite" />
                  </circle>
                )}
                {/* Restored glow */}
                {isRestored && (
                  <circle r={NODE_RADIUS + 4} fill="none" stroke="#ABC7FF" strokeWidth="1"
                    opacity="0.2" filter="url(#greenGlow)" />
                )}

                {/* Main circle */}
                <circle r={NODE_RADIUS} fill="#0d1117" stroke={color} strokeWidth="2.5" />
                {/* Inner icon — transformer symbol */}
                <circle r="10" fill="none" stroke={color} strokeWidth="1.2" opacity="0.6" />
                <circle r="5" fill={color} opacity="0.15" />

                {/* Transformer name */}
                <text y={-NODE_RADIUS - 10} textAnchor="middle" fill="white" fontSize="10" fontWeight="bold">
                  {node.name}
                </text>

                {/* Meter count badge */}
                <g transform={`translate(${NODE_RADIUS - 2}, ${-NODE_RADIUS + 2})`}>
                  <rect x="-10" y="-8" width="20" height="16" rx="8" fill={color} opacity="0.9" />
                  <text x="0" y="4" textAnchor="middle" fill="white" fontSize="8" fontWeight="bold">
                    {node.meter_count || '?'}
                  </text>
                </g>

                {/* Status label below */}
                <text y={NODE_RADIUS + 18} textAnchor="middle" fill={color} fontSize="8" fontWeight="600">
                  {node.status === 'energised' ? 'ONLINE' :
                   node.status === 'faulted' ? 'FAULTED' :
                   node.status === 'fault_located' ? 'LOCATED' :
                   node.status === 'isolated' ? 'ISOLATED' :
                   node.status === 'restored_alt' ? 'ALT FEED' :
                   'OFFLINE'}
                </text>
              </g>
            )
          })}

          {/* Crew dispatch indicator */}
          {crewStatus === 'dispatched' && faultUpstream && (
            <g>
              {nodePositions.filter(n => n.name === faultUpstream || n.name === faultDownstream).map((n, i) => (
                <g key={`crew-${i}`} transform={`translate(${n.x}, ${n.y - NODE_RADIUS - 28})`}>
                  <rect x="-22" y="-8" width="44" height="16" rx="8" fill="#F59E0B" opacity="0.2" />
                  <text x="0" y="4" textAnchor="middle" fill="#F59E0B" fontSize="7" fontWeight="bold">
                    REPAIR
                  </text>
                </g>
              ))}
            </g>
          )}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        {[
          { color: '#02C9A8', label: 'Energised' },
          { color: '#E94B4B', label: 'Faulted' },
          { color: '#F59E0B', label: 'Located' },
          { color: '#6B7280', label: 'Isolated' },
          { color: '#ABC7FF', label: 'Alt Feed' },
        ].map(item => (
          <div key={item.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: item.color }} />
            <span className="text-white/40" style={{ fontSize: 10 }}>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
