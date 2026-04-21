/**
 * EvChargingViz — faithful port of
 * simulation_sample/ev_charging_smoc_dashboard.html.
 *
 * Light-theme SMOC layout driven by live networkState. Bays + forecast +
 * OCPP curtailment commands + phase currents all read from the backend
 * scenario step state; onCommand (optional) is wired through to the
 * parent so clicking "Send" in the OCPP panel dispatches a real sim
 * command.
 */

export default function EvChargingViz({ scenario, currentStep, networkState, onCommand }) {
  const params = scenario?.parameters ?? {}
  const ns = networkState ?? {}
  const bays = ns.bays ?? []
  const forecast = ns.forecast ?? params.forecast_4h ?? []
  const loadingPct = ns.loading_percent ?? 0
  const totalKw = ns.transformer_load_kw ?? ns.ev_demand_kw ?? 0
  const txCapKva = params.transformer_capacity_kva ?? 150
  const wT = ns.winding_temp_c ?? 0
  const oT = ns.oil_temp_c ?? 0
  const wAlarm = params.winding_alarm_c ?? 90
  const wTrip = params.winding_trip_c ?? 105
  const activeSessions = ns.active_sessions ?? bays.filter(b => b.plugged).length
  const stationEnvelope = ns.station_setpoint_kw ?? params.station_envelope_kw ?? 600
  const curtailActive = !!ns.curtailment_active
  const reqReduce = Math.max(0, totalKw - stationEnvelope).toFixed(0)

  const loadSeverity = loadingPct > 100 ? 'danger' : loadingPct > 80 ? 'warn' : 'ok'
  const loadPhrase = loadingPct > 100 ? 'OVERLOADED' : loadingPct > 80 ? 'WARNING' : 'NORMAL'
  const loadBarPct = Math.min(100, (loadingPct / 150) * 100) // 0–150% range → 0–100% width
  const loadBarColor = loadingPct > 100 ? '#E24B4A' : loadingPct > 80 ? '#EF9F27' : '#639922'

  const wSeverity = wT >= wTrip ? 'danger' : wT >= wAlarm ? 'warn' : 'ok'

  const phaseLbl = (() => {
    if (activeSessions === 0) return 'Station energised — no vehicles'
    if (curtailActive) return `Curtailed — station at ${stationEnvelope} kW envelope`
    if (loadingPct > 100) return `Overload — ${activeSessions} vehicles drawing ${totalKw.toFixed(0)} kW`
    return `${activeSessions} vehicle${activeSessions === 1 ? '' : 's'} charging`
  })()

  const topStatus = loadingPct > 100
    ? { pulse: 'red', color: '#A32D2D', text: 'TX OVERLOAD' }
    : loadingPct > 80
      ? { pulse: 'amber', color: '#854F0B', text: 'TX OVERLOAD WARNING' }
      : { pulse: 'green', color: '#3B6D11', text: 'NORMAL' }

  const dispatchCmd = (cmd, value) => {
    onCommand?.(cmd, value)
  }

  const maxForecast = Math.max(220, ...forecast.map(f => Math.max(f.predicted_kw || 0, f.curtailed_kw || 0)))

  return (
    <div className="smoc-sim">
      {/* TOP BAR */}
      <div className="topbar">
        <div>
          <div className="tb-title">SMOC — EV Fast Charging Station · {params.station_name ?? 'Depot'}</div>
          <div className="tb-meta">
            {currentStep ? `Step ${currentStep}/${scenario?.total_steps ?? '?'}` : 'Awaiting start'}
            {' · '}4-bay DC fast charger · {params.transformer_id_label ?? 'TX-07'} · {txCapKva} kVA
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
            Phase: <span style={{ fontWeight: 500, color: '#185FA5' }}>{phaseLbl}</span>
          </div>
          <div className="tb-status" style={{ color: topStatus.color }}>
            <div className={`pulse ${topStatus.pulse}`} />
            {topStatus.text}
          </div>
        </div>
      </div>

      {/* ROW 1: KPIs */}
      <div className="g4">
        <div className="mcard">
          <div className="mlabel">TX loading</div>
          <div className={`mval ${loadSeverity}`}>{loadingPct.toFixed(0)}<span className="munit">%</span></div>
        </div>
        <div className="mcard">
          <div className="mlabel">Total station draw</div>
          <div className={`mval ${loadSeverity}`}>{totalKw.toFixed(0)}<span className="munit"> kW</span></div>
        </div>
        <div className="mcard">
          <div className="mlabel">TX rated capacity</div>
          <div className="mval">{txCapKva.toFixed(0)}<span className="munit"> kVA</span></div>
        </div>
        <div className="mcard">
          <div className="mlabel">Active sessions</div>
          <div className="mval warn">{activeSessions}<span className="munit"> / {bays.length || 4}</span></div>
        </div>
      </div>

      {/* ROW 2: Transformer panel + Bays + Alarms */}
      <div className="g3">
        {/* Transformer */}
        <div className="panel">
          <div className={`ptitle ${loadSeverity}`}>Transformer {params.transformer_id_label ?? 'TX-07'} — loading detail</div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Loading</span>
              <span style={{ fontWeight: 500, color: loadBarColor }}>{loadingPct.toFixed(0)}% — {loadPhrase}</span>
            </div>
            <div className="loadbar-wrap" style={{ height: 18 }}>
              <div className="loadbar" style={{ width: `${loadBarPct}%`, background: loadBarColor, height: 18 }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--color-text-secondary)', marginTop: 2 }}>
              <span>0%</span>
              <span style={{ color: '#854F0B' }}>100% rated</span>
              <span>150%</span>
            </div>
          </div>
          <Strip label="Rated capacity"    value={`${txCapKva} kVA`} />
          <Strip label="Current draw"      value={`${totalKw.toFixed(0)} kVA`} severity={loadSeverity} />
          <Strip label="Winding temp"      value={`${wT.toFixed(0)}°C`} severity={wSeverity} />
          <Strip label="Oil temp"          value={`${oT.toFixed(0)}°C`} />
          <Strip label="Thermal alarm"     value={`${wAlarm.toFixed(0)}°C`} />
          <Strip label="Thermal trip"      value={`${wTrip.toFixed(0)}°C`} />
          <Strip label="Power factor"      value="0.97 lag" />
        </div>

        {/* Bays */}
        <div className="panel">
          <div className="ptitle">EV charging bays — session status</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
            {bays.slice(0, 4).map((b) => {
              const state = !b.plugged ? 'idle'
                : b.setpoint_kw < b.rated_kw && curtailActive ? 'curtailed'
                : 'charging'
              const socPct = Math.max(0, Math.min(100, b.soc_pct ?? 0))
              const pwrColor = state === 'idle' ? 'var(--color-text-secondary)' : state === 'curtailed' ? '#854F0B' : '#0C447C'
              const socColor = state === 'idle' ? '#888780' : state === 'curtailed' ? '#EF9F27' : '#378ADD'
              return (
                <div className={`ev-bay ${state}`} key={b.id}>
                  <div className="bay-id">{b.id} — DC {b.rated_kw} kW ({b.connector})</div>
                  <div className="bay-pwr" style={{ color: pwrColor }}>{b.charging_kw?.toFixed(0) ?? 0} kW</div>
                  <div className="soc-bar-wrap">
                    <div className="soc-bar" style={{ width: `${socPct}%`, background: socColor }} />
                  </div>
                  <div className="phase-tag">
                    {b.plugged ? `SoC ${socPct.toFixed(0)}% · Setpoint ${b.setpoint_kw?.toFixed(0)} kW` : 'Idle — no vehicle'}
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <span className={`badge ${state === 'idle' ? 'neutral' : state === 'curtailed' ? 'warn' : 'info'}`}>
                      {state === 'idle' ? 'Idle' : state === 'curtailed' ? 'Curtailed' : 'Charging'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
          <div style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
            Charger protocol: CCS2 · {params.protocol ?? 'OCPP 2.0.1'} · Smart charging enabled
          </div>
        </div>

        {/* Alarms + curtailment strategy */}
        <div className="panel">
          <div className={`ptitle ${loadSeverity}`}>Active alarms</div>
          {loadingPct > 100 && (
            <div className="alarm critical">
              <div><div className="alarm-badge">CRITICAL</div></div>
              <div>
                <div className="alarm-text">
                  {params.transformer_id_label ?? 'TX-07'} overloaded — {totalKw.toFixed(0)} kVA on {txCapKva} kVA rated unit ({loadingPct.toFixed(0)}%).
                </div>
                <div className="alarm-time">Active this step</div>
              </div>
            </div>
          )}
          {wT >= wAlarm && (
            <div className={`alarm ${wSeverity === 'danger' ? 'critical' : 'major'}`}>
              <div><div className="alarm-badge">{wSeverity === 'danger' ? 'CRITICAL' : 'MAJOR'}</div></div>
              <div>
                <div className="alarm-text">
                  TX winding temperature {wSeverity === 'danger' ? 'critical' : 'rising'} — {wT.toFixed(0)}°C (limit {wTrip.toFixed(0)}°C).
                  Thermal headroom {(wTrip - wT).toFixed(0)}°C.
                </div>
                <div className="alarm-time">Sensor feed</div>
              </div>
            </div>
          )}
          {loadingPct <= 100 && wT < wAlarm && (
            <div className="alarm ok">
              <div><div className="alarm-badge">OK</div></div>
              <div><div className="alarm-text">Station within envelope — no action required.</div></div>
            </div>
          )}

          <div style={{ marginTop: 10 }}>
            <div className="ptitle ok">Curtailment strategy</div>
            <Strip label="Target station limit" value={`${stationEnvelope} kW`} severity="ok" />
            <Strip label="Required reduction"   value={`${reqReduce} kW`}        severity={reqReduce > 0 ? 'danger' : 'ok'} />
            <Strip label="Method"               value="OCPP SetChargingProfile" />
            <Strip label="Priority order"       value="SoC-based (highest first)" />
          </div>
        </div>
      </div>

      {/* ROW 3: Forecast bar chart + OCPP commands */}
      <div className="g3" style={{ marginBottom: 8 }}>
        {/* Forecast */}
        <div className="panel" style={{ gridColumn: 'span 2' }}>
          <div className="ptitle">EV demand forecast — next 4 hours</div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <LegendChip color="#B5D4F4" label="Forecast arrivals (kW)" />
            <LegendChip color="#C0DD97" label="After curtailment (kW)" />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 160, padding: '0 2px' }}>
            {forecast.slice(0, 16).map((f, i) => {
              const ph = Math.max(2, Math.round((f.predicted_kw / maxForecast) * 150))
              const ch = Math.max(2, Math.round((f.curtailed_kw / maxForecast) * 150))
              return (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 150, width: '100%' }}>
                    <div style={{ flex: 1, background: '#B5D4F4', height: ph, borderRadius: '3px 3px 0 0', transition: 'height 1s ease' }} />
                    <div style={{ flex: 1, background: '#C0DD97', height: ch, borderRadius: '3px 3px 0 0', transition: 'height 1s ease' }} />
                  </div>
                  {i % 4 === 0 && (
                    <div style={{ fontSize: 8, color: 'var(--color-text-secondary)' }}>+{f.t_offset_min}m</div>
                  )}
                </div>
              )
            })}
          </div>
          <div style={{ marginTop: 6, fontSize: 10, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
            Forecast model: historical arrival patterns + time-of-day · Peak predicted 16:30–17:30 (evening commute).
          </div>
        </div>

        {/* OCPP commands */}
        <div className="panel">
          <div className="ptitle">OCPP curtailment commands</div>
          <div className="cmd-list">
            <div className="cmd-row">
              <span className="cmd-label">Station limit</span>
              <span className="cmd-val">{stationEnvelope} kW</span>
              <button className={`cmd-btn ${curtailActive ? 'active' : ''}`} onClick={() => dispatchCmd('curtail_ev_charger', stationEnvelope)}>Send</button>
            </div>
            {bays.slice(0, 4).map((b, i) => (
              <div className="cmd-row" key={b.id}>
                <span className="cmd-label">Bay {i + 1} setpoint</span>
                <span className="cmd-val">{(b.setpoint_kw ?? 0).toFixed(0)} kW</span>
                <button
                  className="cmd-btn"
                  disabled={!b.plugged}
                  style={!b.plugged ? { opacity: 0.4 } : undefined}
                  onClick={() => b.plugged && dispatchCmd('curtail_bay', b.setpoint_kw)}
                >
                  {b.plugged ? 'Send' : '—'}
                </button>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 10, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
            Protocol: {params.protocol ?? 'OCPP 2.0.1'}<br />
            Msg: SetChargingProfile<br />
            Profile: TxDefaultProfile<br />
            Stack level: 3 (operator)
          </div>
          <div
            style={{
              marginTop: 6, fontSize: 10, padding: '6px 8px', borderRadius: 6,
              background: curtailActive ? '#EAF3DE' : '#FAEEDA',
              color: curtailActive ? '#27500A' : '#633806',
            }}
          >
            {curtailActive
              ? `Curtailment active — station capped at ${stationEnvelope} kW`
              : `Awaiting dispatch — station at ${loadingPct.toFixed(0)}% loading`}
          </div>
        </div>
      </div>
    </div>
  )
}

function Strip({ label, value, severity }) {
  return (
    <div className="strip">
      <span className="strip-l">{label}</span>
      <span className={`strip-v ${severity ?? ''}`}>{value}</span>
    </div>
  )
}

function LegendChip({ color, label }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--color-text-secondary)' }}>
      <span style={{ width: 14, height: 10, background: color, borderRadius: 2, display: 'inline-block' }} />
      {label}
    </span>
  )
}
