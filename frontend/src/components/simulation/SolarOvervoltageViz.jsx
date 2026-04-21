/**
 * SolarOvervoltageViz — faithful React port of
 * simulation_sample/smoc_solar_overvoltage_dashboard.html.
 *
 * Design classes come from src/styles/smoc-samples.css, scoped under the
 * root `.smoc-sim` div so the light palette doesn't leak into the rest of
 * the dark app. Data points bind to networkState + scenario.parameters
 * from the local simulation engine.
 */

const NODE_STATE = (v, vOnset, vLimit) => {
  if (v >= vLimit) return 'over'
  if (v >= vOnset) return 'warn'
  return 'ok'
}

const BAND_COLOR = {
  over: '#E24B4A',
  warn: '#EF9F27',
  ok:   '#639922',
}

const NODE_STROKE = {
  over: '#E24B4A',
  warn: '#EF9F27',
  ok:   '#639922',
}
const NODE_FILL = {
  over: '#FCEBEB',
  warn: '#FAEEDA',
  ok:   '#EAF3DE',
}
const NODE_TEXT = {
  over: '#791F1F',
  warn: '#633806',
  ok:   '#27500A',
}

const ALGO_STEPS = [
  { num: 1, text: 'Measure V at each node',              sub: 'Smart meter telemetry · 1 s cycle' },
  { num: 2, text: <>Detect violation: V &gt; V<sub>max</sub></>, sub: '253 V threshold · tip node voltage' },
  { num: 3, text: 'Rank inverters by proximity',         sub: 'Electrical distance from tip' },
  { num: 4, text: <>Compute P<sub>curtail</sub> per inverter</>, sub: <>Droop: ΔP = k · (V − V<sub>ref</sub>)</> },
  { num: 5, text: 'Dispatch setpoint via DER comms',     sub: 'IEC 61850 / SunSpec Modbus' },
  { num: 6, text: <>Verify V returns below V<sub>max</sub></>, sub: 'Confirm & close alarm if resolved' },
]

// Map live algorithm_step to the 6-row stepper (done/active/pending).
function stepStates(current) {
  const currentIdx = (() => {
    if (!current || current === 'monitor') return 0
    if (current === 'detect') return 1
    if (current === 'compute') return 3
    if (current === 'curtail') return 4
    if (current === 'restore') return 5
    return 0
  })()
  return [0,1,2,3,4,5].map((i) => i < currentIdx ? 'done' : i === currentIdx ? 'active' : 'pending')
}

