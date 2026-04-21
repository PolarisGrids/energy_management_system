// Spec 018 W3.T11 — Distribution-room sensors dashboard (SMOC-FUNC-018).
// Route: /distribution.
// Uses existing /api/v1/sensors/* endpoints (transformer_sensor_reading
// populated by hesv2.sensor.readings Kafka consumer).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Thermometer, Droplets, Flame, Waves, DoorOpen, RefreshCw, AlertTriangle,
  CheckCircle, Gauge, ShieldAlert, Activity,
} from 'lucide-react'
import { sensorsAPI, metersAPI, alarmsAPI } from '@/services/api'

const fmt = (v, d = 1) =>
  v == null ? '—' : Number(v).toLocaleString('en-ZA', { maximumFractionDigits: d })

const ICON_BY_TYPE = {
  oil_temp: Thermometer,
  ambient_temp: Thermometer,
  humidity: Droplets,
  smoke: Flame,
  water: Waves,
  water_immersion: Waves,
  door: DoorOpen,
  door_access: DoorOpen,
  load_current: Gauge,
}

const COLOR_BY_TYPE = {
  oil_temp: '#F59E0B',
  ambient_temp: '#F97316',
  humidity: '#56CCF2',
  smoke: '#E94B4B',
  water: '#ABC7FF',
  water_immersion: '#ABC7FF',
  door: '#02C9A8',
  door_access: '#02C9A8',
  load_current: '#F59E0B',
}

export default function DistributionRoom() {
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // SMOC-FUNC-018-FR-02 — active equipment alarms, grouped by transformer.
  const [alarmsByTx, setAlarmsByTx] = useState({})

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      // Per-transformer sensor lists form the "room" grouping.
      const [txRes, sensorsRes, alarmsRes] = await Promise.all([
        metersAPI.transformers().catch(() => ({ data: [] })),
        sensorsAPI.list({}),
        alarmsAPI.list({ status: 'active', limit: 200 }).catch(() => ({ data: [] })),
      ])
      const transformers = txRes.data
      const sensors = sensorsRes.data

      const txMap = new Map(
        (transformers || []).map((t) => [t.id, t]),
      )
      const byTx = new Map()
      for (const s of sensors || []) {
        const key = s.transformer_id
        if (!byTx.has(key)) byTx.set(key, [])
        byTx.get(key).push(s)
      }
      const out = []
      for (const [txId, sensorList] of byTx.entries()) {
        const tx = txMap.get(txId) || { id: txId, name: `DTR-${txId}` }
        out.push({ transformer: tx, sensors: sensorList })
      }
      out.sort((a, b) => (a.transformer.name || '').localeCompare(b.transformer.name || ''))
      setRooms(out)

      // Bucket active alarms by transformer_id so each RoomCard can list
      // its own equipment alarms (FR-02).
      const ab = {}
      for (const a of (alarmsRes.data || [])) {
        const tid = a.transformer_id ?? a.source_id ?? null
        if (tid == null) continue
        if (!ab[tid]) ab[tid] = []
        ab[tid].push(a)
      }
      setAlarmsByTx(ab)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load distribution-room data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 60_000)
    return () => clearInterval(id)
  }, [load])

  const totals = useMemo(() => {
    const allSensors = rooms.flatMap((r) => r.sensors)
    const critical = allSensors.filter((s) => (s.status || '').toLowerCase() === 'critical').length
    const warning = allSensors.filter((s) => (s.status || '').toLowerCase() === 'warning').length
    const online = allSensors.filter((s) => (s.status || '').toLowerCase() === 'ok' || (s.status || '').toLowerCase() === 'normal').length
    return { rooms: rooms.length, critical, warning, online }
  }, [rooms])

  return (
    <div className="space-y-5 animate-slide-up" data-testid="distribution-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white font-black" style={{ fontSize: 22 }}>Distribution Rooms</h1>
          <div className="text-white/40" style={{ fontSize: 13, marginTop: 2 }}>
            REQ-25 · Temp · Humidity · Smoke · Water · Door Access
          </div>
        </div>
        <button onClick={load} disabled={loading}
          className="btn-secondary flex items-center gap-2"
          style={{ padding: '8px 16px', fontSize: 13 }}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="glass-card p-3 flex items-center gap-3"
          style={{ borderColor: 'rgba(233,75,75,0.3)', background: 'rgba(233,75,75,0.08)' }}>
          <AlertTriangle size={16} style={{ color: '#E94B4B' }} />
          <span className="text-white/80" style={{ fontSize: 13 }}>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPI icon={Gauge} label="Rooms" value={totals.rooms} color="#56CCF2" />
        <KPI icon={CheckCircle} label="Sensors Normal" value={totals.online} color="#02C9A8" />
        <KPI icon={AlertTriangle} label="Warnings" value={totals.warning} color="#F59E0B" />
        <KPI icon={Flame} label="Critical" value={totals.critical} color="#E94B4B" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="distribution-rooms">
        {rooms.map((r) => (
          <RoomCard
            key={r.transformer.id}
            room={r}
            alarms={alarmsByTx[r.transformer.id] || []}
          />
        ))}
        {rooms.length === 0 && !loading && (
          <div className="glass-card p-6 text-center text-white/40 md:col-span-2 xl:col-span-3" style={{ fontSize: 13 }}>
            No distribution-room sensors registered.
          </div>
        )}
      </div>
    </div>
  )
}

