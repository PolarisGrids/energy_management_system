import { useState } from 'react'
import {
  Monitor, Server, Wifi, Battery, Tv2, Cpu, ChevronRight,
  Layers, Eye, Cable, Building2, Shield,
} from 'lucide-react'

// ─── Hardware spec data ───────────────────────────────────────────────────────
const HW_SPECS = [
  {
    id: 'workstation',
    icon: Monitor,
    title: 'Operator Workstation',
    color: '#02C9A8',
    subtitle: 'Dell OptiPlex 7090 Ultra',
    specs: [
      { label: 'Processor', value: 'Intel Core i9-11900, 8-core, 5.2 GHz' },
      { label: 'Memory', value: '64 GB DDR4-3200 ECC' },
      { label: 'Storage', value: '2 TB NVMe SSD (PCIe 4.0)' },
      { label: 'Displays', value: '4× Dell 27" 4K UHD (3840×2160)' },
      { label: 'GPU', value: 'Dual NVIDIA RTX 3060 12GB' },
      { label: 'OS', value: 'Windows 11 Pro for Workstations' },
      { label: 'Qty', value: '4 operator + 1 supervisor' },
    ],
  },
  {
    id: 'videowall',
    icon: Tv2,
    title: 'Video Wall',
    color: '#56CCF2',
    subtitle: 'Samsung IF Series LED Tile Array',
    specs: [
      { label: 'Tile Model', value: 'Samsung IF055A 55" LED' },
      { label: 'Configuration', value: '3×2 array — 6 tiles total' },
      { label: 'Combined Diagonal', value: '≈ 220" (5.6 m width)' },
      { label: 'Resolution per tile', value: '1920×1080 Full HD' },
      { label: 'Brightness', value: '500 nit, 5000:1 contrast' },
      { label: 'Bezel width', value: '0.88 mm (tile-to-tile)' },
      { label: 'Refresh rate', value: '120 Hz, 1ms response' },
    ],
  },
  {
    id: 'server',
    icon: Server,
    title: 'Server Rack',
    color: '#3C63FF',
    subtitle: 'Dell PowerEdge R750 × 2',
    specs: [
      { label: 'Processor', value: '2× Intel Xeon Gold 6338 (32-core)' },
      { label: 'Memory', value: '512 GB DDR4-3200 RDIMM ECC' },
      { label: 'Storage', value: '10 TB NVMe RAID-6 (12× 1TB)' },
      { label: 'Network', value: 'Dual 25GbE SFP28 + IPMI OOB' },
      { label: 'GPU', value: 'NVIDIA A10 24GB (compute node)' },
      { label: 'OS', value: 'Ubuntu Server 22.04 LTS' },
      { label: 'Form factor', value: '2U rack-mount, 42U cabinet' },
    ],
  },
  {
    id: 'network',
    icon: Wifi,
    title: 'Network Infrastructure',
    color: '#F59E0B',
    subtitle: 'Cisco Enterprise Switching',
    specs: [
      { label: 'Core switch', value: 'Cisco Catalyst 9300-48UXM' },
      { label: 'Backbone speed', value: '10GbE (SFP+) inter-switch' },
      { label: 'Uplinks', value: '2× 40GbE QSFP+ redundant' },
      { label: 'PoE', value: '802.3bt PoE++ (90W per port)' },
      { label: 'VLAN segments', value: 'OT / IT / AV / MGMT / DMZ' },
      { label: 'Firewall', value: 'Cisco Firepower 2140 NGFW' },
      { label: 'Monitoring', value: 'Cisco DNA Centre with telemetry' },
    ],
  },
  {
    id: 'av',
    icon: Cable,
    title: 'AV Controller',
    color: '#8B5CF6',
    subtitle: 'Crestron NVX Matrix System',
    specs: [
      { label: 'Matrix switcher', value: 'Crestron DM-NVX-SW72 (72×72)' },
      { label: 'Endpoint', value: 'Crestron DM-NVX-350C encoders' },
      { label: 'Signal', value: '4K60 HDR, 4:4:4, zero-latency' },
      { label: 'Protocol', value: 'AV over IP (1GbE per endpoint)' },
      { label: 'Audio', value: 'Dante audio networking' },
      { label: 'Control', value: 'Crestron CP4-R processor' },
      { label: 'UI', value: 'Crestron TSW-770 10" touch panel' },
    ],
  },
  {
    id: 'ups',
    icon: Battery,
    title: 'UPS / Power',
    color: '#E94B4B',
    subtitle: 'APC Smart-UPS 10000VA',
    specs: [
      { label: 'Capacity', value: '10 kVA / 10 kW (unity PF)' },
      { label: 'Runtime', value: '30 min at full load' },
      { label: 'Input voltage', value: '400V 3-phase TN-S' },
      { label: 'Transfer time', value: '<2 ms (double-conversion)' },
      { label: 'Battery', value: 'VRLA sealed lead-acid, hot-swap' },
      { label: 'Management', value: 'APC Network Management Card 3' },
      { label: 'Bypass', value: 'Automatic static bypass relay' },
    ],
  },
]

