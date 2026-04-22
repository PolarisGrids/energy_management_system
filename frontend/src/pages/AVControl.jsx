import { useState, useEffect, useCallback } from 'react'
import {
  Monitor, Thermometer, Mic, MicOff, Video, VideoOff,
  Phone, PhoneOff, Share2, Calendar, Clock, Sliders, Lightbulb,
  Flame, Waves, AlertTriangle, CheckCircle, RefreshCw,
} from 'lucide-react'
import { sensorsAPI } from '@/services/api'

// ─── Constants ────────────────────────────────────────────────────────────────
const SOURCES = [
  'LV Network Map', 'GIS Map', 'Alarm Console', 'Energy Dashboard',
  'DER Dashboard', 'Simulation', 'CCTV Feed 1', 'CCTV Feed 2',
]

const SHARE_SOURCES = ['Desktop', 'LV Dashboard', 'GIS Map', 'Simulation']

const MEETINGS = [
  { id: 1, title: 'AMI Programme Sync', time: '09:00 – 09:30', organizer: 'T. Dlamini' },
  { id: 2, title: 'Eskom Rehearsal', time: '11:00 – 12:00', organizer: 'A. van der Merwe' },
  { id: 3, title: 'DER Integration Review', time: '14:30 – 15:00', organizer: 'P. Nkosi' },
]

const PARTICIPANTS = ['Thandi Dlamini', 'Arno van der Merwe', 'Precious Nkosi']

const BLIND_ZONES = ['North Wall', 'South Wall', 'East Window', 'West Window']

const PRESET_LAYOUTS = {
  '2-Split': [0, 0, 1, 1, 2, 2],
  '3-Split': [0, 1, 2, 0, 1, 2],
  '4-Split': [0, 1, 2, 3, 3, 3],
  'Focus Mode': [0, 1, 2, 3, 4, 5],
}

