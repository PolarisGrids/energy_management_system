import { Sun, Flame, Battery, Car, Zap, AlertTriangle, Activity } from 'lucide-react'

/**
 * MicrogridViz — Riverside Industrial Precinct VPP/microgrid visualization for REQ-23.
 * Renders asset mix cards, reverse-flow needle gauge, PCC voltage meter, a big
 * net-export number, and an island-mode banner.
 */

const ASSET_ICON = {
  pv:         Sun,
  solar:      Sun,
  gas:        Flame,
  gas_peaker: Flame,
  peaker:     Flame,
  bess:       Battery,
  battery:    Battery,
  ev:         Car,
  ev_fleet:   Car,
}

const ASSET_LABEL = {
  pv:         'Solar PV Array',
  solar:      'Solar PV Array',
  gas:        'Gas Peaker',
  gas_peaker: 'Gas Peaker',
  peaker:     'Gas Peaker',
  bess:       'Battery Storage',
  battery:    'Battery Storage',
  ev:         'EV Fleet',
  ev_fleet:   'EV Fleet',
}

const ASSET_COLOR = {
  pv: '#F59E0B', solar: '#F59E0B',
  gas: '#E94B4B', gas_peaker: '#E94B4B', peaker: '#E94B4B',
  bess: '#02C9A8', battery: '#02C9A8',
  ev: '#56CCF2', ev_fleet: '#56CCF2',
}

function valueForAsset(type, ns) {
  if (!ns) return 0
  switch (type) {
    case 'pv': case 'solar':         return ns.pv_kw ?? 0
    case 'gas': case 'gas_peaker': case 'peaker': return ns.gas_kw ?? 0
    case 'bess': case 'battery':     return ns.bess_kw ?? 0
    case 'ev': case 'ev_fleet':      return ns.ev_fleet_kw ?? 0
    default: return 0
  }
}

function voltageBandColor(puVal) {
  if (puVal == null) return '#6B7280'
  if (puVal >= 1.08) return '#E94B4B'
  if (puVal >= 1.05) return '#F59E0B'
  if (puVal >= 1.02) return '#ABC7FF'
  return '#02C9A8'
}