const DESIGN_HIGHLIGHTS = [
  {
    icon: Eye,
    title: 'Optimal Sightlines',
    color: '#02C9A8',
    text: 'Arc-arranged operator consoles maintain unobstructed views of the 220" video wall from every seat, with a maximum viewing angle of 35°.',
  },
  {
    icon: Layers,
    title: 'Ergonomic Console Design',
    color: '#56CCF2',
    text: 'Height-adjustable sit-stand desks at each station with 120° monitor swing arm arrays, reducing operator fatigue during extended shifts.',
  },
  {
    icon: Cable,
    title: 'Integrated Cable Management',
    color: '#8B5CF6',
    text: 'Under-floor cable trays with colour-coded AV, power, and data routes. Maintenance access via removable floor tiles without console disruption.',
  },
]

// ─── SVG Floor Plan ───────────────────────────────────────────────────────────
function FloorPlan() {
  const W = 760, H = 480

  // Operator console arc positions (4 consoles)
  const consoles = [
    { x: 160, y: 260 },
    { x: 255, y: 220 },
    { x: 355, y: 210 },
    { x: 450, y: 230 },
  ]

  return (
    <div style={{
      width: '100%', background: 'rgba(6,11,24,0.7)', borderRadius: 12,
      border: '1px solid rgba(171,199,255,0.1)', overflow: 'hidden',
    }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', display: 'block' }}>
        {/* Definitions */}
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <linearGradient id="wallGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#02C9A8" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#56CCF2" stopOpacity="0.6" />
          </linearGradient>
          <linearGradient id="floorGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#0A1535" stopOpacity="1" />
            <stop offset="100%" stopColor="#060B18" stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* Room floor */}
        <rect x={20} y={20} width={720} height={440} rx={8} fill="url(#floorGrad)" stroke="rgba(171,199,255,0.15)" strokeWidth={1.5} />

        {/* Grid lines (subtle) */}
        {[100, 200, 300, 400, 500, 600, 700].map(x => (
          <line key={`vg${x}`} x1={x} y1={20} x2={x} y2={460} stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
        ))}
        {[80, 160, 240, 320, 400].map(y => (
          <line key={`hg${y}`} x1={20} y1={y} x2={740} y2={y} stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
        ))}

        {/* Video wall — front wall */}
        <rect x={30} y={25} width={440} height={65} rx={4} fill="#02C9A822" stroke="#02C9A8" strokeWidth={1.5} filter="url(#glow)" />
        {/* 3×2 tile grid */}
        {[0, 1, 2].map(col => [0, 1].map(row => (
          <rect key={`tile-${col}-${row}`}
            x={34 + col * 145} y={29 + row * 29}
            width={140} height={27} rx={2}
            fill="#02C9A812" stroke="#02C9A855" strokeWidth={1}
          />
        )))}
        <text x={250} y={70} textAnchor="middle" fill="#02C9A8" fontSize={10} fontWeight={700} fontFamily="Satoshi,sans-serif">
          4K VIDEO WALL — 3×2 LED ARRAY
        </text>

        {/* Server room — right side */}
        <rect x={600} y={25} width={130} height={210} rx={6} fill="#56CCF218" stroke="#56CCF2" strokeWidth={1.5} />
        {/* Server rack icons */}
        {[0, 1, 2, 3].map(i => (
          <rect key={`rack${i}`} x={615} y={40 + i * 44} width={100} height={36} rx={3}
            fill="#3C63FF22" stroke="#3C63FF66" strokeWidth={1} />
        ))}
        <text x={665} y={248} textAnchor="middle" fill="#56CCF2" fontSize={10} fontWeight={700} fontFamily="Satoshi,sans-serif">
          SERVER ROOM
        </text>

        {/* Visitor / eval zone */}
        <rect x={30} y={380} width={260} height={75} rx={6} fill="rgba(171,199,255,0.04)" stroke="rgba(171,199,255,0.2)" strokeWidth={1.5} strokeDasharray="6,3" />
        <text x={160} y={422} textAnchor="middle" fill="rgba(171,199,255,0.5)" fontSize={10} fontWeight={700} fontFamily="Satoshi,sans-serif">VISITOR / EVALUATION ZONE</text>

        {/* Entrance door */}
        <rect x={340} y={450} width={80} height={10} rx={3} fill="rgba(255,255,255,0.1)" stroke="rgba(255,255,255,0.25)" strokeWidth={1} />
        <path d={`M 340 460 Q 380 430 420 460`} fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth={1} strokeDasharray="4,3" />
        <text x={380} y={475} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={9} fontFamily="Satoshi,sans-serif">ENTRANCE</text>

        {/* Supervisor station */}
        <rect x={360} y={295} width={120} height={70} rx={6} fill="#F59E0B18" stroke="#F59E0B" strokeWidth={1.5} />
        <text x={420} y={325} textAnchor="middle" fill="#F59E0B" fontSize={9} fontWeight={700} fontFamily="Satoshi,sans-serif">SUPERVISOR</text>
        <text x={420} y={340} textAnchor="middle" fill="#F59E0B99" fontSize={8} fontFamily="Satoshi,sans-serif">STATION</text>
        {/* Supervisor monitor */}
        <rect x={375} y={303} width={90} height={22} rx={2} fill="#F59E0B22" stroke="#F59E0B66" strokeWidth={1} />

        {/* 4 operator consoles */}
        {consoles.map((c, i) => (
          <g key={`console-${i}`}>
            {/* Desk */}
            <ellipse cx={c.x} cy={c.y + 10} rx={48} ry={16} fill="#0A369022" stroke="#0A3690" strokeWidth={1.5} />
            {/* Monitor array (3 screens each) */}
            {[-1, 0, 1].map(offset => (
              <rect key={`mon-${i}-${offset}`}
                x={c.x - 12 + offset * 26} y={c.y - 30}
                width={22} height={16} rx={2}
                fill="#0A369033" stroke="#ABC7FF66" strokeWidth={1}
              />
            ))}
            {/* Chair */}
            <circle cx={c.x} cy={c.y + 38} r={10} fill="#0A3690" stroke="#ABC7FF33" strokeWidth={1} />
            <text x={c.x} y={c.y + 55} textAnchor="middle" fill="#ABC7FF" fontSize={8} fontWeight={700} fontFamily="Satoshi,sans-serif">
              OP {i + 1}
            </text>
          </g>
        ))}

        {/* Zone labels */}
        <text x={480} y={140} fill="#0A3690" fontSize={10} fontWeight={700} fontFamily="Satoshi,sans-serif" fillOpacity={0.8}>OPERATOR</text>
        <text x={478} y={152} fill="#0A3690" fontSize={10} fontWeight={700} fontFamily="Satoshi,sans-serif" fillOpacity={0.8}>FLOOR</text>

        {/* Compass indicator */}
        <g transform="translate(700, 400)">
          <circle cx={0} cy={0} r={22} fill="rgba(10,54,144,0.3)" stroke="rgba(171,199,255,0.2)" strokeWidth={1} />
          <text x={0} y={-8} textAnchor="middle" fill="#56CCF2" fontSize={9} fontWeight={900} fontFamily="Satoshi,sans-serif">N</text>
          <line x1={0} y1={-5} x2={0} y2={5} stroke="#56CCF2" strokeWidth={1.5} />
          <text x={0} y={17} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={8} fontFamily="Satoshi,sans-serif">S</text>
          <text x={-16} y={4} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={8} fontFamily="Satoshi,sans-serif">W</text>
          <text x={16} y={4} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={8} fontFamily="Satoshi,sans-serif">E</text>
        </g>

        {/* Scale bar */}
        <line x1={580} y1={450} x2={650} y2={450} stroke="rgba(255,255,255,0.3)" strokeWidth={1.5} />
        <line x1={580} y1={445} x2={580} y2={455} stroke="rgba(255,255,255,0.3)" strokeWidth={1.5} />
        <line x1={650} y1={445} x2={650} y2={455} stroke="rgba(255,255,255,0.3)" strokeWidth={1.5} />
        <text x={615} y={467} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={8} fontFamily="Satoshi,sans-serif">5 m</text>

        {/* Room dimension labels */}
        <text x={380} y={16} textAnchor="middle" fill="rgba(255,255,255,0.2)" fontSize={8} fontFamily="Satoshi,sans-serif">15.2 m</text>
        <text x={12} y={250} textAnchor="middle" fill="rgba(255,255,255,0.2)" fontSize={8} fontFamily="Satoshi,sans-serif" transform="rotate(-90,12,250)">9.8 m</text>
      </svg>

      {/* Legend */}
      <div style={{
        padding: '10px 16px', borderTop: '1px solid rgba(255,255,255,0.05)',
        display: 'flex', gap: 20, flexWrap: 'wrap',
      }}>
        {[
          { color: '#0A3690', label: 'Operator Stations' },
          { color: '#02C9A8', label: 'Video Wall' },
          { color: '#56CCF2', label: 'Server Room' },
          { color: '#F59E0B', label: 'Supervisor Station' },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: color, opacity: 0.8 }} />
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Spec Card ────────────────────────────────────────────────────────────────
function SpecCard({ spec }) {
  const { icon: Icon, title, color, subtitle, specs } = spec
  return (
    <div className="glass-card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: `${color}20`, border: `1px solid ${color}44`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icon size={20} style={{ color }} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>{title}</div>
          <div style={{ fontSize: 11, color: `${color}cc`, marginTop: 1 }}>{subtitle}</div>
        </div>
      </div>
      <div style={{ borderTop: `1px solid rgba(255,255,255,0.06)`, paddingTop: 12 }}>
        {specs.map(({ label, value }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.04)',
            gap: 8,
          }}>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', fontWeight: 600, flexShrink: 0 }}>{label}</span>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.85)', textAlign: 'right' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function SMOCShowcase() {
  const [tab, setTab] = useState('Facility Layout')

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>SMOC Facility Showcase</h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
          REQ-1, REQ-2 — Control room layout and hardware specifications
        </p>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 2, marginBottom: 24,
        background: 'rgba(10,54,144,0.2)', borderRadius: 10, padding: 4,
        border: '1px solid rgba(171,199,255,0.1)', width: 'fit-content',
      }}>
        {['Facility Layout', 'Hardware Specifications'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '8px 22px', borderRadius: 8, border: 'none', fontWeight: 700, fontSize: 13, cursor: 'pointer',
            background: tab === t ? 'linear-gradient(45deg, #11ABBE, #3C63FF)' : 'transparent',
            color: tab === t ? '#fff' : 'rgba(255,255,255,0.5)',
            transition: 'all 0.2s',
          }}>{t}</button>
        ))}
      </div>

      {tab === 'Facility Layout' && (
        <div>
          {/* Hero banner */}
          <div style={{
            borderRadius: 14, padding: '32px 40px', marginBottom: 24,
            background: 'linear-gradient(135deg, #0A3690 0%, #0A2870 40%, #02C9A822 100%)',
            border: '1px solid rgba(2,201,168,0.2)', position: 'relative', overflow: 'hidden',
          }}>
            {/* Decorative circles */}
            <div style={{
              position: 'absolute', right: -60, top: -60, width: 250, height: 250,
              borderRadius: '50%', background: 'rgba(2,201,168,0.06)', pointerEvents: 'none',
            }} />
            <div style={{
              position: 'absolute', right: 60, top: 20, width: 150, height: 150,
              borderRadius: '50%', background: 'rgba(86,204,242,0.05)', pointerEvents: 'none',
            }} />
            <div style={{ position: 'relative', zIndex: 1 }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 20,
                background: 'rgba(2,201,168,0.15)', border: '1px solid rgba(2,201,168,0.3)', marginBottom: 14,
              }}>
                <Shield size={12} style={{ color: '#02C9A8' }} />
                <span style={{ fontSize: 11, fontWeight: 700, color: '#02C9A8' }}>Eskom AMI Programme — Tender E2136DXLP</span>
              </div>
              <h2 style={{ margin: '0 0 8px', fontSize: 28, fontWeight: 900, color: '#fff', lineHeight: 1.2 }}>
                SMOC Control Room
              </h2>
              <p style={{ margin: '0 0 16px', fontSize: 16, color: 'rgba(255,255,255,0.6)' }}>
                Megawatt Park · Sunninghill · Johannesburg, South Africa
              </p>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                {[
                  ['4', 'Operator Workstations'],
                  ['1', 'Supervisor Station'],
                  ['6-tile', '3×2 Video Wall'],
                  ['42U', 'Server Cabinet'],
                ].map(([val, lbl]) => (
                  <div key={lbl}>
                    <div style={{ fontSize: 24, fontWeight: 900, color: '#02C9A8' }}>{val}</div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{lbl}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SVG Floor plan */}
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: '#fff', margin: '0 0 12px' }}>Control Room Floor Plan</h3>
            <FloorPlan />
          </div>

          {/* Design highlights */}
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#fff', margin: '0 0 12px' }}>Design Highlights</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {DESIGN_HIGHLIGHTS.map(d => (
              <div key={d.title} className="glass-card" style={{ padding: 20 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10, marginBottom: 12,
                  background: `${d.color}20`, border: `1px solid ${d.color}44`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <d.icon size={18} style={{ color: d.color }} />
                </div>
                <div style={{ fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 6 }}>{d.title}</div>
                <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)', lineHeight: 1.6 }}>{d.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'Hardware Specifications' && (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <p style={{ margin: 0, color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>
              All hardware supplied and configured by Polaris Grids. Own infrastructure — no Eskom network dependency.
            </p>
            <span style={{ fontSize: 11, color: '#02C9A8', fontWeight: 700, background: 'rgba(2,201,168,0.1)', padding: '4px 10px', borderRadius: 20, border: '1px solid rgba(2,201,168,0.2)' }}>
              {HW_SPECS.length} components
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {HW_SPECS.map(spec => <SpecCard key={spec.id} spec={spec} />)}
          </div>
        </div>
      )}
    </div>
  )
}