function KPI({ icon: Icon, label, value, color = '#02C9A8' }) {
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: `${color}20` }}>
          <Icon size={18} style={{ color }} />
        </div>
      </div>
      <div className="mt-3">
        <div className="text-white font-black" style={{ fontSize: 26 }}>{value}</div>
        <div className="text-white/50 font-medium mt-0.5" style={{ fontSize: 13 }}>{label}</div>
      </div>
    </div>
  )
}

function RoomCard({ room, alarms = [] }) {
  const status = (room.sensors || []).reduce((worst, s) => {
    const v = (s.status || '').toLowerCase()
    if (v === 'critical') return 'critical'
    if (v === 'warning' && worst !== 'critical') return 'warning'
    return worst
  }, 'normal')
  const borderColor =
    status === 'critical' ? 'rgba(233,75,75,0.4)'
    : status === 'warning' ? 'rgba(245,158,11,0.4)'
    : 'rgba(2,201,168,0.2)'
  // Highlight environmental sensors that SMOC-18 specifically calls out
  // (smoke / water / temperature) so they're never buried at the bottom.
  const critTypes = ['smoke', 'water', 'water_immersion', 'winding_temp', 'oil_temp']
  const sortedSensors = [...(room.sensors || [])].sort((a, b) => {
    const ai = critTypes.indexOf(a.sensor_type); const bi = critTypes.indexOf(b.sensor_type)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
  const txId = room.transformer.id
  return (
    <div className="glass-card p-4" data-testid="distribution-room" style={{ borderColor }}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-white font-bold" style={{ fontSize: 14 }}>
            {room.transformer.name || `DTR ${txId}`}
          </div>
          <div className="text-white/40" style={{ fontSize: 11 }}>
            Transformer ID {txId}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={
            status === 'critical' ? 'badge-critical'
            : status === 'warning' ? 'badge-medium'
            : 'badge-ok'
          }>{status}</span>
          {/* SMOC-FUNC-018-FR-06 — jump to per-sensor history trend. */}
          <Link
            to={`/sensors?transformer=${txId}`}
            className="btn-secondary"
            style={{ padding: '4px 8px', fontSize: 10, gap: 3 }}
            title="View historical sensor trend"
          >
            <Activity size={10} /> History
          </Link>
        </div>
      </div>

      {alarms.length > 0 && (
        // SMOC-FUNC-018-FR-02 — equipment alarm roll-up (top 3 per room).
        <div className="mb-3 rounded-lg px-2 py-1.5"
          style={{ background: 'rgba(233,75,75,0.08)', border: '1px solid rgba(233,75,75,0.2)' }}>
          <div className="flex items-center gap-1.5 mb-1">
            <ShieldAlert size={11} style={{ color: '#E94B4B' }} />
            <span style={{ fontSize: 10, color: '#E94B4B', fontWeight: 700, textTransform: 'uppercase' }}>
              {alarms.length} active alarm{alarms.length !== 1 ? 's' : ''}
            </span>
          </div>
          {alarms.slice(0, 3).map((a) => (
            <div key={a.id} className="text-white/70" style={{ fontSize: 10 }}>
              · {a.alarm_type || a.title || 'Alarm'}
              <span className="text-white/40"> — {(a.severity || '').toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        {sortedSensors.map((s) => <SensorCell key={s.id} sensor={s} />)}
      </div>
    </div>
  )
}

function SensorCell({ sensor }) {
  const Icon = ICON_BY_TYPE[sensor.sensor_type] || Gauge
  const color = COLOR_BY_TYPE[sensor.sensor_type] || '#ABC7FF'
  const status = (sensor.status || 'normal').toLowerCase()
  // Backend schema returns `value`; prior bug read `last_value` and always
  // rendered '—'. Keep the fallback so older payloads still display.
  const rawValue = sensor.value ?? sensor.last_value
  const isBoolean = ['smoke', 'water', 'water_immersion', 'door', 'door_access'].includes(sensor.sensor_type)
  const display = isBoolean
    ? (rawValue ? 'ALARM' : 'OK')
    : `${fmt(rawValue, 1)}${sensor.unit ? ` ${sensor.unit}` : ''}`
  return (
    <div className="rounded-lg p-2 flex items-center gap-2"
      style={{
        background:
          status === 'critical' ? 'rgba(233,75,75,0.08)'
          : status === 'warning' ? 'rgba(245,158,11,0.08)'
          : 'rgba(255,255,255,0.03)',
      }}>
      <div className="w-8 h-8 rounded-lg flex items-center justify-center"
        style={{ background: `${color}20` }}>
        <Icon size={14} style={{ color }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-white/40" style={{ fontSize: 10 }}>
          {(sensor.sensor_type || '').replace(/_/g, ' ')}
        </div>
        <div className="text-white font-bold" style={{ fontSize: 13, fontFamily: 'monospace' }}>
          {display}
        </div>
      </div>
    </div>
  )
}