export default function MicrogridViz({ scenario, currentStep, networkState }) {
  const params = scenario?.parameters || {}
  const assets = params.assets || [
    { type: 'pv',         rated_kw: 400 },
    { type: 'gas_peaker', rated_kw: 300 },
    { type: 'bess',       rated_kw: 250 },
    { type: 'ev_fleet',   rated_kw: 150 },
  ]

  const ns = networkState || {}
  const islanded = !!ns.islanded
  const aggMode = ns.aggregation_mode || 'individual'
  const netExportKw = ns.net_export_kw ?? 0
  const reversePowerKw = ns.reverse_power_kw ?? 0
  const relayKw = ns.reverse_power_relay_kw ?? params.reverse_power_relay_kw ?? -150
  const vPuInjection = ns.v_pu_injection ?? null
  const bessSocPct = ns.bess_soc_pct ?? null
  const evFleetSocPct = ns.ev_fleet_soc_pct ?? null
  const evFleetCount = ns.ev_fleet_count ?? params.ev_fleet_count ?? 8
  const pvIrradiance = ns.pv_irradiance_w_m2 ?? null
  const gasRampStatus = ns.gas_ramp_status || 'idle'
  const relayMarginKw = ns.relay_margin_kw ?? (reversePowerKw - relayKw)

  // Gauge scale: -300..+300 kW
  const gMin = -300
  const gMax = 300
  const clamp = (v) => Math.max(gMin, Math.min(gMax, v))
  const toPct = (v) => ((clamp(v) - gMin) / (gMax - gMin)) * 100

  const relayPct  = toPct(relayKw)          // e.g. -150 -> 25%
  const amberLo   = toPct(relayKw + 20)     // amber zone ends 20 kW above relay
  const needlePct = toPct(reversePowerKw)

  // Needle zone color
  let needleColor = '#02C9A8'
  if (reversePowerKw <= relayKw) needleColor = '#E94B4B'
  else if (reversePowerKw <= relayKw + 20) needleColor = '#F59E0B'

  // V_pu meter geometry (vertical: bottom=1.00, top=1.10)
  const vPuMin = 1.00
  const vPuMax = 1.10
  const vPuPct = vPuInjection != null
    ? Math.max(0, Math.min(1, (vPuInjection - vPuMin) / (vPuMax - vPuMin))) * 100
    : 0
  const vColor = voltageBandColor(vPuInjection)

  return (
    <div className="glass-card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'rgba(171,199,255,0.15)' }}>
            <Zap size={18} style={{ color: '#ABC7FF' }} />
          </div>
          <div>
            <div className="text-white font-black" style={{ fontSize: 15 }}>
              Riverside Industrial Precinct
            </div>
            <div className="text-white/40" style={{ fontSize: 11 }}>
              {params.site_name || 'VPP microgrid'} · {assets.length} DERs · PCC 11 kV
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
            style={{
              background: islanded ? 'rgba(233,75,75,0.2)' : 'rgba(2,201,168,0.15)',
              border: `1px solid ${islanded ? '#E94B4B' : '#02C9A8'}40`,
            }}>
            <span className={`w-1.5 h-1.5 rounded-full ${islanded ? 'animate-pulse' : ''}`}
              style={{ background: islanded ? '#E94B4B' : '#02C9A8' }} />
            <span className="font-black tracking-wider" style={{
              fontSize: 11,
              color: islanded ? '#E94B4B' : '#02C9A8',
            }}>
              {islanded ? 'ISLANDED' : 'GRID-TIED'}
            </span>
          </div>
        </div>
      </div>

      {/* Island banner */}
      {islanded && (
        <div className="mb-4 p-3 rounded-lg flex items-center gap-3"
          style={{
            background: 'rgba(233,75,75,0.12)',
            border: '1px solid rgba(233,75,75,0.35)',
          }}>
          <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
          <div className="font-bold" style={{ fontSize: 12, color: '#E94B4B' }}>
            ISLAND MODE — gas peaker forming voltage reference, grid disconnected.
          </div>
        </div>
      )}

      {/* Aggregation mode tabs */}
      <div className="mb-4">
        <div className="text-white/40 font-bold mb-2" style={{ fontSize: 11 }}>
          AGGREGATION MODE
        </div>
        <div className="inline-flex rounded-lg overflow-hidden"
          style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
          {[
            { key: 'individual', label: 'Individual control' },
            { key: 'vpp',        label: 'VPP aggregation' },
          ].map(t => {
            const active = aggMode === t.key || (t.key === 'vpp' && aggMode === 'aggregated')
            return (
              <div key={t.key}
                className="px-4 py-1.5 font-bold transition-all"
                style={{
                  fontSize: 11,
                  background: active ? 'rgba(2,201,168,0.18)' : 'transparent',
                  color: active ? '#02C9A8' : 'rgba(255,255,255,0.45)',
                  cursor: 'default',
                }}>
                {t.label}
              </div>
            )
          })}
        </div>
      </div>

      {/* 4 DER asset cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {assets.slice(0, 4).map((asset, i) => {
          const type = asset.type || 'pv'
          const Icon = ASSET_ICON[type] || Battery
          const label = asset.label || ASSET_LABEL[type] || type
          const color = ASSET_COLOR[type] || '#ABC7FF'
          const rated = asset.rated_kw ?? 100
          const current = valueForAsset(type, ns)
          const ratio = rated > 0 ? Math.min(Math.abs(current) / rated, 1) : 0
          const sign = current >= 0 ? '+' : ''
          const signColor = current >= 0 ? color : '#ABC7FF'

          // Type-specific extra line
          let extra = null
          if (type === 'pv' || type === 'solar') {
            extra = pvIrradiance != null
              ? `${pvIrradiance.toFixed(0)} W/m²`
              : 'Irradiance —'
          } else if (type === 'gas' || type === 'gas_peaker' || type === 'peaker') {
            extra = `Ramp: ${String(gasRampStatus).toUpperCase()}`
          } else if (type === 'bess' || type === 'battery') {
            extra = bessSocPct != null ? `SoC ${bessSocPct.toFixed(0)}%` : 'SoC —'
          } else if (type === 'ev' || type === 'ev_fleet') {
            extra = evFleetSocPct != null
              ? `${evFleetCount} EVs · SoC ${evFleetSocPct.toFixed(0)}%`
              : `${evFleetCount} EVs`
          }

          return (
            <div key={i} className="p-3 rounded-lg"
              style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${color}20` }}>
                  <Icon size={13} style={{ color }} />
                </div>
                <span className="text-white font-bold" style={{ fontSize: 11 }}>{label}</span>
              </div>
              <div className="font-black" style={{ fontSize: 20, color: signColor }}>
                {sign}{current.toFixed(0)}
                <span className="text-white/40 font-normal ml-1" style={{ fontSize: 11 }}>kW</span>
              </div>
              <div className="mt-2">
                <div className="flex justify-between mb-1">
                  <span className="text-white/40" style={{ fontSize: 9 }}>RATED</span>
                  <span className="text-white/60" style={{ fontSize: 9 }}>{rated.toFixed(0)} kW</span>
                </div>
                <div className="w-full h-1.5 rounded-full"
                  style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <div className="h-1.5 rounded-full transition-all duration-700" style={{
                    width: `${ratio * 100}%`,
                    background: color,
                  }} />
                </div>
              </div>
              {extra && (
                <div className="text-white/40 mt-2" style={{ fontSize: 10 }}>
                  {extra}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Reverse-flow gauge + PCC voltage meter + Net export */}
      <div className="grid grid-cols-12 gap-3">
        {/* Reverse-flow gauge */}
        <div className="col-span-7 p-3 rounded-lg"
          style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-white/40 font-bold" style={{ fontSize: 11 }}>
              REVERSE-FLOW GAUGE
            </span>
            <span className="font-bold" style={{ fontSize: 11, color: needleColor }}>
              {reversePowerKw >= 0 ? '+' : ''}{reversePowerKw.toFixed(0)} kW
            </span>
          </div>
          <div className="relative w-full h-6 rounded-full overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.04)' }}>
            {/* Red zone: left end up to relayPct */}
            <div className="absolute top-0 h-full" style={{
              left: 0,
              width: `${relayPct}%`,
              background: 'rgba(233,75,75,0.22)',
            }} />
            {/* Amber zone: relayPct to amberLo */}
            <div className="absolute top-0 h-full" style={{
              left: `${relayPct}%`,
              width: `${Math.max(0, amberLo - relayPct)}%`,
              background: 'rgba(245,158,11,0.18)',
            }} />
            {/* Zero line */}
            <div className="absolute top-0 h-full w-px"
              style={{ left: `${toPct(0)}%`, background: 'rgba(255,255,255,0.25)' }} />
            {/* Relay threshold line */}
            <div className="absolute top-0 h-full w-0.5"
              style={{ left: `${relayPct}%`, background: '#E94B4B', opacity: 0.8 }} />
            {/* Needle */}
            <div className="absolute top-0 h-full" style={{
              left: `${needlePct}%`,
              width: 2,
              background: needleColor,
              boxShadow: `0 0 6px ${needleColor}`,
              transition: 'left 700ms',
            }} />
          </div>
          <div className="flex justify-between mt-1" style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>
            <span>−300 kW</span>
            <span style={{ color: '#E94B4B' }}>Relay {relayKw} kW</span>
            <span>0</span>
            <span>+300 kW</span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <Activity size={11} style={{ color: needleColor }} />
            <span className="text-white/60" style={{ fontSize: 11 }}>
              Relay margin:{' '}
              <span className="font-bold" style={{ color: needleColor }}>
                {relayMarginKw >= 0 ? '+' : ''}{Number(relayMarginKw).toFixed(0)} kW
              </span>
            </span>
          </div>
        </div>

        {/* Injection voltage meter */}
        <div className="col-span-2 p-3 rounded-lg flex flex-col items-center"
          style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
          <span className="text-white/40 font-bold mb-2" style={{ fontSize: 10 }}>V_PU</span>
          <div className="relative w-6 h-28 rounded-full"
            style={{ background: 'rgba(255,255,255,0.04)' }}>
            {/* Colored band segments top-down: red @ top, amber mid, green base */}
            <div className="absolute left-0 right-0 top-0 rounded-t-full" style={{
              height: '30%',
              background: 'rgba(233,75,75,0.2)',
            }} />
            <div className="absolute left-0 right-0" style={{
              top: '30%',
              height: '20%',
              background: 'rgba(245,158,11,0.18)',
            }} />
            {/* Marker */}
            <div className="absolute left-0 right-0" style={{
              bottom: `${vPuPct}%`,
              height: 3,
              background: vColor,
              boxShadow: `0 0 6px ${vColor}`,
              transition: 'bottom 700ms',
            }} />
          </div>
          <div className="font-black mt-2" style={{ fontSize: 14, color: vColor }}>
            {vPuInjection != null ? vPuInjection.toFixed(3) : '—'}
          </div>
          <div className="text-white/40" style={{ fontSize: 9 }}>pu (PCC)</div>
        </div>

        {/* Big net-export panel */}
        <div className="col-span-3 p-3 rounded-lg flex flex-col justify-center items-center"
          style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.05)',
          }}>
          <span className="text-white/40 font-bold mb-1" style={{ fontSize: 10 }}>NET EXPORT</span>
          <div className="font-black" style={{
            fontSize: 36,
            lineHeight: 1,
            color: netExportKw > 0 ? '#02C9A8' : netExportKw < 0 ? '#ABC7FF' : 'rgba(255,255,255,0.6)',
          }}>
            {netExportKw >= 0 ? '+' : ''}{netExportKw.toFixed(0)}
          </div>
          <div className="text-white/40 mt-1" style={{ fontSize: 10 }}>
            {netExportKw >= 0 ? 'kW exported to grid' : 'kW imported'}
          </div>
        </div>
      </div>
    </div>
  )
}