export default function SolarOvervoltageViz({ scenario, currentStep, networkState }) {
  const params = scenario?.parameters ?? {}
  const topo = params.topology ?? {}
  const nodes = topo.nodes ?? []
  const invFleet = topo.inverters ?? []
  const v_nominal = params.v_nominal ?? 230
  const v_onset = params.v_onset ?? 246
  const v_limit = params.v_limit ?? 253
  const k = params.k_droop_kw_per_v ?? 2.5

  const ns = networkState ?? {}
  const v_tip = ns.v_tip ?? v_nominal
  const delta_v = ns.delta_v ?? Math.max(0, +(v_tip - v_limit).toFixed(2))
  const delta_p = ns.delta_p_kw ?? +(k * delta_v).toFixed(2)
  const totalCurtail = ns.total_curtailment_kw ?? 0
  const algoStep = ns.algorithm_step ?? 'monitor'

  const nodeVoltages = ns.node_voltages ?? {}
  const nodeRows = nodes.map((n) => {
    const v = nodeVoltages[n.id] ?? v_nominal
    const state = NODE_STATE(v, v_onset, v_limit)
    return { id: n.id, v, state }
  })

  const invRows = (ns.inverters ?? []).map((inv) => ({
    ...inv,
    addr: inv.customer ?? invFleet.find(f => f.id === inv.id)?.customer ?? '—',
  }))

  const steps = stepStates(algoStep)

  const phaseLabel = {
    monitor: 'Monitoring',
    detect:  'Detecting overvoltage',
    compute: 'Computing curtailment',
    curtail: 'Curtailment in progress',
    restore: 'Voltage restored',
  }[algoStep] ?? 'Monitoring'

  const alarmSeverity = v_tip >= v_limit ? 'cr' : v_tip >= v_onset ? 'ma' : 'ok'
  const topbarStatusClass =
    alarmSeverity === 'cr' ? 'danger' :
    alarmSeverity === 'ma' ? 'warn' :
    'ok'

  return (
    <div className="smoc-sim">
      {/* TOP BAR */}
      <div className="topbar">
        <div>
          <div className="topbar-title">SMOC — Smart Meter Operations Centre</div>
          <div className="topbar-meta">
            Simulation · {params.feeder_name ?? 'LV Feeder'}
            {currentStep ? ` · Step ${currentStep}/${scenario?.total_steps ?? '?'}` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
            Phase: <span style={{ color: '#185FA5', fontWeight: 500 }}>{phaseLabel}</span>
          </div>
          <div className={`topbar-status ${topbarStatusClass}`}>
            <div className={`pulse ${alarmSeverity === 'ma' ? 'amber' : alarmSeverity === 'ok' ? 'green' : ''}`} />
            {alarmSeverity === 'cr' ? 'ACTIVE ALARM' : alarmSeverity === 'ma' ? 'WARNING' : 'NORMAL'}
          </div>
        </div>
      </div>

      {/* ROW 1: KPIs */}
      <div className="grid">
        <div className="panel">
          <div className="panel-title">{params.feeder_name ?? 'Feeder'} — Network status</div>
          <div className="metrics">
            <div className="metric">
              <div className="metric-label">Peak voltage</div>
              <div className={`metric-val ${alarmSeverity === 'cr' ? 'danger' : alarmSeverity === 'ma' ? 'warn' : 'ok'}`}>
                {v_tip.toFixed(1)}<span className="metric-unit"> V</span>
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Net export</div>
              <div className="metric-val warn">
                {((ns.pv_output_kw ?? 0) - (ns.load_kw ?? 0)).toFixed(0)}<span className="metric-unit"> kW</span>
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Solar gen.</div>
              <div className="metric-val">
                {(ns.pv_output_kw ?? 0).toFixed(0)}<span className="metric-unit"> kW</span>
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Solar irradiance &amp; load</div>
          <Strip label="Irradiance"          value={`${Math.round(800 + (v_tip - v_nominal) * 15)} W/m²`} />
          <Strip label="Neighbourhood load"  value={`${(ns.load_kw ?? 0).toFixed(0)} kW`} />
          <Strip label="Active inverters"    value={`${invRows.length || invFleet.length} / ${invFleet.length || invRows.length}`} />
          <Strip label="Power factor (avg)"  value="0.98 lag" />
        </div>

        <div className="panel">
          <div className={`panel-title ${alarmSeverity === 'cr' ? 'danger' : 'warn'}`}>
            Active alarms {alarmSeverity !== 'ok' ? '(2)' : '(0)'}
          </div>
          {alarmSeverity !== 'ok' ? (
            <>
              <div className={`alarm ${alarmSeverity}`}>
                <div><div className="ab">{alarmSeverity === 'cr' ? 'CRITICAL' : 'MAJOR'}</div></div>
                <div>
                  <div className="alarm-text">
                    Overvoltage — tip node {v_tip.toFixed(1)} V
                    {alarmSeverity === 'cr' ? ` exceeds ${v_limit} V` : ` approaching ${v_limit} V limit`}
                  </div>
                  <div className="alarm-time">Active · Step {currentStep ?? '—'}</div>
                </div>
              </div>
              <div className="alarm in">
                <div><div className="ab">INFO</div></div>
                <div>
                  <div className="alarm-text">
                    {totalCurtail > 0
                      ? `Curtailment dispatched — ${totalCurtail.toFixed(1)} kW across inverters`
                      : 'Droop algorithm armed'}
                  </div>
                  <div className="alarm-time">Automatic action</div>
                </div>
              </div>
            </>
          ) : (
            <div className="alarm ok">
              <div><div className="ab">OK</div></div>
              <div><div className="alarm-text">All nodes within nominal band</div></div>
            </div>
          )}
        </div>
      </div>

      {/* ROW 2: Voltage profile + Algorithm + Curtailment calc */}
      <div className="grid-bot">
        {/* Voltage profile */}
        <div className="panel">
          <div className="panel-title">{params.feeder_name ?? 'Feeder'} — Node voltage profile</div>
          <div style={{ marginBottom: 6, fontSize: 9, color: 'var(--color-text-secondary)' }}>
            Nominal {v_nominal} V · Limit {v_limit} V · Red = violation
          </div>
          {nodeRows.map((n) => {
            const lo = v_nominal - 5
            const hi = v_limit + 5
            const pct = Math.min(100, Math.max(0, ((n.v - lo) / (hi - lo)) * 100))
            return (
              <div className="vbar-row" key={n.id}>
                <div className="vbar-label">{n.id}</div>
                <div className="vbar-bg">
                  <div className="vbar-fill" style={{ width: `${pct}%`, background: BAND_COLOR[n.state] }} />
                </div>
                <div className={`vbar-val ${n.state}`}>{n.v.toFixed(1)} V</div>
              </div>
            )
          })}
          <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 9, color: 'var(--color-text-secondary)' }}>
            <Legend color="#E24B4A" label="Overvoltage" />
            <Legend color="#639922" label="Normal" />
            <Legend color="#EF9F27" label="Warning" />
          </div>
        </div>

        {/* Algorithm stepper */}
        <div className="panel">
          <div className="panel-title">Droop curtailment algorithm</div>
          <div className="algo-steps">
            {ALGO_STEPS.map((s, i) => (
              <div className={`algo-step ${steps[i]}`} key={i}>
                <div className="step-num">{s.num}</div>
                <div>
                  <div className="step-text">{s.text}</div>
                  <div className="step-sub">{s.sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Curtailment calculation */}
        <div className="panel">
          <div className="panel-title">Curtailment calculation</div>
          <div
            style={{
              background: 'var(--color-background-secondary)', borderRadius: 6,
              padding: '8px 10px', marginBottom: 6,
              fontSize: 10, fontFamily: 'var(--font-mono, monospace)',
              color: 'var(--color-text-primary)', lineHeight: 1.7,
            }}
          >
            V<sub>tip</sub> = <span style={{ color: '#993C1D', fontWeight: 500 }}>{v_tip.toFixed(1)} V</span><br />
            V<sub>ref</sub> = {v_nominal.toFixed(1)} V<br />
            V<sub>max</sub> = {v_limit.toFixed(1)} V<br />
            ΔV = <span style={{ color: '#993C1D', fontWeight: 500 }}>{delta_v >= 0 ? '+' : ''}{delta_v.toFixed(2)} V</span><br />
            <br />
            Droop gain k = {k} kW/V<br />
            ΔP<sub>total</sub> = k × ΔV<br />
            &nbsp;&nbsp;&nbsp;&nbsp;= {k} × {delta_v.toFixed(2)} = <span style={{ color: '#993C1D', fontWeight: 500 }}>{delta_p.toFixed(2)} kW</span><br />
            <br />
            Split across {invRows.filter(r => r.is_curtailing).length || 6} inverters<br />
            proportional to P<sub>available</sub>:<br />
            New P<sub>set</sub> = P<sub>avail</sub> − ΔP<br />
          </div>
          <div style={{ fontSize: 9, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
            k is configurable. Higher k = faster voltage response but more solar curtailment. Droop is proportional — voltage violation drives curtailment depth linearly.
          </div>
        </div>
      </div>

      {/* ROW 3: Smart inverter table + Network topology SVG */}
      <div className="grid-2" style={{ marginTop: 8 }}>
        {/* Inverter table */}
        <div className="panel">
          <div className="panel-title">
            Smart inverter status — {params.feeder_name ?? 'Feeder'} ({invRows.length} DER units)
          </div>
          <table>
            <thead>
              <tr>
                <th>ID</th><th>Address</th>
                <th>P<sub>avail</sub> kW</th><th>P<sub>set</sub> kW</th>
                <th>Output %</th><th>Node</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {invRows.map((inv) => {
                const pct = Math.round(((inv.setpoint_kw ?? inv.available_kw ?? 0) / Math.max(inv.available_kw ?? inv.rated_kw ?? 1, 0.01)) * 100)
                const nodeV = nodeVoltages[inv.node] ?? v_nominal
                return (
                  <tr key={inv.id}>
                    <td style={{ fontWeight: 500 }}>{inv.id}</td>
                    <td style={{ fontSize: 9, color: 'var(--color-text-secondary)' }}>{inv.addr}</td>
                    <td>{(inv.available_kw ?? 0).toFixed(1)}</td>
                    <td>{(inv.setpoint_kw ?? 0).toFixed(1)}</td>
                    <td>
                      <div className="pbar-wrap">
                        <div
                          className={`pbar ${inv.is_curtailing ? 'warn' : 'ok'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>{' '}
                      {pct}%
                    </td>
                    <td style={{ fontSize: 9 }}>{inv.node} {nodeV.toFixed(1)} V</td>
                    <td>
                      <span className={`badge ${inv.is_curtailing ? 'warn' : 'ok'}`}>
                        {inv.is_curtailing ? 'Curtailing' : 'Normal'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Network topology SVG */}
        <div className="panel">
          <div className="panel-title">{params.feeder_name ?? 'Feeder'} — Network topology</div>
          <svg width="100%" viewBox="0 0 340 290" role="img">
            <title>LV feeder topology</title>
            <defs>
              <marker id="solar-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </marker>
            </defs>

            <rect x="8" y="8" width="324" height="274" rx="8" fill="none" stroke="var(--color-border-tertiary)" strokeWidth="0.5" strokeDasharray="4 3" />
            <text x="20" y="22" fontSize="9" fill="var(--color-text-secondary)">Suburb · {params.feeder_name ?? 'Feeder'}</text>

            {/* Substation */}
            <rect x="135" y="26" width="70" height="28" rx="5" fill="#E6F1FB" stroke="#185FA5" strokeWidth="0.5" />
            <text x="170" y="37" fontSize="9" fontWeight="500" fill="#0C447C" textAnchor="middle">Zone Sub.</text>
            <text x="170" y="48" fontSize="8" fill="#185FA5" textAnchor="middle">11kV/400V TX</text>
            <line x1="170" y1="54" x2="170" y2="78" stroke="#888780" strokeWidth="1.5" markerEnd="url(#solar-arrow)" />

            {nodeRows.slice(0, 7).map((n, idx) => {
              const col = idx % 2 === 0 ? 135 : 217
              const row = 78 + Math.floor(idx / 2) * 44
              const state = n.state
              const fill = NODE_FILL[state]
              const stroke = NODE_STROKE[state]
              const text = NODE_TEXT[state]
              const strokeW = state === 'over' ? 1.2 : 0.5
              return (
                <g key={n.id}>
                  <rect x={col} y={row} width="70" height="24" rx="4" fill={fill} stroke={stroke} strokeWidth={strokeW} />
                  <text x={col + 35} y={row + 15} fontSize="9" fontWeight="500" fill={text} textAnchor="middle">
                    {state === 'over' ? '⚠ ' : ''}{n.id} · {n.v.toFixed(1)} V
                  </text>
                </g>
              )
            })}

            <text x="300" y="175" fontSize="14">☀</text>
            <text x="300" y="223" fontSize="14">☀</text>
            <text x="300" y="267" fontSize="14">☀</text>

            <rect x="12" y="240" width="8" height="8" rx="2" fill="#EAF3DE" stroke="#639922" strokeWidth="0.5" />
            <text x="24" y="248" fontSize="8" fill="var(--color-text-secondary)">Normal</text>
            <rect x="12" y="254" width="8" height="8" rx="2" fill="#FAEEDA" stroke="#EF9F27" strokeWidth="0.5" />
            <text x="24" y="262" fontSize="8" fill="var(--color-text-secondary)">Warning</text>
            <rect x="12" y="268" width="8" height="8" rx="2" fill="#FCEBEB" stroke="#E24B4A" strokeWidth="0.8" />
            <text x="24" y="276" fontSize="8" fill="var(--color-text-secondary)">Violation</text>
          </svg>
        </div>
      </div>

      {/* Standards footer */}
      {Array.isArray(params.standards) && params.standards.length > 0 && (
        <div className="panel" style={{ marginTop: 8 }}>
          <div className="panel-title">Standards</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {params.standards.map(s => <span key={s} className="badge info">{s}</span>)}
          </div>
        </div>
      )}
    </div>
  )
}

function Strip({ label, value }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: 'var(--color-background-secondary)', borderRadius: 6,
      padding: '5px 8px', marginBottom: 5, fontSize: 10,
    }}>
      <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <span style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>{value}</span>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
      <span style={{ width: 10, height: 4, background: color, borderRadius: 2, display: 'inline-block' }} />
      {label}
    </span>
  )
}
