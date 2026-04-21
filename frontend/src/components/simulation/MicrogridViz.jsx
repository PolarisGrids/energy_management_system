/**
 * MicrogridViz — faithful port of
 * simulation_sample/peaking_microgrid_smoc_dashboard.html.
 *
 * 4-DER peaking microgrid with reverse-flow detection, VPP aggregation,
 * and island-mode capability. Renders from networkState +
 * scenario.parameters shape emitted by the simulation engine.
 */

const ASSET_DEFAULTS = {
  pv:         { label: 'PV array',        rated_kw: 200 },
  gas_peaker: { label: 'Gas peaker',      rated_kw: 150 },
  bess:       { label: 'BESS',            rated_kw: 100 },
  ev_fleet:   { label: 'EV fleet (V2G)',  rated_kw: 120 },
}

export default function MicrogridViz({ scenario, currentStep, networkState }) {
  const params = scenario?.parameters ?? {}
  const ns = networkState ?? {}
  const assets = params.assets ?? []
  const relayKw = params.reverse_power_relay_kw ?? -150
  const islanded = !!ns.islanded
  const mode = ns.aggregation_mode ?? 'individual'
  const phase = ns.phase ?? 'startup'

  const pvKw = ns.pv_kw ?? 0
  const gasKw = ns.gas_kw ?? 0
  const bessKw = ns.bess_kw ?? 0
  const evKw = ns.ev_fleet_kw ?? 0
  const totalGen = ns.total_gen_kw ?? Math.max(0, pvKw + gasKw + Math.max(0, bessKw) + Math.max(0, evKw))
  const localLoad = ns.local_load_kw ?? 0
  const netExport = ns.net_export_kw ?? 0
  const reversePower = ns.reverse_power_kw ?? 0
  const relayMargin = ns.relay_margin_kw ?? Math.max(0, Math.abs(relayKw) - reversePower)
  const vpu = ns.v_pu_injection ?? 1.0
  const vv = ns.v_v_injection ?? Math.round(vpu * 230 * 10) / 10

  // Flow direction and severity
  const flowSev = reversePower > 0
    ? (relayMargin < 20 ? 'cr' : relayMargin < 40 ? 'ma' : 'in')
    : 'ok'
  const flowBadgeText = reversePower > 0
    ? `← ${(-reversePower).toFixed(0)} kW (reverse)`
    : netExport < 0
      ? `→ ${Math.abs(netExport).toFixed(0)} kW (import)`
      : `→ ${netExport.toFixed(0)} kW (import)`
  const flowBadgeClass = reversePower > 0 ? 'flow-rev' : 'flow-fwd'
  const flowBarPct = (() => {
    if (reversePower > 0) return Math.min(100, (reversePower / Math.abs(relayKw)) * 100)
    if (netExport < 0)    return 50 + Math.min(50, (Math.abs(netExport) / Math.abs(relayKw)) * 50)
    return 50
  })()
  const flowBarColor = flowSev === 'cr' ? '#E24B4A' : flowSev === 'ma' ? '#EF9F27' : flowSev === 'in' ? '#378ADD' : '#639922'

  const topStatus = islanded
    ? { pulse: 'amber', color: '#854F0B', text: 'ISLAND MODE' }
    : flowSev === 'cr'
      ? { pulse: 'red', color: '#A32D2D', text: 'REVERSE POWER FLOW' }
      : flowSev === 'ma'
        ? { pulse: 'amber', color: '#854F0B', text: 'APPROACHING RELAY LIMIT' }
        : { pulse: 'green', color: '#3B6D11', text: 'STABLE' }

  // Resolve a DER asset by id/type — falls back to defaults if the scenario
  // hasn't registered one.
  const assetByType = (t) => assets.find(a => a.type === t) ?? { type: t, ...ASSET_DEFAULTS[t] }
  const pv = assetByType('pv')
  const gas = assetByType('gas_peaker')
  const bess = assetByType('bess')
  const evf = assetByType('ev_fleet')

  const derCards = [
    { key: 'pv',   asset: pv,  kw: pvKw,  color: '#185FA5', badgeClass: 'info',
      barColor: '#378ADD', sub: `Rated ${pv.rated_kw} kW · solar PV`,
      mode: 'Mode: max power point', badge: pvKw > 0 ? 'Exporting' : 'Idle' },
    { key: 'gas', asset: gas, kw: gasKw, color: '#3B6D11', badgeClass: 'ok',
      barColor: '#639922', sub: `Rated ${gas.rated_kw} kW · peaking`,
      mode: islanded ? 'Mode: grid forming' : 'Mode: frequency support',
      badge: gasKw > 0 ? 'Online' : 'Standby' },
    { key: 'bess', asset: bess, kw: bessKw, color: bessKw < 0 ? '#854F0B' : '#3B6D11',
      badgeClass: bessKw === 0 ? 'warn' : bessKw < 0 ? 'warn' : 'ok',
      barColor: bessKw < 0 ? '#EF9F27' : '#639922',
      sub: `Rated ±${bess.rated_kw} kW · ${bess.capacity_kwh ?? 300} kWh`,
      mode: bessKw < 0 ? 'Mode: charging (absorb)' : bessKw > 0 ? 'Mode: discharging' : 'Mode: standby',
      badge: bessKw < 0 ? `Charging · SoC ${ns.bess_soc_pct ?? 68}%` : bessKw > 0 ? 'Discharging' : `Idle · SoC ${ns.bess_soc_pct ?? 68}%` },
    { key: 'ev', asset: evf, kw: evKw, color: '#26215C', badgeClass: 'purple',
      barColor: '#7F77DD',
      sub: `V2G ±${evf.rated_kw} kW · ${evf.vehicles ?? 8} vehicles · avg SoC ${ns.ev_fleet_soc_pct ?? 68}%`,
      mode: evKw < 0 ? 'Mode: boosted load' : evKw > 0 ? 'Mode: discharge' : 'Mode: idle',
      badge: `${evf.vehicles ?? 8} vehicles` },
  ]

  return (
    <div className="smoc-sim">
      {/* TOP BAR */}
      <div className="topbar">
        <div>
          <div className="tb-title">SMOC — Peaking Microgrid · {params.microgrid_name ?? 'Riverside'}</div>
          <div className="tb-meta">
            {currentStep ? `Step ${currentStep}/${scenario?.total_steps ?? '?'}` : 'Awaiting start'}
            {' · '}4-DER virtual power plant · Feeder {params.feeder_name ?? 'F7'} · GCP-01
          </div>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>
            Mode: <span style={{ fontWeight: 500, color: '#185FA5' }}>{phase.replace(/_/g, ' ')}</span>
          </div>
          <div className="tb-status" style={{ color: topStatus.color }}>
            <div className={`pulse ${topStatus.pulse}`} />
            {topStatus.text}
          </div>
        </div>
      </div>

      {/* KPI row */}
      <div className="g4">
        <div className="mcard">
          <div className="mlabel">Net feeder flow</div>
          <div className={`mval ${reversePower > 0 ? 'danger' : 'ok'}`}>
            {netExport < 0 ? '+' : '-'}{Math.abs(netExport).toFixed(0)}<span className="munit"> kW</span>
          </div>
        </div>
        <div className="mcard">
          <div className="mlabel">Total DER output</div>
          <div className="mval info">{totalGen.toFixed(0)}<span className="munit"> kW</span></div>
        </div>
        <div className="mcard">
          <div className="mlabel">Local load</div>
          <div className="mval">{localLoad.toFixed(0)}<span className="munit"> kW</span></div>
        </div>
        <div className="mcard">
          <div className="mlabel">Reverse flow margin</div>
          <div className={`mval ${flowSev === 'cr' ? 'danger' : flowSev === 'ma' ? 'warn' : 'ok'}`}>
            {relayMargin.toFixed(0)}<span className="munit"> kW</span>
          </div>
        </div>
      </div>

      {/* ROW 2: Feeder + DER cards + Alarms */}
      <div className="g3">
        {/* Feeder */}
        <div className="panel">
          <div className={`ptitle ${flowSev === 'cr' ? 'danger' : 'warn'}`}>Feeder {params.feeder_name ?? 'F7'} — transformer &amp; flow</div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Feeder power flow</span>
              <span
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  fontSize: 10, fontWeight: 500, padding: '3px 7px', borderRadius: 4,
                  background: flowBadgeClass === 'flow-rev' ? '#FCEBEB' : '#EAF3DE',
                  color: flowBadgeClass === 'flow-rev' ? '#791F1F' : '#27500A',
                }}
              >
                {flowBadgeText}
              </span>
            </div>
            <div className="loadbar-wrap" style={{ height: 14 }}>
              <div className="loadbar" style={{ width: `${flowBarPct}%`, background: flowBarColor, height: 14 }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--color-text-secondary)', marginTop: 2 }}>
              <span>{relayKw} kW (trip)</span>
              <span style={{ color: '#639922' }}>0 (neutral)</span>
              <span>+{Math.abs(relayKw)} kW import</span>
            </div>
          </div>
          <Strip label="Reverse-flow relay"   value={`armed at ${relayKw} kW`} severity="danger" />
          <Strip label="Relay headroom"        value={`${relayMargin.toFixed(0)} kW`}
                 severity={flowSev === 'cr' ? 'danger' : flowSev === 'ma' ? 'warn' : 'ok'} />
          <Strip label="Injection voltage"     value={`${vv.toFixed(1)} V (${vpu.toFixed(2)} pu)`}
                 severity={vpu >= 1.08 ? 'danger' : vpu >= 1.05 ? 'warn' : 'ok'} />
          <Strip label="Voltage limit"         value={`${params.v_limit_v ?? 253} V (1.10 pu)`} />
          <Strip label="Island capable"        value={islanded ? 'Islanded' : 'Grid-tied'}
                 severity={islanded ? 'warn' : 'ok'} />
          <Strip label="Grid connection point" value="GCP-01" />
        </div>

        {/* DER cards */}
        <div className="panel">
          <div className="ptitle">DER assets — individual &amp; aggregated</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
            {derCards.map(d => {
              const ratio = Math.min(100, Math.max(0, Math.abs(d.kw) / (d.asset.rated_kw || 1) * 100))
              return (
                <div key={d.key}
                     style={{
                       background: 'var(--color-background-primary)',
                       border: `0.5px solid ${d.kw !== 0 ? d.barColor : 'var(--color-border-tertiary)'}`,
                       borderRadius: 8, padding: 8,
                     }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-primary)' }}>{d.asset.label ?? ASSET_DEFAULTS[d.key]?.label}</div>
                    <span className={`badge ${d.badgeClass}`}>{d.badge}</span>
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 500, color: d.color, marginTop: 3 }}>
                    {d.kw >= 0 ? '' : '-'}{Math.abs(d.kw).toFixed(0)} kW
                  </div>
                  <div className="loadbar-wrap" style={{ height: 8 }}>
                    <div className="loadbar" style={{ width: `${ratio}%`, background: d.barColor, height: 8 }} />
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--color-text-secondary)' }}>{d.sub}</div>
                  <div style={{ marginTop: 3, fontSize: 9, color: 'var(--color-text-secondary)' }}>{d.mode}</div>
                </div>
              )
            })}
          </div>

          {/* VPP aggregation bar */}
          <div style={{ background: 'var(--color-background-secondary)', borderRadius: 6, padding: '8px 10px' }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 5 }}>
              VPP aggregate dispatch
            </div>
            <div style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginBottom: 4 }}>
              Aggregated in {mode === 'vpp' ? 'VPP mode' : 'individual control mode'} · total {totalGen.toFixed(0)} kW
            </div>
            <div style={{ display: 'flex', gap: 2, height: 12, borderRadius: 4, overflow: 'hidden', marginBottom: 4 }}>
              {[
                { w: Math.max(2, (pvKw / Math.max(totalGen, 1)) * 100), c: '#378ADD' },
                { w: Math.max(0, (gasKw / Math.max(totalGen, 1)) * 100), c: '#639922' },
                { w: Math.max(0, (Math.abs(bessKw) / Math.max(totalGen, 1)) * 100), c: '#EF9F27' },
                { w: Math.max(0, (Math.abs(evKw)   / Math.max(totalGen, 1)) * 100), c: '#7F77DD' },
              ].map((b, i) => (
                <div key={i} style={{ width: `${b.w}%`, background: b.c, transition: 'width 1.2s' }} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, fontSize: 9, color: 'var(--color-text-secondary)', flexWrap: 'wrap' }}>
              <LegendChip color="#378ADD" label={`PV ${pvKw.toFixed(0)} kW`} />
              <LegendChip color="#639922" label={`Gas ${gasKw.toFixed(0)} kW`} />
              <LegendChip color="#EF9F27" label={`BESS ${bessKw.toFixed(0)} kW`} />
              <LegendChip color="#7F77DD" label={`EV fleet ${evKw.toFixed(0)} kW`} />
            </div>
            <div style={{ marginTop: 6, fontSize: 10, color: 'var(--color-text-secondary)' }}>
              Net to grid:{' '}
              <span style={{ fontWeight: 500, color: reversePower > 0 ? '#A32D2D' : '#27500A' }}>
                {netExport >= 0 ? '+' : ''}{netExport.toFixed(0)} kW ({netExport > 0 ? 'importing' : 'exporting'})
              </span>
            </div>
          </div>
        </div>

        {/* Alarms + resolution plan */}
        <div className="panel">
          <div className={`ptitle ${flowSev === 'cr' ? 'danger' : 'warn'}`}>Active alarms</div>
          {flowSev === 'cr' && (
            <div className="alarm cr">
              <div className="ab">CRITICAL</div>
              <div>
                <div className="alarm-text">
                  Reverse power flow — feeder at {(-reversePower).toFixed(0)} kW. Trip relay armed at {relayKw} kW.
                  {' '}Headroom {relayMargin.toFixed(0)} kW.
                </div>
                <div className="alarm-time">Active</div>
              </div>
            </div>
          )}
          {vpu >= 1.05 && (
            <div className="alarm ma">
              <div className="ab">MAJOR</div>
              <div>
                <div className="alarm-text">
                  Feeder voltage elevated — {vv.toFixed(1)} V at GCP-01 ({vpu.toFixed(2)} pu). DER injection raising bus voltage.
                </div>
              </div>
            </div>
          )}
          {bessKw === 0 && reversePower > 0 && (
            <div className="alarm ma">
              <div className="ab">MAJOR</div>
              <div>
                <div className="alarm-text">
                  BESS underutilised — available to absorb surplus. Dispatch pending.
                </div>
              </div>
            </div>
          )}
          {flowSev === 'ok' && !islanded && (
            <div className="alarm ok">
              <div className="ab">OK</div>
              <div><div className="alarm-text">Microgrid stable, feeder within operating envelope.</div></div>
            </div>
          )}
          {islanded && (
            <div className="alarm ma">
              <div className="ab">ISLAND</div>
              <div>
                <div className="alarm-text">
                  Grid disconnected. Gas peaker forming voltage reference. Monitoring frequency &amp; voltage.
                </div>
              </div>
            </div>
          )}

          <div style={{ marginTop: 8 }}>
            <div className="ptitle ok">Resolution plan</div>
            <div className="alarm ok"><div className="ab">STEP 1</div><div><div className="alarm-text">Curtail PV via inverter droop command toward {Math.max(0, pv.rated_kw - 20).toFixed(0)} kW.</div></div></div>
            <div className="alarm ok"><div className="ab">STEP 2</div><div><div className="alarm-text">Dispatch BESS to absorb surplus in charge mode (∼{Math.min(bess.rated_kw, Math.abs(Math.min(0, netExport)) + 20).toFixed(0)} kW).</div></div></div>
            <div className="alarm ok"><div className="ab">STEP 3</div><div><div className="alarm-text">Boost EV fleet managed charging via V2G smart schedule.</div></div></div>
            <div className="alarm in"><div className="ab">STEP 4</div><div><div className="alarm-text">Monitor net flow — target +5 to +20 kW import (safe forward flow).</div></div></div>
          </div>
        </div>
      </div>

      {/* ROW 3: DER telemetry table */}
      <div className="panel" style={{ marginTop: 8 }}>
        <div className="ptitle">DER asset telemetry — individual monitoring</div>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Asset</th><th>Type</th><th style={{ textAlign: 'right' }}>Output (kW)</th>
                <th style={{ textAlign: 'right' }}>SoC / %cap</th>
                <th style={{ textAlign: 'right' }}>V (V)</th>
                <th style={{ textAlign: 'right' }}>I (A)</th>
                <th style={{ textAlign: 'right' }}>PF</th>
                <th style={{ textAlign: 'center' }}>Status</th>
                <th>Dispatch role</th>
              </tr>
            </thead>
            <tbody>
              <TelemetryRow name={pv.id ?? 'PV-F7'}   type="Solar PV"    kw={pvKw}   kwColor="#185FA5" soc="—"  v={vv.toFixed(1)} i={(pvKw*1000/400 || 0).toFixed(0)} pf="0.99" status="Exporting" statusClass="info"  role="Primary generation" />
              <TelemetryRow name={gas.id ?? 'GAS-F7'} type="Gas CHP"     kw={gasKw}  kwColor="#3B6D11" soc="—"  v={vv.toFixed(1)} i={(gasKw*1000/400 || 0).toFixed(0)} pf="0.97" status={gasKw > 0 ? 'Online' : 'Standby'} statusClass={gasKw > 0 ? 'ok' : 'neutral'} role={islanded ? 'Grid forming' : 'Freq. support'} />
              <TelemetryRow name={bess.id ?? 'BESS-F7'} type="Li-ion BESS" kw={bessKw} kwColor={bessKw < 0 ? '#854F0B' : '#3B6D11'} soc={`${ns.bess_soc_pct ?? 68}%`} v={vv.toFixed(1)} i={(Math.abs(bessKw)*1000/400 || 0).toFixed(0)} pf="—" status={bessKw < 0 ? 'Charging' : bessKw > 0 ? 'Discharging' : 'Standby'} statusClass={bessKw !== 0 ? 'warn' : 'neutral'} role="Absorb reverse flow" />
              <TelemetryRow name={evf.id ?? 'EVF-F7'}  type="EV V2G"      kw={evKw}   kwColor="#26215C" soc={`${ns.ev_fleet_soc_pct ?? 68}% avg`} v={vv.toFixed(1)} i={(Math.abs(evKw)*1000/400 || 0).toFixed(0)} pf="—" status={evKw !== 0 ? 'Managed' : 'Idle'} statusClass="purple" role={evKw < 0 ? 'Absorb surplus' : 'Load balancing'} />
            </tbody>
          </table>
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
    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
      <span style={{ width: 8, height: 8, background: color, borderRadius: 2, display: 'inline-block' }} />
      {label}
    </span>
  )
}

function TelemetryRow({ name, type, kw, kwColor, soc, v, i, pf, status, statusClass, role }) {
  return (
    <tr>
      <td style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>{name}</td>
      <td style={{ color: 'var(--color-text-secondary)' }}>{type}</td>
      <td style={{ textAlign: 'right', color: kwColor, fontWeight: 500 }}>{kw.toFixed ? kw.toFixed(0) : kw}</td>
      <td style={{ textAlign: 'right', color: 'var(--color-text-secondary)' }}>{soc}</td>
      <td style={{ textAlign: 'right' }}>{v}</td>
      <td style={{ textAlign: 'right' }}>{i}</td>
      <td style={{ textAlign: 'right' }}>{pf}</td>
      <td style={{ textAlign: 'center' }}><span className={`badge ${statusClass}`}>{status}</span></td>
      <td style={{ fontSize: 9, color: 'var(--color-text-secondary)' }}>{role}</td>
    </tr>
  )
}