// source colors for visual identity
const SOURCE_COLORS = {
  'LV Network Map': '#02C9A8',
  'GIS Map': '#56CCF2',
  'Alarm Console': '#E94B4B',
  'Energy Dashboard': '#3C63FF',
  'DER Dashboard': '#F59E0B',
  'Simulation': '#8B5CF6',
  'CCTV Feed 1': '#F97316',
  'CCTV Feed 2': '#EC4899',
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function SectionHeader(props) {
  const HeaderIcon = props.icon
  const { title, color = '#02C9A8' } = props
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: `${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <HeaderIcon size={16} style={{ color }} />
      </div>
      <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>{title}</span>
    </div>
  )
}

function SensorMonitoringPanel({ sensorType, title, Icon, color }) {
  // Live roll-up of every transformer's {sensorType} sensor. Shows
  // normal/warning/critical counts + the first few critical devices.
  const [sensors, setSensors] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    setLoading(true); setErr(null)
    sensorsAPI.list({ sensor_type: sensorType })
      .then(({ data }) => setSensors(data || []))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed to load sensors'))
      .finally(() => setLoading(false))
  }, [sensorType])

  useEffect(() => {
    load()
    const h = setInterval(load, 30_000)
    return () => clearInterval(h)
  }, [load])

  const total = sensors.length
  const warn = sensors.filter(s => (s.status || '').toLowerCase() === 'warning').length
  const crit = sensors.filter(s => (s.status || '').toLowerCase() === 'critical').length
  const normal = total - warn - crit
  const statusColor = crit > 0 ? '#E94B4B' : warn > 0 ? '#F59E0B' : '#02C9A8'

  return (
    <div className="glass-card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: `${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={16} style={{ color }} />
          </div>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>{title}</span>
        </div>
        <button onClick={load} title="Refresh" style={{
          background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: 4,
        }}>
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {err ? (
        <div style={{ fontSize: 12, color: '#E94B4B' }}>{err}</div>
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 12, marginBottom: 14, padding: '14px 0',
            background: `${statusColor}14`, borderRadius: 10, border: `1px solid ${statusColor}33`,
          }}>
            {crit > 0 ? <AlertTriangle size={20} style={{ color: statusColor }} />
              : <CheckCircle size={20} style={{ color: statusColor }} />}
            <span style={{ fontSize: 20, fontWeight: 900, color: '#fff' }}>
              {crit > 0 ? `${crit} CRITICAL` : warn > 0 ? `${warn} WARNING` : 'ALL CLEAR'}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 14 }}>
            <div style={{ background: 'rgba(2,201,168,0.08)', border: '1px solid rgba(2,201,168,0.25)', borderRadius: 8, padding: '10px 6px', textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontWeight: 700, textTransform: 'uppercase' }}>Normal</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: '#02C9A8', marginTop: 2 }}>{normal}</div>
            </div>
            <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 8, padding: '10px 6px', textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontWeight: 700, textTransform: 'uppercase' }}>Warning</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: '#F59E0B', marginTop: 2 }}>{warn}</div>
            </div>
            <div style={{ background: 'rgba(233,75,75,0.08)', border: '1px solid rgba(233,75,75,0.25)', borderRadius: 8, padding: '10px 6px', textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontWeight: 700, textTransform: 'uppercase' }}>Critical</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: '#E94B4B', marginTop: 2 }}>{crit}</div>
            </div>
          </div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>
            {total} sensor{total !== 1 ? 's' : ''} across the fleet · last refresh just now
          </div>
          {crit > 0 && (
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ fontSize: 10, color: '#E94B4B', fontWeight: 700, textTransform: 'uppercase', marginBottom: 6 }}>
                Active alarms
              </div>
              {sensors.filter(s => (s.status || '').toLowerCase() === 'critical').slice(0, 3).map(s => (
                <div key={s.id} style={{ fontSize: 11, color: 'rgba(255,255,255,0.75)' }}>
                  · {s.name || `Sensor ${s.id}`}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function BlindZone({ label, value, onChange }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{label}</span>
        <span style={{ fontSize: 12, color: '#ABC7FF' }}>{value}%</span>
      </div>
      {/* Bar */}
      <div style={{
        height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.08)',
        position: 'relative', overflow: 'hidden', marginBottom: 6,
      }}>
        <div style={{
          height: '100%', width: `${value}%`,
          background: 'linear-gradient(90deg, #0A3690, #56CCF2)',
          borderRadius: 4, transition: 'width 0.3s ease',
        }} />
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {[['Open', 100], ['50%', 50], ['Close', 0]].map(([lbl, v]) => (
          <button key={lbl} onClick={() => onChange(v)} style={{
            flex: 1, padding: '4px 0', borderRadius: 5,
            border: `1px solid ${value === v ? '#56CCF2' : 'rgba(255,255,255,0.12)'}`,
            background: value === v ? 'rgba(86,204,242,0.15)' : 'rgba(255,255,255,0.04)',
            color: value === v ? '#56CCF2' : 'rgba(255,255,255,0.5)',
            fontSize: 11, fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s',
          }}>{lbl}</button>
        ))}
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function AVControl() {
  // Video wall
  const [cells, setCells] = useState(Array(6).fill(''))
  const [selectedCell, setSelectedCell] = useState(null)
  const [activeSource, setActiveSource] = useState(SOURCES[0])

  // HVAC
  const [tempSetpoint, setTempSetpoint] = useState(22)
  const [hvacMode, setHvacMode] = useState('Cool')
  const [fanSpeed, setFanSpeed] = useState('Med')
  const [currentTemp, setCurrentTemp] = useState(22.4)
  const [tempTrend, setTempTrend] = useState(1) // 1=up, -1=down

  // Blinds
  const [blinds, setBlinds] = useState({ 'North Wall': 100, 'South Wall': 50, 'East Window': 0, 'West Window': 100 })

  // Lighting
  const [dimmer, setDimmer] = useState(75)

  // Teams
  const [camOn, setCamOn] = useState(true)
  const [micOn, setMicOn] = useState(true)
  const [speakerVol, setSpeakerVol] = useState(70)
  const [inCall, setInCall] = useState(false)
  const [callSeconds, setCallSeconds] = useState(0)
  const [joinDialog, setJoinDialog] = useState(false)
  const [meetingId, setMeetingId] = useState('')
  const [shareSource, setShareSource] = useState(SHARE_SOURCES[0])
  const [sharing, setSharing] = useState(false)

  // Temp animation
  useEffect(() => {
    const id = setInterval(() => {
      setCurrentTemp(t => {
        const delta = (Math.random() - 0.5) * 0.2
        const next = parseFloat((t + delta).toFixed(1))
        setTempTrend(delta >= 0 ? 1 : -1)
        return Math.max(20, Math.min(26, next))
      })
    }, 3000)
    return () => clearInterval(id)
  }, [])

  // Call timer
  useEffect(() => {
    if (!inCall) return
    const id = setInterval(() => setCallSeconds(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [inCall])

  const formatDuration = (s) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0')
    const sec = (s % 60).toString().padStart(2, '0')
    return `${m}:${sec}`
  }

  const assignSource = () => {
    if (selectedCell === null) return
    setCells(prev => {
      const next = [...prev]
      next[selectedCell] = activeSource
      return next
    })
  }

  const applyPreset = (name) => {
    if (name === 'Focus Mode') {
      // cell 0 = big focus with first source, rest show secondary
      setCells(['Energy Dashboard', 'GIS Map', 'Alarm Console', 'LV Network Map', 'DER Dashboard', 'CCTV Feed 1'])
    } else if (name === '2-Split') {
      setCells(['LV Network Map', 'LV Network Map', 'GIS Map', 'GIS Map', '', ''])
    } else if (name === '3-Split') {
      setCells(['LV Network Map', 'GIS Map', 'Alarm Console', 'LV Network Map', 'GIS Map', 'Alarm Console'])
    } else if (name === '4-Split') {
      setCells(['LV Network Map', 'GIS Map', 'Alarm Console', 'Energy Dashboard', 'Energy Dashboard', 'Energy Dashboard'])
    }
    setSelectedCell(null)
  }

  const col = { display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }

  return (
    <div className="animate-slide-up" style={{ padding: 24, minHeight: '100vh', background: '#0A0F1E' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 900, color: '#fff', margin: 0 }}>Control Room</h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13, margin: '4px 0 0' }}>
          Environmental sensor monitoring · HVAC · Teams integration
        </p>
      </div>

      {/* 3-column layout */}
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>

        {/* ── LEFT: Smoke + Water immersion monitoring (replaced Video Wall) ── */}
        <div style={col}>
          <SensorMonitoringPanel sensorType="smoke" title="Smoke Detector" Icon={Flame} color="#E94B4B" />
          <SensorMonitoringPanel sensorType="water_immersion" title="Water Immersion" Icon={Waves} color="#56CCF2" />
        </div>

        {/* Video Wall retained as a hidden placeholder for legacy code below */}
        <div style={{ display: 'none' }}>
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Monitor} title="Video Wall Control" />

            {/* 3×2 Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 14 }}>
              {cells.map((src, i) => {
                const isSelected = selectedCell === i
                return (
                  <div
                    key={i}
                    onClick={() => setSelectedCell(isSelected ? null : i)}
                    style={{
                      aspectRatio: '16/9',
                      borderRadius: 8,
                      background: src ? `${SOURCE_COLORS[src]}18` : 'rgba(10,15,30,0.8)',
                      border: `2px solid ${isSelected ? '#02C9A8' : src ? `${SOURCE_COLORS[src]}66` : 'rgba(255,255,255,0.08)'}`,
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', transition: 'all 0.2s', position: 'relative',
                      boxShadow: isSelected ? '0 0 12px rgba(2,201,168,0.4)' : 'none',
                    }}
                  >
                    <Monitor size={16} style={{ color: src ? SOURCE_COLORS[src] : 'rgba(255,255,255,0.2)', marginBottom: 4 }} />
                    <span style={{ fontSize: 10, fontWeight: 700, color: src ? SOURCE_COLORS[src] : 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '0 4px' }}>
                      {src || `Screen ${i + 1}`}
                    </span>
                    {isSelected && (
                      <div style={{
                        position: 'absolute', top: 3, right: 3,
                        background: '#02C9A8', borderRadius: 3,
                        fontSize: 8, fontWeight: 900, padding: '1px 4px', color: '#0A0F1E',
                      }}>SEL</div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Source selector + assign */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <select
                value={activeSource}
                onChange={e => setActiveSource(e.target.value)}
                style={{
                  flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.2)',
                  borderRadius: 8, color: '#ABC7FF', padding: '8px 12px', fontSize: 13,
                  outline: 'none', cursor: 'pointer',
                }}
              >
                {SOURCES.map(s => <option key={s} value={s} style={{ background: '#0A1535' }}>{s}</option>)}
              </select>
              <button
                className="btn-primary"
                onClick={assignSource}
                disabled={selectedCell === null}
                style={{ padding: '8px 14px', fontSize: 12, whiteSpace: 'nowrap' }}
              >
                Assign to Selected
              </button>
            </div>

            {selectedCell === null && (
              <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', margin: '0 0 10px', textAlign: 'center' }}>
                Click a screen cell to select it
              </p>
            )}

            {/* Preset layouts */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Preset Layouts</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {Object.keys(PRESET_LAYOUTS).map(name => (
                  <button
                    key={name}
                    onClick={() => applyPreset(name)}
                    className="btn-secondary"
                    style={{ padding: '6px 12px', fontSize: 12 }}
                  >
                    {name}
                  </button>
                ))}
                <button
                  onClick={() => { setCells(Array(6).fill('')); setSelectedCell(null) }}
                  style={{
                    padding: '6px 12px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
                    background: 'rgba(233,75,75,0.15)', border: '1px solid rgba(233,75,75,0.3)',
                    color: '#E94B4B', fontWeight: 700,
                  }}
                >
                  Clear All
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ── MIDDLE: Environmental ── */}
        <div style={col}>
          {/* HVAC */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Thermometer} title="HVAC Control" color="#56CCF2" />

            {/* Current temp reading */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, marginBottom: 16, padding: '12px 0',
              background: 'rgba(86,204,242,0.06)', borderRadius: 10, border: '1px solid rgba(86,204,242,0.12)',
            }}>
              <Thermometer size={20} style={{ color: '#56CCF2' }} />
              <span style={{ fontSize: 32, fontWeight: 900, color: '#fff' }}>{currentTemp}°C</span>
              <span style={{ fontSize: 18, color: tempTrend > 0 ? '#E94B4B' : '#02C9A8', marginLeft: 4 }}>
                {tempTrend > 0 ? '▲' : '▼'}
              </span>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Current</span>
            </div>

            {/* Setpoint slider */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>Setpoint</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#56CCF2' }}>{tempSetpoint}°C</span>
              </div>
              <input
                type="range" min={18} max={26} value={tempSetpoint}
                onChange={e => setTempSetpoint(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#56CCF2' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>18°C</span>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>26°C</span>
              </div>
            </div>

            {/* Mode buttons */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 6, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Mode</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {['Cool', 'Heat', 'Auto', 'Off'].map(m => (
                  <button key={m} onClick={() => setHvacMode(m)} style={{
                    flex: 1, padding: '7px 4px', borderRadius: 6, fontSize: 12, fontWeight: 700,
                    cursor: 'pointer', transition: 'all 0.2s',
                    background: hvacMode === m ? 'rgba(86,204,242,0.2)' : 'rgba(255,255,255,0.05)',
                    border: `1px solid ${hvacMode === m ? '#56CCF2' : 'rgba(255,255,255,0.08)'}`,
                    color: hvacMode === m ? '#56CCF2' : 'rgba(255,255,255,0.4)',
                  }}>{m}</button>
                ))}
              </div>
            </div>

            {/* Fan speed */}
            <div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 6, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Fan Speed</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {['Low', 'Med', 'High'].map(f => (
                  <button key={f} onClick={() => setFanSpeed(f)} style={{
                    flex: 1, padding: '7px 4px', borderRadius: 6, fontSize: 12, fontWeight: 700,
                    cursor: 'pointer', transition: 'all 0.2s',
                    background: fanSpeed === f ? 'rgba(2,201,168,0.2)' : 'rgba(255,255,255,0.05)',
                    border: `1px solid ${fanSpeed === f ? '#02C9A8' : 'rgba(255,255,255,0.08)'}`,
                    color: fanSpeed === f ? '#02C9A8' : 'rgba(255,255,255,0.4)',
                  }}>{f}</button>
                ))}
              </div>
            </div>
          </div>

          {/* Blinds */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Sliders} title="Blind Zones" color="#F59E0B" />
            {BLIND_ZONES.map(zone => (
              <BlindZone
                key={zone}
                label={zone}
                value={blinds[zone]}
                onChange={v => setBlinds(prev => ({ ...prev, [zone]: v }))}
              />
            ))}
          </div>

          {/* Lighting */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Lightbulb} title="Lighting" color="#F59E0B" />
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>Brightness</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#F59E0B' }}>{dimmer}%</span>
              </div>
              <input
                type="range" min={0} max={100} value={dimmer}
                onChange={e => setDimmer(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#F59E0B' }}
              />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {[['Full Bright', 100], ['Presentation', 50], ['Night Mode', 20]].map(([lbl, v]) => (
                <button key={lbl} onClick={() => setDimmer(v)} style={{
                  flex: 1, padding: '7px 4px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 0.2s',
                  background: dimmer === v ? 'rgba(245,158,11,0.2)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${dimmer === v ? '#F59E0B' : 'rgba(255,255,255,0.08)'}`,
                  color: dimmer === v ? '#F59E0B' : 'rgba(255,255,255,0.4)',
                }}>{lbl}</button>
              ))}
            </div>
          </div>
        </div>

        {/* ── RIGHT: Teams ── */}
        <div style={col}>
          {/* Teams status */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Video} title="Teams Room" color="#5B5EA6" />

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Camera */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {camOn ? <Video size={16} style={{ color: '#02C9A8' }} /> : <VideoOff size={16} style={{ color: '#E94B4B' }} />}
                  <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Camera</span>
                </div>
                <button onClick={() => setCamOn(p => !p)} style={{
                  padding: '5px 14px', borderRadius: 16, fontSize: 12, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 0.2s',
                  background: camOn ? 'rgba(2,201,168,0.2)' : 'rgba(233,75,75,0.15)',
                  border: `1px solid ${camOn ? '#02C9A8' : '#E94B4B'}`,
                  color: camOn ? '#02C9A8' : '#E94B4B',
                }}>{camOn ? 'On' : 'Off'}</button>
              </div>

              {/* Microphone */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {micOn ? <Mic size={16} style={{ color: '#02C9A8' }} /> : <MicOff size={16} style={{ color: '#E94B4B' }} />}
                  <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Microphone</span>
                </div>
                <button onClick={() => setMicOn(p => !p)} style={{
                  padding: '5px 14px', borderRadius: 16, fontSize: 12, fontWeight: 700,
                  cursor: 'pointer', transition: 'all 0.2s',
                  background: micOn ? 'rgba(2,201,168,0.2)' : 'rgba(233,75,75,0.15)',
                  border: `1px solid ${micOn ? '#02C9A8' : '#E94B4B'}`,
                  color: micOn ? '#02C9A8' : '#E94B4B',
                }}>{micOn ? 'Unmuted' : 'Muted'}</button>
              </div>

              {/* Speaker */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>Speaker Volume</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#ABC7FF' }}>{speakerVol}%</span>
                </div>
                <input type="range" min={0} max={100} value={speakerVol}
                  onChange={e => setSpeakerVol(Number(e.target.value))}
                  style={{ width: '100%', accentColor: '#ABC7FF' }} />
              </div>

              {/* Join button */}
              {!inCall ? (
                <button className="btn-primary" onClick={() => setJoinDialog(true)} style={{ width: '100%', gap: 8 }}>
                  <Phone size={14} /> Join Meeting
                </button>
              ) : (
                <button onClick={() => { setInCall(false); setCallSeconds(0) }} style={{
                  width: '100%', padding: '12px', borderRadius: 6, cursor: 'pointer',
                  background: 'rgba(233,75,75,0.2)', border: '1px solid #E94B4B',
                  color: '#E94B4B', fontWeight: 700, fontSize: 14, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', gap: 8,
                }}>
                  <PhoneOff size={14} /> End Call
                </button>
              )}
            </div>
          </div>

          {/* Active call panel */}
          {inCall && (
            <div className="glass-card animate-slide-up" style={{ padding: 20, border: '1px solid rgba(2,201,168,0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#02C9A8', boxShadow: '0 0 6px #02C9A8' }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#02C9A8' }}>Active Call</span>
                </div>
                <span style={{ fontSize: 16, fontWeight: 900, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
                  {formatDuration(callSeconds)}
                </span>
              </div>
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Participants</div>
                {PARTICIPANTS.map(p => (
                  <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <div style={{
                      width: 26, height: 26, borderRadius: '50%',
                      background: 'linear-gradient(135deg, #0A3690, #56CCF2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 900, color: '#fff',
                    }}>
                      {p.split(' ').map(w => w[0]).join('')}
                    </div>
                    <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.8)' }}>{p}</span>
                    <div style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: '#02C9A8' }} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upcoming meetings */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Calendar} title="Meeting Room Calendar" color="#56CCF2" />
            {MEETINGS.map(m => (
              <div key={m.id} style={{
                padding: '10px 12px', borderRadius: 8, marginBottom: 8,
                background: 'rgba(86,204,242,0.05)', border: '1px solid rgba(86,204,242,0.1)',
              }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: '#fff', marginBottom: 3 }}>{m.title}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Clock size={11} style={{ color: '#56CCF2' }} />
                  <span style={{ fontSize: 11, color: '#56CCF2' }}>{m.time}</span>
                  <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginLeft: 4 }}>· {m.organizer}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Content sharing */}
          <div className="glass-card" style={{ padding: 20 }}>
            <SectionHeader icon={Share2} title="Content Sharing" color="#8B5CF6" />
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <select
                value={shareSource}
                onChange={e => setShareSource(e.target.value)}
                style={{
                  flex: 1, background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.2)',
                  borderRadius: 8, color: '#ABC7FF', padding: '8px 10px', fontSize: 13, outline: 'none',
                }}
              >
                {SHARE_SOURCES.map(s => <option key={s} value={s} style={{ background: '#0A1535' }}>{s}</option>)}
              </select>
              <button
                onClick={() => setSharing(p => !p)}
                style={{
                  padding: '8px 14px', borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: 'pointer',
                  background: sharing ? 'rgba(139,92,246,0.2)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${sharing ? '#8B5CF6' : 'rgba(255,255,255,0.08)'}`,
                  color: sharing ? '#8B5CF6' : 'rgba(255,255,255,0.5)',
                  transition: 'all 0.2s', whiteSpace: 'nowrap',
                }}
              >
                {sharing ? 'Stop Sharing' : 'Start Sharing'}
              </button>
            </div>
            {sharing && (
              <div style={{
                padding: '8px 12px', borderRadius: 8, background: 'rgba(139,92,246,0.1)',
                border: '1px solid rgba(139,92,246,0.3)', fontSize: 12, color: '#8B5CF6', fontWeight: 700,
              }}>
                Sharing: {shareSource}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Join dialog */}
      {joinDialog && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div className="glass-card" style={{ padding: 32, width: 380, border: '1px solid rgba(2,201,168,0.2)' }}>
            <h3 style={{ margin: '0 0 20px', color: '#fff', fontSize: 18, fontWeight: 900 }}>Join Meeting</h3>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', display: 'block', marginBottom: 6, fontWeight: 700 }}>
                Meeting ID
              </label>
              <input
                value={meetingId}
                onChange={e => setMeetingId(e.target.value)}
                placeholder="e.g. 123-456-789"
                style={{
                  width: '100%', background: 'rgba(10,54,144,0.25)', border: '1px solid rgba(171,199,255,0.2)',
                  borderRadius: 8, color: '#fff', padding: '10px 14px', fontSize: 14, outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn-primary" onClick={() => { setJoinDialog(false); setInCall(true); setCallSeconds(0) }}
                style={{ flex: 1 }}>
                <Phone size={14} /> Join Now
              </button>
              <button className="btn-secondary" onClick={() => setJoinDialog(false)} style={{ flex: 1 }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
